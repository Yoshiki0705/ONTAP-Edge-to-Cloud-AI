#!/usr/bin/env bash
# =============================================================================
# 01-connectivity.sh — Task 1: reachability and inventory (read-only)
#
# Probes SSH reachability to the hypervisor, the ONTAP cluster management LIF and the
# Instaclustr gateway, then checks that the Zero Inbound reverse tunnel the gateway
# maintains is actually carrying a listener.
#
# Read-only by construction: it opens TCP sockets and runs `version`-class commands.
# There is no --apply because there is nothing here to apply.
#
# Usage:
#   ./scripts/lab/01-connectivity.sh
#   ./scripts/lab/01-connectivity.sh --show-targets      # resolve names on this screen
#   ./scripts/lab/01-connectivity.sh --evidence          # also write an evidence file
#
# Exit codes:
#   0 — every probe passed
#   1 — at least one probe failed
#   2 — usage or environment error (missing .env, bad permissions, missing variable)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lab/lib/env.sh
source "${SCRIPT_DIR}/lib/env.sh"

WRITE_EVIDENCE=0
while (( $# > 0 )); do
  case "$1" in
    --show-targets) LAB_SHOW_TARGETS=1 ;;
    --evidence)     WRITE_EVIDENCE=1 ;;
    -h|--help)      sed -n '2,22p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)              lab_die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done

lab_load_env
lab_require \
  ESXI_HOST ESXI_SSH_USER \
  ONTAP_CLUSTER_MGMT ONTAP_RO_USER \
  GATEWAY_HOST GATEWAY_SSH_USER GATEWAY_TUNNEL_PORT

# Rows accumulate as "STATUS|VARIABLE|DETAIL" so the table renders after every probe
# has run. Printing as we go would interleave with ssh's own stderr.
declare -a ROWS=()
row() { ROWS+=("$1|$2|$3"); }

# ---------------------------------------------------------------------------
# 1. TCP reachability — separates "host is down" from "credentials are wrong"
# ---------------------------------------------------------------------------
lab_header "1. TCP reachability (port 22)"

probe_tcp_row() {
  local var="$1" port="${2:-22}"
  if lab_probe_tcp "$var" "$port"; then
    lab_pass "$(lab_target "$var") tcp/${port} open"
    row OK "$var" "tcp/${port} open"
  else
    lab_fail "$(lab_target "$var") tcp/${port} unreachable"
    row FAIL "$var" "tcp/${port} unreachable"
  fi
}

probe_tcp_row ESXI_HOST 22
probe_tcp_row ONTAP_CLUSTER_MGMT 22
probe_tcp_row GATEWAY_HOST 22

# ---------------------------------------------------------------------------
# 2. SSH authentication and identity
#
# Each target answers a different "who are you" command; there is no portable one.
# ESXi runs busybox, ONTAP runs clustershell rather than a POSIX shell.
# ---------------------------------------------------------------------------
lab_header "2. SSH authentication"

# ESXi: `vmware -v` is present on the busybox shell and needs no privilege.
if out="$(lab_ssh ESXI_HOST ESXI_SSH_USER -- 'vmware -v' 2>/dev/null)"; then
  lab_pass "$(lab_target ESXI_HOST) ssh ok — ${out}"
  row OK ESXI_HOST "ssh ok, ${out}"
else
  lab_fail "$(lab_target ESXI_HOST) ssh failed (key not accepted, or SSH service disabled)"
  lab_note "ESXi ships with SSH off. Enable: Host > Services > TSM-SSH, or via vCenter."
  row FAIL ESXI_HOST "ssh failed"
fi

# ONTAP: `version` is available to a readonly role and prints one line.
if out="$(lab_ssh ONTAP_CLUSTER_MGMT ONTAP_RO_USER -- 'version' 2>/dev/null)"; then
  lab_pass "$(lab_target ONTAP_CLUSTER_MGMT) ssh ok as \${ONTAP_RO_USER}"
  lab_note "${out}"
  row OK ONTAP_CLUSTER_MGMT "ssh ok as readonly"
  # Recorded so evidence files carry the version that produced the numbers.
  LAB_OBSERVED_ONTAP_VERSION="$out"
else
  lab_fail "$(lab_target ONTAP_CLUSTER_MGMT) ssh failed as \${ONTAP_RO_USER}"
  lab_note "Create the readonly login (admin, once):"
  lab_note "  security login create -user-or-group-name \${ONTAP_RO_USER} \\"
  lab_note "    -application ssh -authentication-method publickey -role readonly"
  row FAIL ONTAP_CLUSTER_MGMT "ssh failed as readonly"
fi

# Gateway: plain POSIX shell.
if out="$(lab_ssh GATEWAY_HOST GATEWAY_SSH_USER -- 'uname -sr' 2>/dev/null)"; then
  lab_pass "$(lab_target GATEWAY_HOST) ssh ok — ${out}"
  row OK GATEWAY_HOST "ssh ok, ${out}"
else
  lab_fail "$(lab_target GATEWAY_HOST) ssh failed"
  row FAIL GATEWAY_HOST "ssh failed"
fi

# ---------------------------------------------------------------------------
# 3. Zero Inbound reverse tunnel health
#
# The gateway dials out and holds a reverse tunnel; nothing dials in. A tunnel that
# died leaves the ssh process running while the forwarded port stops listening, so
# checking for the process alone reports healthy on a dead tunnel. This checks the
# listener, then confirms it answers.
# ---------------------------------------------------------------------------
lab_header "3. Zero Inbound reverse tunnel"

tunnel_listener_cmd="ss -ltn 2>/dev/null | grep -q ':${GATEWAY_TUNNEL_PORT} ' \
  || netstat -ltn 2>/dev/null | grep -q ':${GATEWAY_TUNNEL_PORT} '"

if lab_ssh GATEWAY_HOST GATEWAY_SSH_USER -- "$tunnel_listener_cmd" 2>/dev/null; then
  # shellcheck disable=SC2016  # ${...} is literal on purpose; the value must not appear.
  lab_pass 'reverse tunnel listening on ${GATEWAY_TUNNEL_PORT} at '"$(lab_target GATEWAY_HOST)"
  row OK GATEWAY_TUNNEL_PORT "listener present"

  # A listening socket proves the forward exists, not that the far end answers.
  if lab_ssh GATEWAY_HOST GATEWAY_SSH_USER \
      -- "timeout 5 bash -c 'exec 3<>/dev/tcp/127.0.0.1/${GATEWAY_TUNNEL_PORT}'" 2>/dev/null; then
    lab_pass "reverse tunnel accepts a connection (far end is answering)"
    row OK GATEWAY_TUNNEL_PORT "far end answering"
  else
    lab_fail "tunnel port listens but refuses connections — far end is down"
    lab_note "A half-open tunnel looks healthy to a process check. Restart the client side."
    row FAIL GATEWAY_TUNNEL_PORT "listener present, far end silent"
  fi
else
  # shellcheck disable=SC2016  # ${...} is literal on purpose; the value must not appear.
  lab_fail 'no listener on ${GATEWAY_TUNNEL_PORT} at '"$(lab_target GATEWAY_HOST)"
  row FAIL GATEWAY_TUNNEL_PORT "no listener"
fi

# ---------------------------------------------------------------------------
# 4. Data-path LIFs and Instaclustr nodes
#
# Optional variables: a lab mid-build has some of these empty, and that should skip
# rather than fail. Failing on an unset optional target would train the operator to
# ignore red output.
# ---------------------------------------------------------------------------
lab_header "4. Data-path LIFs and node ports"

optional_tcp() {
  local var="$1" port="$2" label="$3"
  if [[ -z "${!var:-}" ]]; then
    lab_skip "\${${var}} not set — ${label}"
    row SKIP "$var" "not set"
    return 0
  fi
  if lab_probe_tcp "$var" "$port"; then
    lab_pass "$(lab_target "$var") tcp/${port} open — ${label}"
    row OK "$var" "tcp/${port} open"
  else
    lab_fail "$(lab_target "$var") tcp/${port} unreachable — ${label}"
    row FAIL "$var" "tcp/${port} unreachable"
  fi
}

optional_tcp NFS_LIF_1 2049 "svm1 NFS"
optional_tcp NFS_LIF_2 2049 "svm1 NFS"
optional_tcp S3_LIF_1  443  "svm2-s3 ONTAP S3"
optional_tcp S3_LIF_2  443  "svm2-s3 ONTAP S3"
optional_tcp SVM1_S3_LIF 443 "svm1 ONTAP S3 (task 3 enables this)"
optional_tcp KAFKA_NODE_1 "${KAFKA_BOOTSTRAP_PORT:-9092}" "Kafka broker"
optional_tcp KAFKA_NODE_2 "${KAFKA_BOOTSTRAP_PORT:-9092}" "Kafka broker"
optional_tcp KAFKA_NODE_3 "${KAFKA_BOOTSTRAP_PORT:-9092}" "Kafka broker"
optional_tcp CLICKHOUSE_NODE "${CLICKHOUSE_HTTP_PORT:-8123}" "ClickHouse HTTP"

# ---------------------------------------------------------------------------
# 5. Reachability report
# ---------------------------------------------------------------------------
lab_header "5. Reachability report"

render_table() {
  printf '  %-10s %-24s %s\n' "STATUS" "TARGET" "DETAIL"
  printf '  %-10s %-24s %s\n' "------" "------" "------"
  local r status var detail
  for r in "${ROWS[@]+"${ROWS[@]}"}"; do
    IFS='|' read -r status var detail <<< "$r"
    local shown
    if [[ "$LAB_SHOW_TARGETS" == "1" ]]; then shown="${!var:-<unset>}"; else shown="\${${var}}"; fi
    printf '  %-10s %-24s %s\n' "$status" "$shown" "$detail"
  done
}
render_table

if (( WRITE_EVIDENCE == 1 )); then
  lab_require LAB_RUN_ID
  evidence="$(lab_evidence_path 01-connectivity)"
  {
    echo "# Task 1 — connectivity and inventory"
    echo
    echo "| field | value |"
    echo "|---|---|"
    echo "| run id | ${LAB_RUN_ID} |"
    echo "| recorded | $(date -u +%Y-%m-%dT%H:%M:%SZ) |"
    echo "| ONTAP version observed | ${LAB_OBSERVED_ONTAP_VERSION:-not reached} |"
    echo "| region | ${LAB_REGION:-n/a (on-premises)} |"
    echo
    echo "Targets are recorded as variable names. Resolving them is a local-only action."
    echo
    echo '```'
    LAB_SHOW_TARGETS=0 render_table
    echo '```'
  } > "$evidence"
  lab_info "evidence written: ${evidence}"
fi

lab_summary || exit 1
