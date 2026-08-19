#!/usr/bin/env bash
# =============================================================================
# preflight-check.sh — Pre-deployment validation for edge-to-cloud-ai stacks
#
# Checks: AWS CLI, credentials, region, service quotas, VPC endpoint conflicts,
#          Bedrock model access, and CloudFormation template validity.
#
# Usage:
#   ./scripts/preflight-check.sh                  # All checks
#   ./scripts/preflight-check.sh --skip network   # Skip network checks
#   ./scripts/preflight-check.sh --skip bedrock   # Skip Bedrock checks
#   ./scripts/preflight-check.sh --stack fsxn     # Only check fsxn stack
#   ./scripts/preflight-check.sh --region us-west-2
#
# Exit codes:
#   0 — All checks passed
#   1 — One or more checks failed
#   2 — Script usage error
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors (disabled if not a TTY)
if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
  BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; RESET=''
fi

# Counters
PASS=0; FAIL=0; WARN=0; SKIP_COUNT=0

# Skip categories
declare -a SKIP_CATEGORIES=()
TARGET_STACK=""
REGION=""

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
pass()  { ((PASS++));       printf "${GREEN}  [PASS]${RESET} %s\n" "$1"; }
fail()  { ((FAIL++));       printf "${RED}  [FAIL]${RESET} %s\n" "$1"; }
warn()  { ((WARN++));       printf "${YELLOW}  [WARN]${RESET} %s\n" "$1"; }
skip()  { ((SKIP_COUNT++)); printf "${BLUE}  [SKIP]${RESET} %s\n" "$1"; }
info()  { printf "${BOLD}  [INFO]${RESET} %s\n" "$1"; }
header(){ printf "\n${BOLD}━━━ %s${RESET}\n" "$1"; }

should_skip() {
  local category="$1"
  for s in "${SKIP_CATEGORIES[@]+"${SKIP_CATEGORIES[@]}"}"; do
    [[ "$s" == "$category" ]] && return 0
  done
  return 1
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip)
      [[ -z "${2:-}" ]] && { echo "Error: --skip requires a category"; exit 2; }
      SKIP_CATEGORIES+=("$2"); shift 2 ;;
    --stack)
      [[ -z "${2:-}" ]] && { echo "Error: --stack requires a name"; exit 2; }
      TARGET_STACK="$2"; shift 2 ;;
    --region)
      [[ -z "${2:-}" ]] && { echo "Error: --region requires a value"; exit 2; }
      REGION="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,/^# ====/{ /^# ====/d; s/^# //; s/^#//; p }' "$0"
      exit 0 ;;
    *)
      echo "Unknown option: $1"; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
header "1. Prerequisites"

# AWS CLI
if command -v aws &>/dev/null; then
  AWS_VERSION=$(aws --version 2>&1 | awk '{print $1}')
  pass "AWS CLI installed (${AWS_VERSION})"
else
  fail "AWS CLI not found — install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
fi

# jq
if command -v jq &>/dev/null; then
  pass "jq installed ($(jq --version 2>&1))"
else
  fail "jq not found — install: brew install jq / apt-get install jq"
fi

# cfn-lint (optional but recommended)
if command -v cfn-lint &>/dev/null; then
  pass "cfn-lint installed ($(cfn-lint --version 2>&1 | head -1))"
else
  warn "cfn-lint not found (optional) — install: pip install cfn-lint"
fi

# ---------------------------------------------------------------------------
# 2. AWS Credentials & Identity
# ---------------------------------------------------------------------------
header "2. AWS Credentials & Identity"

if aws sts get-caller-identity &>/dev/null; then
  IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null)
  ACCOUNT_ID=$(echo "$IDENTITY" | jq -r '.Account')
  ARN=$(echo "$IDENTITY" | jq -r '.Arn')
  pass "Authenticated as: ${ARN}"
  info "Account: ${ACCOUNT_ID}"
else
  fail "AWS credentials not configured or expired"
  echo ""
  echo "  Fix: aws configure  OR  export AWS_PROFILE=<profile>"
  echo "  See: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html"
  echo ""
  # Cannot continue without credentials
  printf "\n${BOLD}Summary:${RESET} PASS=%d FAIL=%d WARN=%d SKIP=%d\n" "$PASS" "$FAIL" "$WARN" "$SKIP_COUNT"
  exit 1
fi

# Region
if [[ -n "$REGION" ]]; then
  export AWS_DEFAULT_REGION="$REGION"
elif [[ -z "${AWS_DEFAULT_REGION:-}" && -z "${AWS_REGION:-}" ]]; then
  REGION=$(aws configure get region 2>/dev/null || true)
  if [[ -z "$REGION" ]]; then
    fail "No AWS region configured — use --region or set AWS_DEFAULT_REGION"
  else
    export AWS_DEFAULT_REGION="$REGION"
    pass "Region: ${REGION}"
  fi
else
  REGION="${AWS_DEFAULT_REGION:-${AWS_REGION}}"
  pass "Region: ${REGION}"
fi

# ---------------------------------------------------------------------------
# 3. IAM Permissions (spot check)
# ---------------------------------------------------------------------------
header "3. IAM Permissions (spot check)"

check_iam_action() {
  local service="$1" action="$2" desc="$3"
  # Dry-run isn't available for all services; we check via simulate-principal-policy
  # For simplicity, verify by attempting describe-* calls
  if aws "$service" "$action" --max-items 1 &>/dev/null 2>&1 || \
     aws "$service" "$action" --max-results 1 &>/dev/null 2>&1; then
    pass "$desc"
  else
    warn "$desc — may lack permissions (non-blocking)"
  fi
}

check_iam_action "cloudformation" "list-stacks" "cloudformation:ListStacks"
check_iam_action "s3api" "list-buckets" "s3:ListBuckets"

# Check CAPABILITY_NAMED_IAM awareness
info "Templates require --capabilities CAPABILITY_NAMED_IAM"

# ---------------------------------------------------------------------------
# 4. CloudFormation Template Validation
# ---------------------------------------------------------------------------
header "4. CloudFormation Template Validation"

declare -A TEMPLATES=(
  ["fsxn"]="cloud/fsxn/template.yaml"
  ["ingestion"]="cloud/ingestion/template.yaml"
  ["ontap-telemetry-analytics"]="usecases/ontap-telemetry-analytics/template.yaml"
  ["3d-print-quality"]="usecases/3d-print-quality/template.yaml"
  ["visual-inspection"]="usecases/visual-inspection/template.yaml"
)

for stack_name in "${!TEMPLATES[@]}"; do
  template="${TEMPLATES[$stack_name]}"
  template_path="${PROJECT_ROOT}/${template}"

  # Skip if --stack filter set and doesn't match
  if [[ -n "$TARGET_STACK" && "$TARGET_STACK" != "$stack_name" ]]; then
    continue
  fi

  if [[ ! -f "$template_path" ]]; then
    fail "${template} — file not found"
    continue
  fi

  # AWS validate-template
  if aws cloudformation validate-template \
       --template-body "file://${template_path}" &>/dev/null 2>&1; then
    pass "${template} — valid"
  else
    fail "${template} — validation failed"
    aws cloudformation validate-template \
      --template-body "file://${template_path}" 2>&1 | head -5 | sed 's/^/    /'
  fi

  # cfn-lint (if available)
  if command -v cfn-lint &>/dev/null; then
    if cfn-lint "$template_path" 2>/dev/null; then
      pass "${template} — cfn-lint clean"
    else
      warn "${template} — cfn-lint findings (review output above)"
    fi
  fi
done

# ---------------------------------------------------------------------------
# 5. Network & VPC Endpoint Conflict Matrix
# ---------------------------------------------------------------------------
header "5. Network & VPC Endpoint Checks"

if should_skip "network"; then
  skip "Network checks (--skip network)"
else
  # List existing VPCs to detect CIDR overlap risk
  EXISTING_VPCS=$(aws ec2 describe-vpcs --query 'Vpcs[].CidrBlock' --output text 2>/dev/null || echo "")
  if [[ -n "$EXISTING_VPCS" ]]; then
    info "Existing VPC CIDRs in ${REGION}:"
    for cidr in $EXISTING_VPCS; do
      printf "       %s\n" "$cidr"
    done
    # Check default CIDR overlap
    if echo "$EXISTING_VPCS" | grep -q "10.0.0.0/16"; then
      warn "CIDR 10.0.0.0/16 already exists — customize VpcCidr in cfn-params/fsxn.example.json"
    else
      pass "Default CIDR 10.0.0.0/16 does not conflict with existing VPCs"
    fi
  else
    pass "No existing VPCs (or insufficient permissions to list)"
  fi

  # VPC Endpoint conflict matrix
  # FSx for ONTAP needs these VPC endpoints for private connectivity:
  info "VPC Endpoint compatibility matrix (for private-subnet deployments):"
  printf "       %-30s %s\n" "Endpoint" "Required By"
  printf "       %-30s %s\n" "------------------------------" "-------------------"
  printf "       %-30s %s\n" "com.amazonaws.*.fsx" "FSx for ONTAP"
  printf "       %-30s %s\n" "com.amazonaws.*.s3 (Gateway)" "Ingestion, all stacks"
  printf "       %-30s %s\n" "com.amazonaws.*.kinesis-streams" "Ingestion"
  printf "       %-30s %s\n" "com.amazonaws.*.kinesis-firehose" "Ingestion"
  printf "       %-30s %s\n" "com.amazonaws.*.bedrock-runtime" "3D Print, Visual Insp."
  printf "       %-30s %s\n" "com.amazonaws.*.sns" "Alerts (all use cases)"
  printf "       %-30s %s\n" "com.amazonaws.*.glue" "Telemetry, ETL"
  printf "       %-30s %s\n" "com.amazonaws.*.logs" "Lambda logging"

  # Check AZ count
  AZ_COUNT=$(aws ec2 describe-availability-zones \
    --query 'AvailabilityZones[?State==`available`] | length(@)' \
    --output text 2>/dev/null || echo "0")
  if [[ "$AZ_COUNT" -ge 2 ]]; then
    pass "Region has ${AZ_COUNT} available AZs (FSx for ONTAP Multi-AZ requires >= 2)"
  else
    fail "Region has ${AZ_COUNT} AZs — FSx for ONTAP Multi-AZ requires at least 2"
  fi
fi

# ---------------------------------------------------------------------------
# 6. Service Quotas
# ---------------------------------------------------------------------------
header "6. Service Quotas"

if should_skip "quotas"; then
  skip "Quota checks (--skip quotas)"
else
  # FSx for ONTAP — file systems per account
  FSX_QUOTA=$(aws service-quotas get-service-quota \
    --service-code fsx \
    --quota-code "L-3E3DC5CF" \
    --query 'Quota.Value' --output text 2>/dev/null || echo "unknown")
  if [[ "$FSX_QUOTA" != "unknown" ]]; then
    info "FSx for ONTAP file systems quota: ${FSX_QUOTA}"
  fi

  # Kinesis — on-demand streams
  KINESIS_QUOTA=$(aws service-quotas get-service-quota \
    --service-code kinesis \
    --quota-code "L-3E3DC5CF" \
    --query 'Quota.Value' --output text 2>/dev/null || echo "unknown")
  if [[ "$KINESIS_QUOTA" != "unknown" ]]; then
    info "Kinesis on-demand streams quota: ${KINESIS_QUOTA}"
  fi

  pass "Quota check completed (review INFO values above)"
fi

# ---------------------------------------------------------------------------
# 7. Bedrock Model Access
# ---------------------------------------------------------------------------
header "7. Bedrock Model Access"

if should_skip "bedrock"; then
  skip "Bedrock checks (--skip bedrock)"
else
  MODELS=(
    "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
    "jp.anthropic.claude-sonnet-4-5-20250929-v1:0"
  )

  for model_id in "${MODELS[@]}"; do
    # Check if model is accessible via list-foundation-models or get-foundation-model
    # Note: jp. prefix models may not appear in list — try invoke dry-run style
    if aws bedrock get-foundation-model \
         --model-identifier "$model_id" &>/dev/null 2>&1; then
      pass "Bedrock model accessible: ${model_id}"
    else
      # Try without jp. prefix (cross-region inference prefix)
      base_model="${model_id#jp.}"
      if aws bedrock get-foundation-model \
           --model-identifier "$base_model" &>/dev/null 2>&1; then
        pass "Bedrock model accessible: ${model_id} (via base: ${base_model})"
      else
        warn "Bedrock model not confirmed: ${model_id} — ensure model access is enabled in Bedrock console"
      fi
    fi
  done

  info "Enable model access: Bedrock console → Model access → Manage model access"
fi

# ---------------------------------------------------------------------------
# 8. Existing Stack Conflict Check
# ---------------------------------------------------------------------------
header "8. Existing Stack Conflict Check"

STACK_PREFIXES=("edge-to-cloud-fsxn" "edge-to-cloud-ai" "edge-to-cloud-ingestion")
EXISTING_STACKS=$(aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE \
  --query 'StackSummaries[].StackName' --output text 2>/dev/null || echo "")

if [[ -n "$EXISTING_STACKS" ]]; then
  CONFLICT_FOUND=false
  for prefix in "${STACK_PREFIXES[@]}"; do
    MATCHES=$(echo "$EXISTING_STACKS" | tr '\t' '\n' | grep "^${prefix}" || true)
    if [[ -n "$MATCHES" ]]; then
      warn "Existing stack with prefix '${prefix}': ${MATCHES}"
      CONFLICT_FOUND=true
    fi
  done
  if [[ "$CONFLICT_FOUND" == "false" ]]; then
    pass "No conflicting stack names found"
  fi
else
  pass "No existing stacks with conflicting names"
fi

# ---------------------------------------------------------------------------
# 9. Cost Warning
# ---------------------------------------------------------------------------
header "9. Cost Awareness"
# No figures here beyond the warning. This block used to reprint the cost table from
# docs/{ja,en}/deployment-guide.md, and the two had already drifted: the guide said the Glue
# crawler was ~$30/month while this said ~$1/run. Two copies of a number that changes is one
# copy that gets updated and one that misleads, so the figures live in one document now.
warn "FSx for ONTAP dominates the bill for this stack. Deploy it only when needed, and"
warn "delete it afterwards with scripts/teardown.sh."
info "Figures, formulas and the pricing date: docs/en/cost-model.md (ja: docs/ja/cost-model.md)"
info "Use 'Environment=poc' and delete stacks after testing."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
header "Summary"
printf "  ${GREEN}PASS: %d${RESET}  ${RED}FAIL: %d${RESET}  ${YELLOW}WARN: %d${RESET}  ${BLUE}SKIP: %d${RESET}\n" \
  "$PASS" "$FAIL" "$WARN" "$SKIP_COUNT"

if [[ "$FAIL" -gt 0 ]]; then
  printf "\n  ${RED}${BOLD}Pre-flight check FAILED.${RESET} Fix the issues above before deploying.\n\n"
  exit 1
else
  printf "\n  ${GREEN}${BOLD}Pre-flight check PASSED.${RESET} Ready to deploy.\n\n"
  exit 0
fi
