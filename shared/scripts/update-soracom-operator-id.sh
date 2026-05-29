#!/bin/bash
# Update CloudFormation stack with SORACOM Operator ID
# Usage: ./update-soracom-operator-id.sh <OPERATOR_ID>
#
# Get your Operator ID from:
#   https://console.soracom.io → Dashboard → top-right corner
#
# Example: ./update-soracom-operator-id.sh OP0012345678

set -euo pipefail

OPERATOR_ID="${1:-}"
STACK_NAME="edge-to-cloud-ai-poc"
REGION="ap-northeast-1"

if [ -z "$OPERATOR_ID" ]; then
    echo "Usage: $0 <SORACOM_OPERATOR_ID>"
    echo ""
    echo "Get your Operator ID from:"
    echo "  https://console.soracom.io → Dashboard → top-right corner"
    echo ""
    echo "Format: OP followed by 10 digits (e.g., OP0012345678)"
    exit 1
fi

echo "Updating stack '${STACK_NAME}' with SORACOM Operator ID: ${OPERATOR_ID}"

aws cloudformation update-stack \
    --stack-name "${STACK_NAME}" \
    --use-previous-template \
    --parameters \
        "ParameterKey=Environment,UsePreviousValue=true" \
        "ParameterKey=SoracomOperatorId,ParameterValue=${OPERATOR_ID}" \
        "ParameterKey=AlertEmail,UsePreviousValue=true" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}"

echo "Stack update initiated. Waiting for completion..."

aws cloudformation wait stack-update-complete \
    --stack-name "${STACK_NAME}" \
    --region "${REGION}"

echo "✅ Stack updated successfully."
echo ""
echo "Next steps:"
echo "  1. Go to SORACOM Console → SIM Groups → Funnel settings"
echo "  2. Set Role ARN: $(aws cloudformation describe-stacks --stack-name ${STACK_NAME} --query 'Stacks[0].Outputs[?OutputKey==`SoracomIngestionRoleArn`].OutputValue' --output text --region ${REGION})"
echo "  3. Set External ID: ${OPERATOR_ID}"
echo "  4. Set Stream name: edge-to-cloud-poc-ingestion"
echo "  5. Set Region: ${REGION}"
