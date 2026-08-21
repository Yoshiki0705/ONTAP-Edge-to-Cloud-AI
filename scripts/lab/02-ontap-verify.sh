#!/usr/bin/env bash
# =============================================================================
# 02-ontap-verify.sh — Task 2: ONTAP inventory and health (read-only)
#
# Authenticates as ${ONTAP_RO_USER}, a login bound to the built-in `readonly` role.
# Nothing here can change the cluster: the role rejects create/modify/delete, so a
# mistake in this script fails closed rather than reconfiguring storage.
#
# Every verdict runs its own read command and refuses to conclude anything when that
# command fails. An earlier revision evaluated captured text instead, and because a
# failed ONTAP call still emits an error message onto stdout, nine checks reported
# PASS against a cluster that was never contacted. A check that cannot tell "no bad
# rows" from "the command did not run" is worse than no check.
#
# Usage:
#   ./scripts/lab/02-ontap-verify.sh
#   ./scripts/lab/02-ontap-verify.sh --section svm      # one section only
#   ./scripts/lab/02-ontap-verify.sh --raw              # print raw ONTAP output
#   ./scripts/lab/02-ontap-verify.sh --evidence
#
# Sections: cluster, license, svm, lif, volume, export, s3
#
# Exit codes:
#   0 — every check passed
#   1 — at least one check failed
#   2 — usage or environment error
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lab/lib/env.sh
source "${SCRIPT_DIR}/lib/env.sh"

SECTIONS_ALL="cluster license svm lif volume export s3"
SECTIONS=""
SHOW_RAW=0
WRITE_EVIDENCE=0

while (( $# > 0 )); do
  case "$1" in
    --section) [[ -n "${2:-}" ]] || lab_die "--section needs a value (${SECTIONS_ALL// /, })"
               case " ${SECTIONS_ALL} " in
                 *" $2 "*) : ;;
                 *) lab_die "unknown section: $2 (choose from ${SECTIONS_ALL// /, })" ;;
               esac
               SECTIONS="${SECTIONS} $2"; shift ;;
    --raw)     SHOW_RAW=1 ;;
    --evidence) WRITE_EVIDENCE=1 ;;
    --show-targets) LAB_SHOW_TARGETS=1 ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)         lab_die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done
SECTIONS="${SECTIONS:-$SECTIONS_ALL}"

lab_load_env
lab_require ONTAP_CLUSTER_MGMT ONTAP_RO_USER SVM1_NAME SVM2_S3_NAME

want() { [[ " ${SECTIONS} " == *" $1 "* ]]; }

ONTAP_RAW_LOG="$(mktemp)"
trap 'rm -f "$ONTAP_RAW_LOG"' EXIT

# ---------------------------------------------------------------------------
# ontap CMD — run one clustershell command. Prints output, returns its status.
#
# `-rows 0` disables the pager. Without it a long `volume show` blocks on a
# "Press <space> to page down" prompt and the ssh call hangs until ConnectTimeout,
# which reads as a network fault rather than a paging prompt.
# ---------------------------------------------------------------------------
ontap() {
  local cmd="$*" out rc
  if out="$(lab_ssh ONTAP_CLUSTER_MGMT ONTAP_RO_USER -- "set -showallfields false -rows 0; ${cmd}" 2>&1)"; then
    rc=0
  else
    rc=$?
  fi
  printf '%s\n' "$out"
  { printf '\n$ %s\n%s%s\n' "$cmd" "$( ((rc==0)) || printf '[FAILED rc=%d] ' "$rc" )" "$out"; } >> "$ONTAP_RAW_LOG"
  return "$rc"
}

# A readonly role rejects mutating verbs with a permission error. Distinguishing that
# from a genuine fault matters: "unrecognized command" on 9.19.1 means the feature name
# changed, "not authorized" means the role is working as intended.
explain_ontap_error() {
  case "$1" in
    *"not authorized"*|*"Insufficient privileges"*)
      lab_note "readonly role refused this command. Expected for mutating verbs." ;;
    *"Unrecognized command"*|*"Ambiguous command"*)
      lab_note "command name not present on this release — check the 9.19 CLI reference." ;;
    *"is not a recognized"*|*"Invalid field"*)
      lab_note "field name not present on this release." ;;
    *"Permission denied"*|*"Connection refused"*|*"Operation timed out"*|*"Could not resolve"*)
      lab_note "did not reach the cluster; fix task 1 before reading this section." ;;
  esac
}

# _run LABEL CMD — shared preamble. Sets RUN_OUT, returns non-zero when the command
# failed, having already reported the failure.
RUN_OUT=""
_run() {
  local label="$1" cmd="$2"
  if RUN_OUT="$(ontap "$cmd")"; then
    (( SHOW_RAW == 1 )) && lab_indent <<< "$RUN_OUT"
    if [[ -z "${RUN_OUT//[[:space:]]/}" ]]; then
      lab_fail "${label} — command succeeded but returned no rows"
      return 1
    fi
    return 0
  fi
  lab_fail "${label} — read command failed, nothing evaluated"
  explain_ontap_error "$RUN_OUT"
  (( SHOW_RAW == 1 )) && lab_indent <<< "$RUN_OUT"
  return 1
}

# ontap_show LABEL CMD [EXPECT] — the command ran and its output matches EXPECT.
ontap_show() {
  local label="$1" cmd="$2" expect="${3:-}"
  _run "$label" "$cmd" || return 1
  if [[ -z "$expect" ]] || grep -qiE "$expect" <<< "$RUN_OUT"; then
    lab_pass "$label"; return 0
  fi
  lab_fail "${label} — output did not match /${expect}/"
  return 1
}

# ontap_absent LABEL PATTERN CMD FOUND_MSG — PASS only when the command ran and the
# pattern is absent from real rows.
ontap_absent() {
  local label="$1" pattern="$2" cmd="$3" found="$4"
  _run "$label" "$cmd" || return 1
  if grep -qiE "$pattern" <<< "$RUN_OUT"; then lab_fail "$found"; return 1; fi
  lab_pass "$label"; return 0
}

# ontap_absent_warn — advisory variant.
ontap_absent_warn() {
  local label="$1" pattern="$2" cmd="$3" warned="$4"
  _run "$label" "$cmd" || return 1
  if grep -qiE "$pattern" <<< "$RUN_OUT"; then lab_warn "$warned"; return 1; fi
  lab_pass "$label"; return 0
}

# ontap_present_warn — PASS when the pattern IS present.
ontap_present_warn() {
  local label="$1" pattern="$2" cmd="$3" missing_msg="$4"
  _run "$label" "$cmd" || return 1
  if grep -qiE "$pattern" <<< "$RUN_OUT"; then lab_pass "$label"; return 0; fi
  lab_warn "$missing_msg"; return 1
}

# ---------------------------------------------------------------------------
# cluster — health of the cluster and both nodes
# ---------------------------------------------------------------------------
if want cluster; then
  lab_header "cluster — health and version"

  # Expected shape:
  #   Node                  Health  Eligibility  Epsilon
  #   --------------------- ------- ------------ --------
  #   <node1>               true    true         false
  #   <node2>               true    true         true
  ontap_absent "no node reports health=false" '\bfalse\b' \
    "cluster show -fields node,health" \
    "a node reports health=false — investigate before trusting anything else in this run" || true

  # Expected shape:
  #   NetApp Release 9.19.1: <build date>
  if ontap_show "version — release string present" "version" "NetApp Release"; then
    LAB_OBSERVED_ONTAP_VERSION="$(head -1 <<< "$RUN_OUT")"
  fi

  # Expected shape:
  #   Node    Partner   Possible
  #   ------- --------- --------
  #   <node1> <node2>   true
  ontap_absent "storage failover — takeover possible on both nodes" \
    '(^|[[:space:]])false([[:space:]]|$)' \
    "storage failover show -fields node,partner,possible" \
    "takeover is not possible on at least one node — one controller cannot cover the other" || true
fi

# ---------------------------------------------------------------------------
# license — entitlement and expiry
#
# FlexCache and ONTAP S3 are separately licensed. An expired license does not always
# fail loudly at create time, so this reads expiry rather than mere presence.
# ---------------------------------------------------------------------------
if want license; then
  lab_header "license — entitlement and expiry"

  # Expected shape:
  #   Serial Number  Package    Type     Expiration
  #   -------------- ---------- -------- ----------
  #   <serial>       NFS        license  -
  if _run "license table readable" "system license show -fields package,expiration"; then
    lab_pass "license table readable"
    license_out="$RUN_OUT"
    for pkg in NFS CIFS S3 FlexCache; do
      if grep -qiE "(^|[[:space:]])${pkg}([[:space:]]|$)" <<< "$license_out"; then
        lab_pass "license present: ${pkg}"
      else
        lab_warn "license not listed: ${pkg}"
        case "$pkg" in
          S3)        lab_note "Task 3 (svm1 S3 server) needs this." ;;
          FlexCache) lab_note "Task 5 needs this on both origin and cache." ;;
        esac
      fi
    done
    if grep -qE '[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}' <<< "$license_out"; then
      lab_warn "one or more licenses carry an expiration date — check it against today"
    else
      lab_pass "no dated expirations (perpetual or demo-free)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# svm — the two SVMs this lab uses
# ---------------------------------------------------------------------------
if want svm; then
  lab_header "svm — data SVMs"

  # Expected shape:
  #   Vserver  Type  Subtype  Admin State  Operational State  Allowed Protocols
  #   -------- ----- -------- ------------ ------------------ -----------------
  #   svm1     data  default  running      running            nfs, cifs
  ontap_show "vserver show — SVM1_NAME running" \
    "vserver show -vserver ${SVM1_NAME} -fields vserver,state,allowed-protocols" "running" || true

  ontap_show "vserver show — SVM2_S3_NAME running" \
    "vserver show -vserver ${SVM2_S3_NAME} -fields vserver,state,allowed-protocols" "running" || true

  # This is the finding that shaped task 6: a volume belongs to exactly one SVM, so NFS
  # on svm1 and S3 on svm2-s3 cannot expose the same data. Reading allowed-protocols on
  # svm1 says whether the S3 server that task 3 adds is already there.
  if ! ontap_present_warn "SVM1_NAME allows s3 — dual-protocol on one volume is possible" \
        's3' "vserver show -vserver ${SVM1_NAME} -fields allowed-protocols" \
        "SVM1_NAME does not allow s3 yet"; then
    lab_note "Task 6 (an NFS write readable over S3) needs the S3 server on this SVM:"
    lab_note "a volume belongs to one SVM, so svm2-s3 cannot serve svm1's volumes."
    lab_note "Task 3 --apply adds it:  vserver add-protocols -vserver <svm1> -protocols s3"
  fi
fi

# ---------------------------------------------------------------------------
# lif — data and management interfaces
# ---------------------------------------------------------------------------
if want lif; then
  lab_header "lif — interfaces"

  # Expected shape:
  #   Vserver  Logical    Status     Network        Current  Current Is
  #                       Admin/Oper Address/Mask   Node     Port    Home
  #   -------- ---------- ---------- -------------- -------- ------- ----
  #   svm1     nfs_lif1   up/up      <addr>/<mask>  <node1>  a0a-103 true
  ontap_absent "no LIF reports oper=down" '[[:space:]]down' \
    "network interface show -fields vserver,lif,status-oper" \
    "at least one LIF is operationally down" || true

  # A LIF away from home survives failover but adds a hop. Advisory, not a failure.
  ontap_absent_warn "every LIF is on its home port" '(^|[[:space:]])false([[:space:]]|$)' \
    "network interface show -fields lif,is-home" \
    "a LIF is not on its home port — revert before measuring throughput" || true
fi

# ---------------------------------------------------------------------------
# volume — volumes behind the exports and buckets
# ---------------------------------------------------------------------------
if want volume; then
  lab_header "volume — state and junction paths"

  # Expected shape:
  #   Vserver  Volume            State   Junction Path      Available  Total
  #   -------- ----------------- ------- ------------------ ---------- -----
  #   svm1     nfsdatastore_ssd  online  /nfsdatastore_ssd  ...        ...
  ontap_absent "no volume is offline or restricted" \
    '[[:space:]](offline|restricted)([[:space:]]|$)' \
    "volume show -fields vserver,volume,state,junction-path,size,available" \
    "a volume is offline or restricted" || true

  # An access point attaches only to a volume that has a junction path. Which volumes
  # lack one determines what task 3 can expose.
  if ! ontap_absent_warn "every volume on SVM1_NAME is mounted" \
        '[[:space:]]-([[:space:]]|$)' \
        "volume show -vserver ${SVM1_NAME} -fields volume,junction-path" \
        "a volume on SVM1_NAME has no junction path"; then
    lab_note "Unmounted volumes cannot back an access point and are invisible to NFS clients."
  fi
fi

# ---------------------------------------------------------------------------
# export — NFS export policies and rules
# ---------------------------------------------------------------------------
if want export; then
  lab_header "export — NFS policies and rules"

  # Expected shape:
  #   Vserver  Policy   Rule  Client     RO    RW    Super  Protocol
  #                     Index Match      Rule  Rule  User
  #   -------- -------- ----- ---------- ----- ----- ------ ---------
  #   svm1     default  1     <cidr>     sys   sys   sys    nfs3,nfs4
  if ! ontap_absent_warn "no export rule matches 0.0.0.0/0" '0\.0\.0\.0/0' \
        "export-policy rule show -vserver ${SVM1_NAME} -fields policyname,clientmatch,rorule,rwrule,protocol" \
        "an export rule matches 0.0.0.0/0"; then
    lab_note "Every client on the reachable network can mount. Narrow it to the VLAN103 CIDR."
  fi

  ontap_absent_warn "export rules name explicit auth flavours" \
    '(^|[[:space:]])(any|none)([[:space:]]|$)' \
    "export-policy rule show -vserver ${SVM1_NAME} -fields rorule,rwrule" \
    "an export rule uses rorule/rwrule of any or none — confirm that is deliberate" || true

  ontap_show "nfs show — NFS versions enabled" \
    "nfs show -vserver ${SVM1_NAME} -fields vserver,v3,v4.0,v4.1" "" || true
fi

# ---------------------------------------------------------------------------
# s3 — ONTAP S3 object server on svm2-s3
#
# This is the on-premises ONTAP S3 object server, not the FSx for ONTAP S3 Access Point
# feature. They are different mechanisms and neither is evidence for the other.
# ---------------------------------------------------------------------------
if want s3; then
  lab_header "s3 — ONTAP S3 on SVM2_S3_NAME"

  # Expected shape:
  #   Vserver  Server Name  Is Enabled  Default UNIX User
  #   -------- ------------ ----------- -----------------
  #   svm2-s3  <fqdn>       true        pcuser
  ontap_show "object-store-server show — server enabled" \
    "vserver object-store-server show -vserver ${SVM2_S3_NAME}" "true" || true

  # Expected shape:
  #   Vserver  Bucket    Volume  Size  Encryption  Role
  #   -------- --------- ------- ----- ----------- ----
  #   svm2-s3  <bucket>  <fv>    ...   false       s3
  ontap_show "bucket show — buckets listed" \
    "vserver object-store-server bucket show -vserver ${SVM2_S3_NAME}" "" || true

  # `user show` does not print secrets. Regenerating a key is what reveals one, and
  # that is a task 3 action behind --apply.
  ontap_show "user show — S3 users listed" \
    "vserver object-store-server user show -vserver ${SVM2_S3_NAME}" "" || true

  ontap_show "policy show — bucket access policies" \
    "vserver object-store-server bucket policy show -vserver ${SVM2_S3_NAME}" "" || true

  # An S3 endpoint on plain HTTP puts the access key on the wire in clear text.
  if ! ontap_absent_warn "plain HTTP not enabled" 'is-http-enabled[^0-9a-z]*true' \
        "vserver object-store-server show -vserver ${SVM2_S3_NAME} -fields is-http-enabled,is-https-enabled,secure-listener-port" \
        "plain HTTP is enabled on the object store server"; then
    lab_note "Access keys transit in clear text. Prefer HTTPS only for the tiering endpoint."
  fi
fi

# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------
if (( WRITE_EVIDENCE == 1 )); then
  lab_require LAB_RUN_ID

  # Raw transcript into the gitignored directory: it holds addresses and serials.
  raw="$(lab_raw_log_path 02-ontap-verify)"
  cat "$ONTAP_RAW_LOG" > "$raw"
  chmod 600 "$raw" 2>/dev/null || true
  lab_info "raw transcript (gitignored): ${raw}"

  evidence="$(lab_evidence_path 02-ontap-verify)"
  {
    echo "# Task 2 — ONTAP inventory and health (read-only)"
    echo
    echo "| field | value |"
    echo "|---|---|"
    echo "| run id | ${LAB_RUN_ID} |"
    echo "| recorded | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
    echo "| authenticated as | readonly role login |"
    echo "| ONTAP release observed | ${LAB_OBSERVED_ONTAP_VERSION:-not reached} |"
    echo "| sections run | ${SECTIONS} |"
    echo "| pass | ${LAB_PASS} |"
    echo "| fail | ${LAB_FAIL} |"
    echo "| warn | ${LAB_WARN} |"
    echo
    echo "Raw command output is deliberately absent: it carries management addresses and"
    echo "controller serial numbers. It stays in scripts/lab/.evidence/, which is"
    echo "gitignored. Quote a line into this file by hand only after checking that it"
    echo "carries nothing identifying."
  } > "$evidence"
  lab_info "summary (tracked): ${evidence}"
fi

lab_summary || exit 1
