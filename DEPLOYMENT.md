# Deploying BreakFix

> **Status: not yet deployed.** Nothing in this project has made a real AWS call.
> Everything below is written, validated and wired, but the first run of
> `deploy.sh` will be the first time this stack touches AWS. Budget an hour, not
> five minutes, and do it before demo day — not on demo day.

## What you need that the repo cannot provide

| Thing | Why | Where |
|---|---|---|
| AWS account + credentials | Everything | `aws configure` |
| AWS CLI v2 | `deploy.sh` reads stack outputs | `brew install awscli` |
| AWS SAM CLI | Builds and deploys the stack | `brew install aws-sam-cli` |
| **Bedrock model access** | Both live agents | Bedrock console → *Model access* → enable the model, **in the same region you deploy to** |
| A region choice | Bedrock model availability varies | `us-east-1` is the safest default |

**The Bedrock model-access step is the one people forget.** Without it the stack
deploys fine, the app works fine, and every result quietly comes from the
deterministic fallback scorer — which is exactly the thing the pitch says it
does not do. `verify_aws.py` exists to catch that.

## Order of operations

```bash
# 0. Confirm credentials and Bedrock BEFORE deploying anything.
export AWS_REGION=us-east-1
python scripts/verify_aws.py --only bedrock
```

If that reports `FAIL` on *Bedrock reachable*, stop and fix model access first.
Everything else is wasted effort until it passes.

```bash
# 1. Backend: tables, Lambdas, REST API, WebSocket API, Step Functions,
#    EventBridge bus, and the challenge seeding.
./scripts/deploy.sh

# 2. Frontend: build with BOTH urls baked in, publish to Amplify Hosting,
#    and install the SPA rewrite so deep links work.
./scripts/deploy_frontend.sh
```

`deploy.sh` prints the API URL, the WebSocket URL, the state machine ARN and a
**generated admin passphrase** — save that passphrase, CloudFormation will not
show it again (`NoEcho`).

## After the first deploy

```bash
# Full verification against the real, deployed stack.
STATE_MACHINE_ARN=<printed by deploy.sh> \
WEBSOCKET_URL=<printed by deploy.sh> \
  python scripts/verify_aws.py --api-url <printed by deploy.sh>
```

This makes one real Bedrock call per agent, starts a **real Step Functions
execution** against `shlex.quote`, submits a real fix through the deployed
Lambda + sandbox, and handshakes the WebSocket. It fails loudly rather than
falling back, so a green run is meaningful.

Then lock CORS down to the Amplify origin:

```bash
CorsAllowOrigin=https://main.<app-id>.amplifyapp.com ./scripts/deploy.sh
```

## Things that behave differently once deployed

| | Local | Deployed |
|---|---|---|
| Evaluator feedback | deterministic fallback (labelled in the UI) | Bedrock, if model access is on |
| Bug injection (live authoring) | `mutation-fallback` | Bug Injector Agent |
| Test execution | in-process subprocess | separate zero-IAM Lambda |
| Broadcast trigger | synthetic stream record | real DynamoDB Streams |
| Authoring orchestration | threaded local runner | real Step Functions |
| System status panel | "unavailable" | real CloudWatch numbers |
| `RLIMIT_AS` memory cap | skipped (macOS refuses it) | applied |

That last row matters: the sandbox's memory limit is genuinely inactive on a
Mac and genuinely active on Lambda.

## Known deployment risks

1. **Cold starts.** First submission after a quiet period pays a Lambda cold
   start plus a Bedrock call. Pre-warm by submitting once before the demo.
2. **Bedrock throttling.** A burst of submissions can hit account limits. The
   evaluator degrades to the fallback and the UI labels it; correctness is
   unaffected.
3. **`sam build` needs Python 3.12** available locally to build the bundle.
4. **Step Functions has never run in AWS.** The local orchestrator drove the
   identical step functions, but `DescribeExecution` history projection and the
   ASL `Catch`/`ResultSelector` wiring are unproven. Run `verify_aws.py` and
   watch a real execution before relying on it in a demo.
