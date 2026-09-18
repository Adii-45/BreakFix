#!/usr/bin/env bash
# Build the frontend and publish it to AWS Amplify Hosting via manual deploy.
#
# The alternative (and the one the PRD assumes for the demo) is connecting this
# GitHub repo in the Amplify console, which uses amplify.yml at the repo root and
# redeploys on every push. This script is the no-console path.
#
# Usage:
#   ./scripts/deploy_frontend.sh            # creates/uses an app named "breakfix"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="${AMPLIFY_APP_NAME:-breakfix}"
BRANCH="${AMPLIFY_BRANCH:-main}"
AWS_REGION="${AWS_REGION:-us-east-1}"

step() { printf '\n\033[1;33m==> %s\033[0m\n' "$1"; }

[ -f "$ROOT/frontend/.env.production" ] || {
  echo "frontend/.env.production is missing. Run ./scripts/deploy.sh first."; exit 1; }

step "Building the frontend"
(cd "$ROOT/frontend" && npm ci && npm run build)

step "Finding or creating the Amplify app"
APP_ID="$(aws amplify list-apps --region "$AWS_REGION" \
  --query "apps[?name=='$APP_NAME'].appId | [0]" --output text)"
if [ "$APP_ID" = "None" ] || [ -z "$APP_ID" ]; then
  APP_ID="$(aws amplify create-app --name "$APP_NAME" --region "$AWS_REGION" \
    --query 'app.appId' --output text)"
  echo "Created Amplify app $APP_ID"
fi

aws amplify get-branch --app-id "$APP_ID" --branch-name "$BRANCH" --region "$AWS_REGION" >/dev/null 2>&1 \
  || aws amplify create-branch --app-id "$APP_ID" --branch-name "$BRANCH" --region "$AWS_REGION" >/dev/null

step "Configuring SPA rewrites"
# The app uses client-side routing, so every unknown path must serve index.html
# or a deep link (e.g. /leaderboard) 404s on a hard refresh.
aws amplify update-app --app-id "$APP_ID" --region "$AWS_REGION" \
  --custom-rules '[{"source":"</^[^.]+$|\\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>","target":"/index.html","status":"200"}]' \
  >/dev/null

step "Uploading the build"
ZIP="$(mktemp -d)/site.zip"
(cd "$ROOT/frontend/dist" && zip -qr "$ZIP" .)

READ=$(aws amplify create-deployment --app-id "$APP_ID" --branch-name "$BRANCH" \
  --region "$AWS_REGION" --output json)
JOB_ID=$(echo "$READ" | python3 -c 'import json,sys; print(json.load(sys.stdin)["jobId"])')
ZIP_URL=$(echo "$READ" | python3 -c 'import json,sys; print(json.load(sys.stdin)["zipUploadUrl"])')
curl -fsS -X PUT -T "$ZIP" "$ZIP_URL" >/dev/null
aws amplify start-deployment --app-id "$APP_ID" --branch-name "$BRANCH" \
  --job-id "$JOB_ID" --region "$AWS_REGION" >/dev/null

step "Waiting for the deployment"
for _ in $(seq 1 60); do
  STATUS="$(aws amplify get-job --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" \
    --region "$AWS_REGION" --query 'job.summary.status' --output text)"
  [ "$STATUS" = "SUCCEED" ] && break
  [ "$STATUS" = "FAILED" ] && { echo "Amplify deployment failed."; exit 1; }
  sleep 5
done

DOMAIN="$(aws amplify get-app --app-id "$APP_ID" --region "$AWS_REGION" \
  --query 'app.defaultDomain' --output text)"
printf '\n\033[1;32mFrontend live:\033[0m https://%s.%s\n' "$BRANCH" "$DOMAIN"
echo
echo "Now lock CORS down to that origin:"
echo "  CorsAllowOrigin=https://$BRANCH.$DOMAIN  ->  redeploy with ./scripts/deploy.sh"
