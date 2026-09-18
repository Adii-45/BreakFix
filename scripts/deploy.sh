#!/usr/bin/env bash
# Deploy the BreakFix backend to AWS and seed the challenge data.
#
# Prerequisites (see README "Deploying"):
#   * AWS CLI v2 configured with credentials  (aws configure)
#   * AWS SAM CLI                             (brew install aws-sam-cli)
#   * Bedrock model access enabled for the model id you pass in, in this region
#
# Usage:
#   ./scripts/deploy.sh                       # deploy to us-east-1, stage prod
#   AWS_REGION=ap-south-1 ./scripts/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_NAME="${STACK_NAME:-breakfix}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STAGE="${STAGE:-prod}"
BEDROCK_MODEL_ID="${BEDROCK_MODEL_ID:-anthropic.claude-opus-5}"
BEDROCK_FALLBACK_MODEL_ID="${BEDROCK_FALLBACK_MODEL_ID:-us.anthropic.claude-opus-5}"

step() { printf '\n\033[1;33m==> %s\033[0m\n' "$1"; }

command -v aws >/dev/null || { echo "aws CLI not found. Install AWS CLI v2 first."; exit 1; }
command -v sam >/dev/null || { echo "sam CLI not found. Install AWS SAM CLI first."; exit 1; }

step "Checking AWS credentials"
aws sts get-caller-identity --output table

step "Building the Lambda bundle"
sam build --template "$ROOT/infra/template.yaml" --build-dir "$ROOT/.aws-sam/build"

step "Deploying stack '$STACK_NAME' to $AWS_REGION"
sam deploy \
  --template-file "$ROOT/.aws-sam/build/template.yaml" \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --resolve-s3 \
  --parameter-overrides \
    "Stage=$STAGE" \
    "BedrockModelId=$BEDROCK_MODEL_ID" \
    "BedrockFallbackModelId=$BEDROCK_FALLBACK_MODEL_ID"

API_URL="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)"

step "Seeding the 5 challenges into DynamoDB"
AWS_REGION="$AWS_REGION" BREAKFIX_STORAGE=dynamodb \
  python3 "$ROOT/seed-data/author_challenges.py" --storage dynamodb

step "Smoke-testing the deployed API"
curl -fsS "$API_URL/challenges" | head -c 400; echo

printf '\n\033[1;32mBackend deployed.\033[0m\n'
echo "  API base URL: $API_URL"
echo
echo "Next: point the frontend at it and deploy to Amplify Hosting."
echo "  echo \"VITE_API_BASE_URL=$API_URL\" > $ROOT/frontend/.env.production"
echo "  (then connect the repo in the Amplify console, or run ./scripts/deploy_frontend.sh)"

echo "VITE_API_BASE_URL=$API_URL" > "$ROOT/frontend/.env.production"
echo
echo "Wrote frontend/.env.production for you."
