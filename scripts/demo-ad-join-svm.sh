#!/usr/bin/env bash
# =============================================================================
# demo-ad-join-svm.sh — Join an FSx for ONTAP SVM to Active Directory
#
# Uses the ONTAP REST API to configure CIFS (SMB) server on the SVM,
# joining it to the specified AD domain.
#
# Prerequisites:
#   - FSx for ONTAP file system deployed (cloud/fsxn/template.yaml)
#   - AD environment deployed (infrastructure/demo-ad-environment.yaml)
#   - jq, aws CLI, curl installed
#   - Network connectivity from caller to FSx management endpoint
#
# Usage:
#   ./scripts/demo-ad-join-svm.sh \
#     --svm-id svm-0123456789abcdef0 \
#     --domain demo.edge-to-cloud.local \
#     --dns-ips 198.51.100.10,198.51.100.11 \
#     --secret-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:xxx
#
#   # Or with explicit credentials (not recommended — use Secrets Manager):
#   ./scripts/demo-ad-join-svm.sh \
#     --svm-id svm-0123456789abcdef0 \
#     --domain demo.edge-to-cloud.local \
#     --dns-ips 198.51.100.10,198.51.100.11 \
#     --ad-user Admin \
#     --ad-password 'P@ssw0rd'
#
# Exit codes:
#   0 — SVM successfully joined to AD
#   1 — Join failed (see error output)
#   2 — Usage error / missing parameters
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults & Colors
# ---------------------------------------------------------------------------
SCRIPT_NAME="$(basename "$0")"

if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
  BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
fi

info()  { printf "${BOLD}[INFO]${RESET} %s\n" "$1"; }
ok()    { printf "${GREEN}[OK]${RESET}   %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${RESET} %s\n" "$1"; }
err()   { printf "${RED}[ERR]${RESET}  %s\n" "$1" >&2; }

usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [options]

Required:
  --svm-id ID          FSx for ONTAP SVM ID (svm-xxxx)
  --domain FQDN        AD domain name (e.g., demo.edge-to-cloud.local)
  --dns-ips IPs        Comma-separated DNS IPs of the AD domain

Credentials (one of):
  --secret-arn ARN     Secrets Manager ARN containing {username, password, domain}
  --ad-user USER       AD admin username (with --ad-password)
  --ad-password PASS   AD admin password

Optional:
  --cifs-server NAME   CIFS server name (default: derived from SVM name)
  --ou OU              Organizational Unit for the computer account
  --fsxn-secret ARN    Secrets Manager ARN for ONTAP fsxadmin credentials
  --region REGION      AWS region (default: AWS_DEFAULT_REGION or ap-northeast-1)
  --dry-run            Show what would be done without executing
  -h, --help           Show this help
EOF
  exit 2
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
SVM_ID=""
DOMAIN=""
DNS_IPS=""
SECRET_ARN=""
AD_USER=""
AD_PASSWORD=""
CIFS_SERVER=""
OU=""
FSXN_SECRET_ARN=""
REGION="${AWS_DEFAULT_REGION:-${AWS_REGION:-ap-northeast-1}}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --svm-id)       SVM_ID="$2"; shift 2 ;;
    --domain)       DOMAIN="$2"; shift 2 ;;
    --dns-ips)      DNS_IPS="$2"; shift 2 ;;
    --secret-arn)   SECRET_ARN="$2"; shift 2 ;;
    --ad-user)      AD_USER="$2"; shift 2 ;;
    --ad-password)  AD_PASSWORD="$2"; shift 2 ;;
    --cifs-server)  CIFS_SERVER="$2"; shift 2 ;;
    --ou)           OU="$2"; shift 2 ;;
    --fsxn-secret)  FSXN_SECRET_ARN="$2"; shift 2 ;;
    --region)       REGION="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=true; shift ;;
    -h|--help)      usage ;;
    *)              err "Unknown option: $1"; usage ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate required params
# ---------------------------------------------------------------------------
MISSING=()
[[ -z "$SVM_ID" ]] && MISSING+=("--svm-id")
[[ -z "$DOMAIN" ]] && MISSING+=("--domain")
[[ -z "$DNS_IPS" ]] && MISSING+=("--dns-ips")

if [[ -z "$SECRET_ARN" && ( -z "$AD_USER" || -z "$AD_PASSWORD" ) ]]; then
  MISSING+=("--secret-arn OR (--ad-user + --ad-password)")
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
  err "Missing required parameters: ${MISSING[*]}"
  echo ""
  usage
fi

# ---------------------------------------------------------------------------
# Resolve AD credentials
# ---------------------------------------------------------------------------
if [[ -n "$SECRET_ARN" ]]; then
  info "Retrieving AD credentials from Secrets Manager..."
  SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_ARN" \
    --region "$REGION" \
    --query 'SecretString' --output text)
  AD_USER=$(echo "$SECRET_JSON" | jq -r '.username')
  AD_PASSWORD=$(echo "$SECRET_JSON" | jq -r '.password')
  ok "Credentials retrieved (user: ${AD_USER})"
fi

# ---------------------------------------------------------------------------
# Resolve FSx for ONTAP management endpoint
# ---------------------------------------------------------------------------
info "Looking up FSx for ONTAP SVM details..."

# Get the file system ID from the SVM
SVM_INFO=$(aws fsx describe-storage-virtual-machines \
  --filters "Name=StorageVirtualMachineId,Values=${SVM_ID}" \
  --region "$REGION" --output json 2>/dev/null)

FS_ID=$(echo "$SVM_INFO" | jq -r '.StorageVirtualMachines[0].FileSystemId')
SVM_NAME=$(echo "$SVM_INFO" | jq -r '.StorageVirtualMachines[0].Name')

if [[ -z "$FS_ID" || "$FS_ID" == "null" ]]; then
  err "SVM ${SVM_ID} not found in region ${REGION}"
  exit 1
fi

ok "SVM: ${SVM_NAME} (${SVM_ID}) on file system ${FS_ID}"

# Get management endpoint
FS_INFO=$(aws fsx describe-file-systems \
  --file-system-ids "$FS_ID" \
  --region "$REGION" --output json 2>/dev/null)

MGMT_IP=$(echo "$FS_INFO" | jq -r '.FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]')

if [[ -z "$MGMT_IP" || "$MGMT_IP" == "null" ]]; then
  err "Could not determine management endpoint for file system ${FS_ID}"
  exit 1
fi

ok "Management endpoint: ${MGMT_IP}"

# ---------------------------------------------------------------------------
# Resolve ONTAP credentials (fsxadmin)
# ---------------------------------------------------------------------------
if [[ -n "$FSXN_SECRET_ARN" ]]; then
  info "Retrieving ONTAP admin credentials from Secrets Manager..."
  FSXN_SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "$FSXN_SECRET_ARN" \
    --region "$REGION" \
    --query 'SecretString' --output text)
  FSXN_USER=$(echo "$FSXN_SECRET_JSON" | jq -r '.username // "fsxadmin"')
  FSXN_PASSWORD=$(echo "$FSXN_SECRET_JSON" | jq -r '.password')
else
  FSXN_USER="fsxadmin"
  info "ONTAP admin user: fsxadmin (provide password or use --fsxn-secret)"
  if [[ -z "${FSXN_PASSWORD:-}" ]]; then
    read -s -p "  Enter fsxadmin password: " FSXN_PASSWORD
    echo ""
  fi
fi

# ---------------------------------------------------------------------------
# Derive CIFS server name
# ---------------------------------------------------------------------------
if [[ -z "$CIFS_SERVER" ]]; then
  # Use SVM name, uppercase, truncated to 15 chars, replace hyphens with empty
  CIFS_SERVER=$(echo "${SVM_NAME}" | tr '[:lower:]' '[:upper:]' | tr -d '-' | cut -c1-15)
fi

info "CIFS server name: ${CIFS_SERVER}"

# ---------------------------------------------------------------------------
# Build ONTAP REST API request
# ---------------------------------------------------------------------------
# Convert comma-separated DNS IPs to JSON array
DNS_ARRAY=$(echo "$DNS_IPS" | jq -R 'split(",") | map(gsub("\\s"; ""))')

PAYLOAD=$(jq -n \
  --arg name "$CIFS_SERVER" \
  --arg domain "$DOMAIN" \
  --arg user "$AD_USER" \
  --arg pass "$AD_PASSWORD" \
  --argjson dns "$DNS_ARRAY" \
  --arg svm "$SVM_NAME" \
  --arg ou "${OU:-}" \
  '{
    "name": $name,
    "ad_domain": {
      "fqdn": $domain,
      "user": $user,
      "password": $pass,
      "organizational_unit": (if $ou != "" then $ou else null end)
    },
    "dns": {
      "domains": [$domain],
      "servers": $dns
    },
    "svm": {
      "name": $svm
    }
  } | del(.ad_domain.organizational_unit | nulls)')

# ---------------------------------------------------------------------------
# Execute or dry-run
# ---------------------------------------------------------------------------
API_URL="https://${MGMT_IP}/api/protocols/cifs/services"

if [[ "$DRY_RUN" == "true" ]]; then
  warn "DRY RUN — would POST to: ${API_URL}"
  echo ""
  echo "Payload:"
  echo "$PAYLOAD" | jq '(.ad_domain.password) = "********"'
  echo ""
  info "To execute: remove --dry-run flag"
  exit 0
fi

info "Joining SVM '${SVM_NAME}' to AD domain '${DOMAIN}'..."
info "API: POST ${API_URL}"

HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -u "${FSXN_USER}:${FSXN_PASSWORD}" \
  -k \
  -d "$PAYLOAD")

HTTP_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')
HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -1)

# ---------------------------------------------------------------------------
# Handle response
# ---------------------------------------------------------------------------
if [[ "$HTTP_CODE" == "201" || "$HTTP_CODE" == "202" ]]; then
  ok "SVM successfully joined to AD domain '${DOMAIN}'"
  echo ""
  info "CIFS server: ${CIFS_SERVER}"
  info "Domain: ${DOMAIN}"
  info "DNS: ${DNS_IPS}"
  echo ""

  # If 202 (async job), show job UUID
  if [[ "$HTTP_CODE" == "202" ]]; then
    JOB_UUID=$(echo "$HTTP_BODY" | jq -r '.job.uuid // empty')
    if [[ -n "$JOB_UUID" ]]; then
      info "Async job submitted: ${JOB_UUID}"
      info "Monitor: curl -sk -u fsxadmin:*** https://${MGMT_IP}/api/cluster/jobs/${JOB_UUID}"
    fi
  fi

  echo ""
  info "Next steps:"
  echo "  1. Create an SMB share:"
  echo "     curl -sk -u fsxadmin:*** -X POST https://${MGMT_IP}/api/protocols/cifs/shares \\"
  echo "       -H 'Content-Type: application/json' \\"
  echo "       -d '{\"name\":\"edge_data\",\"path\":\"/vol_images\",\"svm\":{\"name\":\"${SVM_NAME}\"}}'"
  echo ""
  echo "  2. Test SMB mount from a domain-joined client:"
  echo "     net use Z: \\\\\\\\${CIFS_SERVER}.${DOMAIN}\\\\edge_data"
  echo ""
  exit 0
else
  err "AD join failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "Response:"
  echo "$HTTP_BODY" | jq . 2>/dev/null || echo "$HTTP_BODY"
  echo ""

  # Common error hints
  case "$HTTP_CODE" in
    401) err "Hint: Check fsxadmin credentials (--fsxn-secret or FSXN_PASSWORD env var)" ;;
    409) warn "Hint: CIFS server may already exist on this SVM. Check with:"
         echo "  curl -sk -u fsxadmin:*** https://${MGMT_IP}/api/protocols/cifs/services?svm.name=${SVM_NAME}" ;;
    *)   err "Hint: Verify DNS connectivity, AD credentials, and domain reachability from VPC" ;;
  esac
  exit 1
fi
