#!/usr/bin/env bash
# =============================================================================
# teardown.sh — Delete the stacks this repository deploys, in an order that works
#
# Deletion is not the reverse of creation by convenience; it is forced. All three
# use-case stacks resolve `Fn::ImportValue` against exports of the shared ingestion
# stack (`${SharedStackName}-BucketName`, `-AlertTopicArn`, `-ImageAnalyzerRoleArn`),
# and CloudFormation refuses to delete a stack whose exports are still imported. Ask
# for the shared stack first and it fails with an export-in-use error after having
# already spent several minutes.
#
# The order below is therefore: use-case stacks, then iot-ingestion, then the shared
# ingestion stack, then FSx for ONTAP. Only the third step is a hard dependency;
# iot-ingestion imports nothing and FSx for ONTAP has no dependents in this
# repository, so those two are ordered by cost, largest last.
#
# Usage:
#   ./scripts/teardown.sh                    # Show the plan. Deletes nothing.
#   ./scripts/teardown.sh --confirm          # Delete
#   ./scripts/teardown.sh --confirm --keep-fsxn
#   ./scripts/teardown.sh --region us-west-2 --environment dev
#
# Exit codes:
#   0 — plan printed, or every present stack deleted
#   1 — a deletion failed
#   2 — script usage error
#
# WHAT SURVIVES THIS SCRIPT
#   The data-lake S3 bucket carries `DeletionPolicy: Retain` in
#   cloud/ingestion/template.yaml, so deleting the shared stack leaves it behind
#   holding its objects. Its name is derived, not random —
#   `edge-to-cloud-ai-<environment>-<account-id>` — so it is also what makes a later
#   redeploy of the same environment fail: CloudFormation tries to create a bucket
#   that already exists and rolls the stack back. This script prints the resolved
#   name and the command to remove it, and does not remove it for you: emptying a
#   bucket is the one step here that destroys data CloudFormation was told to keep.
# =============================================================================
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-northeast-1}"
ENVIRONMENT="${ENVIRONMENT:-poc}"

# Overridable individually; defaults match the names used throughout docs/.
FSXN_STACK="${FSXN_STACK:-edge-to-cloud-fsxn-poc}"
SHARED_STACK="${SHARED_STACK:-edge-to-cloud-ai-poc}"
IOT_INGESTION_STACK="${IOT_INGESTION_STACK:-edge-to-cloud-iot-ingestion-poc}"
USECASE_STACKS=(
  "${VISUAL_INSPECTION_STACK:-edge-to-cloud-visual-inspection-poc}"
  "${PRINT_QUALITY_STACK:-edge-to-cloud-print-quality-poc}"
  "${TELEMETRY_STACK:-edge-to-cloud-telemetry-poc}"
)

CONFIRMED=false
KEEP_FSXN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm)     CONFIRMED=true; shift ;;
    --keep-fsxn)   KEEP_FSXN=true; shift ;;
    --region)      AWS_REGION="${2:?--region needs a value}"; shift 2 ;;
    --environment) ENVIRONMENT="${2:?--environment needs a value}"; shift 2 ;;
    -h|--help)
      sed -n '2,37p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Run '$0 --help' for usage." >&2
      exit 2
      ;;
  esac
done

aws_cfn() { aws cloudformation "$@" --region "$AWS_REGION"; }

stack_exists() {
  aws_cfn describe-stacks --stack-name "$1" >/dev/null 2>&1
}

# --- Work out what is actually there ----------------------------------------
present=()
absent=()
for stack in "${USECASE_STACKS[@]}" "$IOT_INGESTION_STACK" "$SHARED_STACK" "$FSXN_STACK"; do
  if [[ "$stack" == "$FSXN_STACK" ]] && [[ "$KEEP_FSXN" == true ]]; then
    continue
  fi
  if stack_exists "$stack"; then present+=("$stack"); else absent+=("$stack"); fi
done

echo "Region:      $AWS_REGION"
echo "Environment: $ENVIRONMENT"
echo
if [[ ${#present[@]} -eq 0 ]]; then
  echo "Nothing to delete. None of the expected stacks exist in this region."
  echo "If you deployed under different names, set FSXN_STACK, SHARED_STACK,"
  echo "IOT_INGESTION_STACK, VISUAL_INSPECTION_STACK, PRINT_QUALITY_STACK or"
  echo "TELEMETRY_STACK and run again."
  exit 0
fi

echo "Deletion order:"
order=1
for stack in "${USECASE_STACKS[@]}" "$IOT_INGESTION_STACK" "$SHARED_STACK" "$FSXN_STACK"; do
  for candidate in "${present[@]}"; do
    if [[ "$candidate" == "$stack" ]]; then
      printf '  %d. %s\n' "$order" "$stack"
      order=$((order + 1))
    fi
  done
done
if [[ ${#absent[@]} -gt 0 ]]; then
  echo
  echo "Not present, skipping: ${absent[*]}"
fi

account_id="$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo '<account-id>')"
retained_bucket="edge-to-cloud-ai-${ENVIRONMENT}-${account_id}"

if [[ "$CONFIRMED" != true ]]; then
  cat <<EOF

This was a plan. Nothing has been deleted.
Re-run with --confirm to carry it out:

  $0 --confirm

EOF
  exit 0
fi

echo
read -r -p "Type 'DELETE' to delete ${#present[@]} stack(s) in $AWS_REGION: " reply
if [[ "$reply" != "DELETE" ]]; then
  echo "Aborted; nothing was deleted."
  exit 0
fi

failed=()

# --- Use-case stacks: independent of each other, so delete concurrently ------
usecases_present=()
for stack in "${USECASE_STACKS[@]}"; do
  for candidate in "${present[@]}"; do
    [[ "$candidate" == "$stack" ]] && usecases_present+=("$stack")
  done
done

if [[ ${#usecases_present[@]} -gt 0 ]]; then
  echo
  echo "==> Use-case stacks"
  for stack in "${usecases_present[@]}"; do
    echo "    requesting deletion: $stack"
    aws_cfn delete-stack --stack-name "$stack"
  done
  for stack in "${usecases_present[@]}"; do
    echo "    waiting: $stack"
    if ! aws_cfn wait stack-delete-complete --stack-name "$stack"; then
      echo "    FAILED: $stack" >&2
      failed+=("$stack")
    fi
  done
fi

# --- The rest: strictly one at a time ---------------------------------------
for stack in "$IOT_INGESTION_STACK" "$SHARED_STACK" "$FSXN_STACK"; do
  for candidate in "${present[@]}"; do
    [[ "$candidate" != "$stack" ]] && continue
    echo
    echo "==> $stack"
    if [[ ${#failed[@]} -gt 0 ]] && [[ "$stack" == "$SHARED_STACK" ]]; then
      echo "    skipped: a use-case stack above did not delete, so its imports of" >&2
      echo "    this stack's exports are still live and this deletion would fail." >&2
      failed+=("$stack (skipped)")
      continue
    fi
    aws_cfn delete-stack --stack-name "$stack"
    echo "    waiting..."
    if ! aws_cfn wait stack-delete-complete --stack-name "$stack"; then
      echo "    FAILED: $stack" >&2
      failed+=("$stack")
    fi
  done
done

echo
if [[ ${#failed[@]} -gt 0 ]]; then
  echo "Stacks that did not delete: ${failed[*]}" >&2
  echo "Check the reason with:" >&2
  echo "  aws cloudformation describe-stack-events --region $AWS_REGION \\" >&2
  echo "    --stack-name <name> --max-items 20" >&2
  echo "A stack left in DELETE_FAILED usually holds a non-empty S3 bucket or a" >&2
  echo "log group another stack still writes to." >&2
  exit 1
fi

cat <<EOF
All requested stacks are deleted.

Still present, on purpose:
  s3://${retained_bucket}
    Retained by DeletionPolicy in cloud/ingestion/template.yaml, with its objects.
    It will block a redeploy of environment '${ENVIRONMENT}' under the same name.
    To remove it and everything in it:

      aws s3 rb s3://${retained_bucket} --force

Check for anything else still billable in this region:
  aws fsx describe-file-systems --region ${AWS_REGION} \\
    --query 'FileSystems[].FileSystemId'
  aws logs describe-log-groups --region ${AWS_REGION} \\
    --log-group-name-prefix /aws/lambda/edge-to-cloud \\
    --query 'logGroups[].logGroupName'
EOF
