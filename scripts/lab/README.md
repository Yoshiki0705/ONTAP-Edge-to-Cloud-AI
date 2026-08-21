# Lab verification runbook

Scripts that verify a physical Edge-to-Cloud AI lab: an ONTAP cluster, Instaclustr
Kafka and ClickHouse nodes, and Amazon FSx for NetApp ONTAP. They produce the evidence
that fills the unverified rows in `docs/ja/verification-status.md` and its English
mirror.

Everything here defaults to read-only. Tasks that can change state require `--apply`,
and the FlexCache task additionally requires `--confirm`.

## Setup

```bash
cp scripts/lab/.env.example scripts/lab/.env
chmod 600 scripts/lab/.env      # the loader refuses any looser mode
$EDITOR scripts/lab/.env
```

`scripts/lab/.env` is gitignored. The template is tracked, which needs the
`!.env.example` negation in `.gitignore`; without it the `.env.*` rule swallows the
template and `git add` silently does nothing.

## How values are handled

Addresses, host names and user names are treated the same as passwords: read from
`.env`, never printed, never committed.

- Reports name the variable, not its contents. `${ONTAP_CLUSTER_MGMT}` appears where an
  address would be, so a pasted transcript cannot disclose the topology.
- `--show-targets` resolves values on your own terminal. Do not redirect that into a
  tracked file.
- No partial masks or fingerprints of hosts. A short hash of an IPv4 address is
  brute-forceable, so a "redacted" fingerprint would be a false reassurance.
- `.env` is parsed, not sourced. Sourcing would execute whatever the file contains.
- Raw device output goes to `scripts/lab/.evidence/` (gitignored) because it carries
  addresses and controller serial numbers. Only the redacted summary goes to
  `docs/verification-evidence/`.

## Credentials

Two ONTAP logins, so a verification run cannot change storage even by mistake.

| Variable | Role | Used by |
|---|---|---|
| `ONTAP_RO_USER` | built-in `readonly` | tasks 1, 2, 6 |
| `ONTAP_ADMIN_USER` | admin | only tasks invoked with `--apply` |

Create the read-only login once, as admin:

```
security login create -user-or-group-name <ro-user> \
  -application ssh -authentication-method publickey -role readonly
security publickey create -username <ro-user> -publickey "ssh-ed25519 AAAA..."
```

## Task status

| # | Task | Script | State |
|---|---|---|---|
| 1 | Connectivity and inventory | `01-connectivity.sh` | implemented, read-only |
| 2 | ONTAP verification | `02-ontap-verify.sh` | implemented, read-only |
| 3 | ONTAP S3 setup and validation | — | not yet written |
| 4 | Kafka to ClickHouse pipeline | — | not yet written |
| 5 | FlexCache validation | — | not yet written, per-use-case |
| 6 | Edge ingestion smoke test | — | not yet written |

Tasks 3 to 6 are specified below but not implemented. The table says so rather than
implying coverage that does not exist.

---

## Task 1 — Connectivity and inventory

### Prerequisites

- SSH key loaded for the ESXi, ONTAP and gateway logins. The scripts run
  `BatchMode=yes`, so a missing key fails instead of prompting.
- ESXi SSH enabled: Host > Services > TSM-SSH. It ships disabled.
- Read-only ONTAP login created (above).
- `.env` populated with at least: `ESXI_HOST`, `ESXI_SSH_USER`,
  `ONTAP_CLUSTER_MGMT`, `ONTAP_RO_USER`, `GATEWAY_HOST`, `GATEWAY_SSH_USER`,
  `GATEWAY_TUNNEL_PORT`.

### Commands

```bash
./scripts/lab/01-connectivity.sh                  # variable names in the report
./scripts/lab/01-connectivity.sh --show-targets    # resolve locally
./scripts/lab/01-connectivity.sh --evidence        # also write the summary file
```

### Expected result

Five sections, then a report table:

```
___ 1. TCP reachability (port 22)
  [PASS] ${ESXI_HOST} tcp/22 open
___ 2. SSH authentication
  [PASS] ${ONTAP_CLUSTER_MGMT} ssh ok as ${ONTAP_RO_USER}
         NetApp Release 9.19.1: ...
___ 3. Zero Inbound reverse tunnel
  [PASS] reverse tunnel listening on ${GATEWAY_TUNNEL_PORT} at ${GATEWAY_HOST}
  [PASS] reverse tunnel accepts a connection (far end is answering)
___ 5. Reachability report
  STATUS     TARGET                   DETAIL
  OK         ${ESXI_HOST}             tcp/22 open
```

Unset optional targets report `SKIP`, not `FAIL`. A lab mid-build should not print red
for equipment that is not connected yet.

### Pass/Fail verification

```bash
./scripts/lab/01-connectivity.sh; echo "exit=$?"
```

- `exit=0` and `FAIL: 0` — pass.
- `exit=1` — at least one probe failed; the failing row names the variable to fix.
- `exit=2` — `.env` missing, mode looser than 600, or a required variable empty.

The tunnel check is two assertions on purpose. A dead reverse tunnel leaves the ssh
process running while the forwarded port stops accepting, so a process check reports
healthy on a tunnel that carries nothing. The second assertion connects through it.

### Rollback / cleanup

Nothing to roll back: the script opens TCP sockets and runs `version`-class commands.
There is no `--apply` because there is nothing to apply. With `--evidence`, remove
`docs/verification-evidence/<run-id>-01-connectivity.md` to discard the run.

---

## Task 2 — ONTAP verification (read-only)

### Prerequisites

- Task 1 passing for `ONTAP_CLUSTER_MGMT`. Every check in task 2 fails with "did not
  reach the cluster" otherwise, which is noise rather than information.
- `.env`: `ONTAP_CLUSTER_MGMT`, `ONTAP_RO_USER`, `SVM1_NAME`, `SVM2_S3_NAME`.

### Commands

```bash
./scripts/lab/02-ontap-verify.sh                     # all sections
./scripts/lab/02-ontap-verify.sh --section cluster   # one section
./scripts/lab/02-ontap-verify.sh --raw               # include ONTAP output
./scripts/lab/02-ontap-verify.sh --evidence
```

Sections: `cluster`, `license`, `svm`, `lif`, `volume`, `export`, `s3`.

The underlying commands, all readable by the `readonly` role:

```
cluster show -fields node,health
version
storage failover show -fields node,partner,possible
system license show -fields package,expiration
vserver show -vserver <svm1> -fields vserver,state,allowed-protocols
network interface show -fields vserver,lif,status-oper
network interface show -fields lif,is-home
volume show -fields vserver,volume,state,junction-path,size,available
export-policy rule show -vserver <svm1> -fields policyname,clientmatch,rorule,rwrule,protocol
nfs show -vserver <svm1> -fields vserver,v3,v4.0,v4.1
vserver object-store-server show -vserver <svm2-s3>
vserver object-store-server bucket show -vserver <svm2-s3>
vserver object-store-server user show -vserver <svm2-s3>
vserver object-store-server bucket policy show -vserver <svm2-s3>
```

Each is prefixed with `set -showallfields false -rows 0`. Without `-rows 0` a long
`volume show` blocks on a paging prompt and the ssh call hangs until ConnectTimeout,
which reads as a network fault rather than a pager.

### Expected result

```
___ cluster — health and version
  [PASS] no node reports health=false
  [PASS] version — release string present
  [PASS] storage failover — takeover possible on both nodes
___ license — entitlement and expiry
  [PASS] license present: NFS
  [WARN] license not listed: FlexCache
         Task 5 needs this on both origin and cache.
___ svm — data SVMs
  [WARN] SVM1_NAME does not allow s3 yet
```

Output shapes for each command are recorded as comments above the corresponding check
in `02-ontap-verify.sh`, next to the assertion that depends on them.

### Pass/Fail verification

```bash
./scripts/lab/02-ontap-verify.sh; echo "exit=$?"
```

- `FAIL: 0` — pass. `WARN` rows are advisory and name what they would block.
- Any `FAIL` — the label says whether the assertion failed or the read command did.

A check reports `FAIL ... nothing evaluated` when its read command did not run. This
distinction is load-bearing: an earlier revision evaluated captured text, and because a
failed ONTAP call still writes an error message to stdout, nine checks reported `PASS`
against a cluster that was never contacted. Every verdict now runs its own command and
refuses to conclude anything from a failed one.

Two failures worth acting on immediately:

- `a node reports health=false` — nothing else in the run is trustworthy.
- `takeover is not possible on at least one node` — on an HA pair, one controller
  cannot cover the other.

### Rollback / cleanup

Read-only; nothing to roll back. `--evidence` writes two files:

```bash
rm docs/verification-evidence/<run-id>-02-ontap-verify.md   # tracked summary
rm scripts/lab/.evidence/<run-id>-02-ontap-verify.log       # gitignored transcript
```

Review the tracked summary before committing it.

---

## Tasks 3 to 6 — specified, not yet implemented

### Task 3 — ONTAP S3 setup and validation

Creates a bucket and user for ClickHouse tiering and Instaclustr backup, then tests
them through the ONTAP S3 endpoint.

This also adds the S3 server to svm1, which task 6 depends on. In ONTAP a volume
belongs to exactly one SVM, and an ONTAP S3 bucket is backed by a volume in the SVM
running the S3 server. A file written to svm1's NFS export is therefore not reachable
through svm2-s3. Serving the same data over both protocols requires the S3 server on
svm1:

```
vserver add-protocols -vserver <svm1> -protocols s3
```

Key handling: generated keys are written to `scripts/lab/.secrets` at mode 600 and never
echoed. `vserver object-store-server user show` does not print secrets; regenerating a
key is what reveals one, which is why that is an `--apply` action.

Requires `--apply`. Rollback deletes the bucket and user it created, in that order.

### Task 4 — Kafka to ClickHouse pipeline

Broker reachability from the ClickHouse nodes, a topic, sample records, a Kafka table
engine consumer with a materialized view, and a row-count check end to end.

The row-count check needs a baseline count taken before producing, because a non-zero
count proves the table has rows, not that this run delivered them.

Requires `--apply`. Rollback drops the materialized view, then the Kafka table, then
the topic.

### Task 5 — FlexCache validation

Origin and cache direction differs by use case, so this task is split per use case
under `scripts/lab/patterns/<use-case>/` rather than assuming one direction. The
architecture diagram for each use case is generated alongside it.

Note for the repository docs: `docs/ja/iot-greengrass-flexcache-integration.md:235`
states that an access point is usable on the origin side only, equating that with the
FSx for ONTAP side. That holds only while FSx for ONTAP is the origin. Where a use case
puts the origin on the on-premises cluster, that row needs rewording per pattern.

Requires `--apply` and `--confirm`. A FlexCache relationship occupies the cache volume
and has a deletion order, so an accidental run is expensive to undo.

### Task 6 — Edge ingestion smoke test

Raspberry Pi camera writes to the NFS export on svm1; the files are then read back
through S3 to confirm one dataset served over two protocols.

Blocked on task 3 adding the S3 server to svm1. Until then the S3 read has nothing to
resolve against, and reading svm2-s3 instead would look like a pass while proving
nothing about the file written over NFS.

Read-only against ONTAP; writes only the test images it then removes.

## Platform notes

`lab_probe_tcp` implements its own timeout in bash rather than calling `nc` or
`timeout`. Measured on macOS, `nc -z -w 1` against a black-holed address returned after
75 seconds, because BSD `nc` treats `-w` as an idle timeout rather than a connect
timeout; GNU `timeout` is absent on macOS, so the obvious fallback reports every host
unreachable with status 127. Both failure modes look like a dead network rather than a
broken tool.
