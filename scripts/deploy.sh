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

# Live authoring is fail-closed: with no passphrase the admin routes return 503.
# Generated if unset so a deploy is never accidentally wide open OR silently dead.
ADMIN_PASSPHRASE="${ADMIN_PASSPHRASE:-$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 20)}"

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
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND \
  --no-fail-on-empty-changeset \
  --resolve-s3 \
  --parameter-overrides \
    "Stage=$STAGE" \
    "BedrockModelId=$BEDROCK_MODEL_ID" \
    "BedrockFallbackModelId=$BEDROCK_FALLBACK_MODEL_ID" \
    "AdminPassphrase=$ADMIN_PASSPHRASE"

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

API_URL="$(stack_output ApiUrl)"
WS_URL="$(stack_output WebSocketUrl)"
STATE_MACHINE_ARN="$(stack_output StateMachineArn)"

[ -n "$API_URL" ] && [ "$API_URL" != "None" ] || { echo "Could not read ApiUrl from the stack."; exit 1; }
[ -n "$WS_URL" ] && [ "$WS_URL" != "None" ] || { echo "Could not read WebSocketUrl from the stack."; exit 1; }

step "Seeding the 5 challenges into DynamoDB"
AWS_REGION="$AWS_REGION" BREAKFIX_STORAGE=dynamodb \
  python3 "$ROOT/seed-data/author_challenges.py" --storage dynamodb

step "Smoke-testing the deployed API"
curl -fsS "$API_URL/challenges" > /tmp/breakfix-smoke.json
python3 - <<PY
import json
rows = json.load(open("/tmp/breakfix-smoke.json"))["challenges"]
print(f"  GET /challenges -> {len(rows)} published challenge(s)")
assert rows, "the deployed API returned no challenges - seeding did not land"
missing = [c["challenge_id"] for c in rows if not c.get("student_facing_summary")]
assert not missing, f"challenges missing a mission brief: {missing}"
print("  every challenge carries a mission brief")
PY
curl -fsS "$API_URL/stats" | head -c 200; echo

step "Verifying Bedrock and the state machine are actually reachable"
# Makes one real call per agent. Better to find out here than on stage.
AWS_REGION="$AWS_REGION" \
BEDROCK_MODEL_ID="$BEDROCK_MODEL_ID" \
BEDROCK_FALLBACK_MODEL_ID="$BEDROCK_FALLBACK_MODEL_ID" \
STATE_MACHINE_ARN="$STATE_MACHINE_ARN" \
  python3 "$ROOT/scripts/verify_aws.py" --api-url "$API_URL" || {
    echo
    echo "  !! Verification reported problems. The stack is deployed, but read the"
    echo "     output above before demoing - some part is running on a fallback."
  }

# Both URLs must be baked in at build time. Missing VITE_WS_URL was silently
# leaving the whole real-time layer dead on a deployed frontend, and a ws://
# URL is blocked as mixed content on an HTTPS Amplify domain anyway.
cat > "$ROOT/frontend/.env.production" <<ENV
VITE_API_BASE_URL=$API_URL
VITE_WS_URL=$WS_URL
ENV

printf '\n\033[1;32mBackend deployed.\033[0m\n'
echo "  API base URL:  $API_URL"
echo "  WebSocket URL: $WS_URL"
echo "  State machine: $STATE_MACHINE_ARN"
echo
printf '\033[1;33m  Admin passphrase: %s\033[0m\n' "$ADMIN_PASSPHRASE"
echo "  (needed for /admin — store it somewhere, it is not echoed by CloudFormation)"
echo
echo "Wrote frontend/.env.production with BOTH urls."
echo "Next: ./scripts/deploy_frontend.sh"
