# BreakFix

**An AI-judged debugging challenge platform.** A real function from a real
open-source repository is seeded with a plausible bug by an AI agent. You have to
find and fix it against a countdown. Hidden unit tests then *actually execute*
your submission to decide whether it is correct, and a second AI agent reviews
*how* you debugged it.

Built for **First Commit — Bharat Builds Tour (WeMakeDevs × AWS)** by team Code
Blooded. Targeting the **Ship It** and **Best UI** tracks.

---

## The one design decision that matters

> **Correctness is decided by running real hidden unit tests. It is never decided
> by asking a model whether the code looks right.**

LLMs can be talked into approving code that is subtly wrong, and one bad call in
a live demo sinks the whole pitch. So the pipeline is:

```
submit → Test Runner (sandboxed Lambda) → correct = tests_passed == tests_total
                                        → Evaluator Agent (Bedrock) explains and scores quality
```

The Evaluator Agent is handed the test outcome **as a fact** and is told not to
contradict it. That instruction is also enforced in code: its score is clamped
into the band the verdict allows (pass → 60–100, fail → 0–50), and it has no
`correct` field to return in the first place. See
[`backend/agents/evaluator.py`](backend/agents/evaluator.py).

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │  AWS Amplify Hosting         │
                    │  React + CodeMirror 6        │
                    └──────────────┬───────────────┘
                                   │  HTTPS
                    ┌──────────────▼───────────────┐
                    │  Amazon API Gateway (REST)   │
                    └──────────────┬───────────────┘
            ┌──────────────┬───────┴───────┬──────────────────┐
            ▼              ▼               ▼                  ▼
     GET /challenges  POST /sessions  POST /sessions/    GET /leaderboard
            │              │          {id}/submit               │
            ▼              ▼               │                    ▼
      ┌───────────┐  ┌───────────┐         │             ┌────────────┐
      │  Lambda   │  │  Lambda   │         │             │   Lambda   │
      └─────┬─────┘  └─────┬─────┘         │             └──────┬─────┘
            │              │               ▼                    │
            │              │      ┌──────────────────┐          │
            │              │      │  Submit Lambda   │          │
            │              │      └────┬────────┬────┘          │
            │              │           │        │               │
            │              │  ┌────────▼──┐  ┌──▼────────────┐  │
            │              │  │Test Runner│  │Amazon Bedrock │  │
            │              │  │  Lambda   │  │Evaluator Agent│  │
            │              │  │(sandboxed,│  │  (quality     │  │
            │              │  │ zero IAM) │  │   feedback)   │  │
            │              │  └────┬──────┘  └──┬────────────┘  │
            │              │       │ GROUND     │ never         │
            │              │       │ TRUTH      │ overrides     │
            ▼              ▼       ▼            ▼               ▼
      ┌──────────────────────────────────────────────────────────┐
      │  Amazon DynamoDB — Challenges · Sessions · Results (GSI) │
      └──────────────────────────────────────────────────────────┘

      Offline, before the demo:
      clean function ─→ Bedrock Bug Injector Agent ─→ buggy function
                        + hidden tests re-run to prove the bug bites
                        + human review  ─→ seeded into DynamoDB
```

### Two genuinely different agents

| | Bug Injector Agent | Evaluator Agent |
|---|---|---|
| Runs | Offline, once per challenge | Live, on every submission |
| Input | Clean function + bug category | Buggy code, ground truth, student's diff, **and the test result** |
| Output | `buggy_code`, `diff_summary`, `why_its_a_bug`, `hint_level_description` | `score`, `process_feedback`, `correctness_notes` |
| Can decide correctness? | n/a | **No** — never |
| Code | [`backend/agents/bug_injector.py`](backend/agents/bug_injector.py) | [`backend/agents/evaluator.py`](backend/agents/evaluator.py) |

---

## AWS services — mandatory-compliance mapping

> *"Using an AWS open-source project or AWS services is mandatory to win a prize."*

| AWS service | Where it lives in BreakFix | File |
|---|---|---|
| **Amazon Bedrock** | Runs both agents (Bug Injector offline, Evaluator live) | [`backend/agents/`](backend/agents/) |
| **AWS Lambda** | All backend compute — 4 API functions plus an isolated Test Runner | [`backend/lambdas/`](backend/lambdas/) |
| **Amazon API Gateway** | REST endpoints between the frontend and Lambda | [`infra/template.yaml`](infra/template.yaml) |
| **Amazon DynamoDB** | Challenges, Sessions, Results (+ leaderboard GSI) | [`backend/common/storage.py`](backend/common/storage.py) |
| **AWS Amplify Hosting** | Hosts the React frontend, gives the live URL | [`amplify.yml`](amplify.yml) |
| **API Gateway WebSocket API** | Carries the live layer: leaderboard, presence, activity feed | [`backend/lambdas/ws/`](backend/lambdas/ws/) |
| **Amazon DynamoDB Streams** | Triggers the broadcaster on every Sessions/Results write | [`backend/lambdas/broadcaster/`](backend/lambdas/broadcaster/) |
| **AWS Step Functions** | Orchestrates live challenge authoring, one state per gate | [`infra/statemachine.asl.json`](infra/statemachine.asl.json) |
| **Amazon EventBridge** | Domain events (`challenge.published`, `highscore.set`) | [`backend/common/events.py`](backend/common/events.py) |
| **Amazon CloudWatch** | Source of the live system-status panel | [`backend/lambdas/metrics/`](backend/lambdas/metrics/) |
| GitHub API | *Not AWS* — source of seed and live-authored functions | [`backend/authoring/github.py`](backend/authoring/github.py) |

All five are on-demand: `PAY_PER_REQUEST` DynamoDB, no provisioned capacity, no
always-on compute beyond Lambda.

---

## Repository layout

```
backend/
  common/        config, storage adapter (DynamoDB or local JSON), HTTP helpers, diffing
  agents/        Bedrock client + Bug Injector Agent + Evaluator Agent
  test_runner/   the sandbox: parent orchestrator, child process, Lambda invoker
  lambdas/       one directory per Lambda handler
  local_server.py  API Gateway stand-in for local development
seed-data/
  challenges/    5 challenges: clean.py, buggy.py, tests.json, ground_truth.json, golden/
  author_challenges.py  the offline authoring pipeline
  REVIEW.md      the human-review gate
scripts/
  validate_golden_set.py  PRD 12.3 golden-set validation
  deploy.sh / deploy_frontend.sh
infra/template.yaml  SAM template — the whole stack
frontend/
  src/theme/     Obsidian Telemetry design tokens + the CodeMirror theme built from them
  src/pages/     Landing, Challenges, Editor, Results, Leaderboard, How It Works
  src/components/ Nav, reveals, skeletons, score ring, countdown, pipeline diagram
tests/           unit, sandbox-isolation and DynamoDB integration tests
```

---

## Running it locally

**Everything runs from the repo root except the two `npm` commands, which run
from `frontend/`.** There is no separate backend directory to `cd` into — the
Python entry points are invoked by path from the root.

### One-time setup

```bash
# --- backend --- (from the repo root) -------------------------------------
cd ~/path/to/BreakFix
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# --- frontend --- (from frontend/) ----------------------------------------
cd frontend
npm install
cd ..
```

Or in one step, from the repo root: `make setup`

### Seed the challenges and check everything works

All three run **from the repo root**:

```bash
BREAKFIX_STORAGE=local .venv/bin/python seed-data/author_challenges.py   # make seed
.venv/bin/python scripts/validate_golden_set.py                          # make validate
.venv/bin/python -m pytest tests -q                                      # make test
```

`seed` writes the 5 challenges into `.localdb/`. You must run it once before
starting the servers, or the challenge list will be empty.

### Run it — two terminals

```bash
# Terminal 1 — API, from the REPO ROOT
.venv/bin/python backend/local_server.py --port 8000      # make serve

# Terminal 2 — UI, from FRONTEND/
cd frontend && npm run dev                                 # make web
```

Open **http://localhost:5173**. The UI defaults to the API on
`http://127.0.0.1:8000`, so no `.env` file is needed locally — set
`VITE_API_BASE_URL` only when pointing at a deployed API Gateway stage.

### Quick reference

| What | Run from | Command | Make shortcut |
|---|---|---|---|
| Backend deps | repo root | `.venv/bin/pip install -r requirements.txt` | `make setup` |
| Frontend deps | `frontend/` | `npm install` | `make setup` |
| Seed challenges | repo root | `BREAKFIX_STORAGE=local .venv/bin/python seed-data/author_challenges.py` | `make seed` |
| Golden set | repo root | `.venv/bin/python scripts/validate_golden_set.py` | `make validate` |
| Tests | repo root | `.venv/bin/python -m pytest tests -q` | `make test` |
| API server | repo root | `.venv/bin/python backend/local_server.py --port 8000` | `make serve` |
| UI dev server | `frontend/` | `npm run dev` | `make web` |
| Production build | `frontend/` | `npm run build` | `make build` |

Every `make` target is run from the repo root — the Makefile does its own `cd`.

Nothing above needs AWS credentials. Storage falls back to a local JSON store
and, without Bedrock, the Evaluator Agent degrades to a deterministic fallback
scorer that is **clearly labelled as such in the UI**. The pass/fail verdict is
identical either way, because it comes from executing the tests.

---

## Deploying to AWS

**Prerequisites**

* AWS CLI v2, configured (`aws configure`)
* AWS SAM CLI (`brew install aws-sam-cli`)
* **Bedrock model access enabled** in your region for the model id you deploy
  with (Bedrock console → Model access). This is a manual, one-time step.

```bash
./scripts/deploy.sh             # backend: SAM build + deploy, then seeds DynamoDB
./scripts/deploy_frontend.sh    # frontend: build + Amplify Hosting deploy
```

`deploy.sh` prints the API Gateway URL and writes `frontend/.env.production`.
`deploy_frontend.sh` prints the live Amplify URL.

Alternatively, connect this repo in the Amplify console — [`amplify.yml`](amplify.yml)
is the build spec — and set `VITE_API_BASE_URL` to the API URL.

**After the first deploy**, lock CORS down to the Amplify origin:

```bash
CorsAllowOrigin=https://main.<app-id>.amplifyapp.com ./scripts/deploy.sh
```

---

## Frontend

Six pages, all reading from the live API — there is no mock data in the build.

| Page | Route | Real data behind it |
|---|---|---|
| Landing | `/` | `GET /stats` for every headline figure |
| Active Challenges | `/challenges` | `GET /challenges` + `GET /stats` per-challenge attempts, `GET /leaderboard` in the rail |
| Challenge Editor | `/challenges/:sessionId` | `POST /sessions` response: real `buggy_code`, `start_time`, `tests_total` |
| Results | `/results/:sessionId` | The `POST /sessions/{id}/submit` response, verbatim |
| Leaderboard | `/leaderboard` | `GET /leaderboard` only |
| How It Works | `/how-it-works` | Static architecture copy + real counts from `GET /stats` |

**Design system.** `src/theme/tokens.css` holds the Obsidian Telemetry palette,
type scale, 4px spacing baseline, 10px/6px radii and the elevation matrix. The
CodeMirror theme is built from the same tokens so the editor is part of the
system rather than a foreign widget. Ligatures are disabled on every code
surface — JetBrains Mono renders `<=` as a single `≤` glyph, and this is a
product about spotting exactly that difference.

**Motion.** Framer Motion (`motion/react`) handles all of it: the hero word
reveal and highlight sweep, scroll reveals with `whileInView` + `once`, the
`AnimatePresence` page cross-fade, spring-physics hover lifts, the score-ring
stroke animation, the rolling countdown digits, and the pipeline's SVG
`pathLength` line draw. GSAP was not needed. Every animation collapses to an
instant state change under `prefers-reduced-motion`.

**Honest empty states.** Where there is no data, the UI says so. `null` from the
API renders as an em dash, the leaderboard shows an empty state instead of
padded rows, and a challenge with no attempts reads "No attempts yet" rather
than a fabricated count.

**Client-side routing.** Deep links need an SPA rewrite;
`scripts/deploy_frontend.sh` applies the Amplify custom rule automatically.

## Mission briefs

Every challenge carries a student-facing brief so the screen is never just "here
is some code, go":

* `student_facing_summary` — what the function does in the real codebase
* `symptom_description` — what goes wrong, observably
* `source_url` — a link to the real function on GitHub

These are generated by the **Mission Brief Agent** ([`backend/agents/brief_writer.py`](backend/agents/brief_writer.py))
in the offline pipeline, and **leak-checked before acceptance**: a brief is
rejected if it quotes the changed line, names the bug category, names an
identifier that differs between the clean and buggy versions, or uses
prescriptive language. The check runs again at publish time, so no route into
the Challenges table can bypass it.

## Real-time layer

```
Sessions / Results write
        │  DynamoDB Streams
        ▼
  Broadcaster Lambda ──► API Gateway WebSocket API ──► every connected client
        ▲                                               (snapshot on $connect)
        │  EventBridge rule
  challenge.published / highscore.set
```

Nothing polls. Three live views, all built from committed rows:

| View | Real source | Empty state |
|---|---|---|
| Leaderboard | Results GSI | honest empty panel |
| Presence — "N solving now" | Sessions with `status = in_progress`, **expired** past their own time limit + grace | the badge is absent, never "0 people" |
| Activity feed | Results, newest first | "No submissions yet" — never padded |

Presence expiry matters: without it an abandoned tab would inflate the count
forever, so a real number would drift into a fake one.

Locally, [`backend/local_ws.py`](backend/local_ws.py) is a dependency-free
RFC 6455 server and the same broadcaster Lambda is invoked with a synthetic
stream record, so the live layer is genuinely exercised in development.

## Live challenge authoring (admin only)

An AWS Step Functions state machine runs the same gates as the offline pipeline:

```
fetch → author tests → verify against CLEAN → inject bug → verify the bug bites
      → golden-set validation → mission brief → land in pending_review
```

* **Terminal state is `pending_review`.** A challenge becomes visible only after
  an explicit human click in the admin screen, and publishing is refused without
  a leak-checked mission brief.
* **Fail-closed auth.** With `ADMIN_PASSPHRASE` unset every admin route returns
  503, so an unconfigured deploy exposes nothing.
* **Step transitions stream live** over the same WebSocket channel.
* **Bug injection** uses the Bug Injector Agent, falling back to deterministic
  AST mutation ([`backend/authoring/mutation.py`](backend/authoring/mutation.py))
  labelled `mutation-fallback` — never passed off as the agent.

**Known constraint:** live authoring only works for functions that run
standalone. Most library functions import from their own package
(`from .i18n import ...`), and the fetcher rejects those with a clear message
rather than producing a broken challenge. Self-contained stdlib functions such
as `shlex.quote` and `textwrap.indent` work well; there is also a paste-source
path for adapted code.

## Difficulty calibration

Each card shows a real pass rate and median solve time computed from the Results
table — but only once a challenge has at least `CALIBRATION_MIN_SAMPLE` (default
5) scored submissions. Below that the curated static label stands and the card
says how many more attempts are needed. A pass rate off one data point would be
worse than no pass rate.

## Sandbox threat model

Submitted code is untrusted, arbitrary code executing on our infrastructure. It
is treated accordingly ([`backend/test_runner/`](backend/test_runner/)):

| Control | How |
|---|---|
| Separate process | Spawned as `python -I -B child_runner.py`, own session/process group |
| Hard wall-clock timeout | Parent `SIGKILL`s the whole process group after 5s |
| Per-test timeout | `signal.setitimer` at 2s per test |
| CPU limit | `RLIMIT_CPU` |
| Memory limit | `RLIMIT_AS` (falls back to `RLIMIT_DATA`), plus the Lambda memory ceiling |
| No network | CPython audit hook on every `socket.*` event + the `socket` module neutered before user code loads |
| No filesystem outside scratch | Audit hook on `open` and path-bearing `os.*` events; only the per-run temp dir is writable, only the stdlib is readable |
| No process creation | Audit hook on `subprocess`/`os.exec`/`os.fork`/`os.system`, plus `RLIMIT_NPROC` |
| No blast radius | The Test Runner is **its own Lambda with no IAM policies at all** — an escape reaches no DynamoDB table, no Bedrock, nothing |
| Output integrity | The result channel is a duped fd; the student's `stdout` goes to `/dev/null` and cannot forge a result |

**What this is not:** it is a CPython audit-hook sandbox inside a disposable
Lambda execution environment, not gVisor or a container per submission. A
CPython sandbox-escape primitive would defeat the in-process layer — which is
exactly why the Test Runner's IAM role grants nothing, so the layer that
actually protects the data does not depend on CPython.

Every control above has a test in [`tests/test_test_runner.py`](tests/test_test_runner.py).

---

## Authoring a new challenge

```
seed-data/challenges/challenge-06/
  meta.json          repo, function name, bug category, difficulty, time limit, licence
  clean.py           the correct function
  tests.json         2–4 hidden {input, expected_output} pairs
  buggy.py           written by the agent (or by hand), reviewed by a human
  ground_truth.json  what changed and why it is a bug
  golden/alt_fix.py     a correct fix by a different approach
  golden/masked_fix.py  a fix that hides the symptom without fixing the cause
```

```bash
python seed-data/author_challenges.py              # verify + seed
python seed-data/author_challenges.py --use-agent  # regenerate bugs via Bedrock
python scripts/validate_golden_set.py              # the acceptance gate
```

The pipeline refuses to accept a challenge whose hidden tests do not pass
against `clean.py`, and **discards any injected bug that fails to break at
least one test**.

---

## Testing

| Layer | Command | Covers |
|---|---|---|
| Unit + sandbox isolation | `make test` | handlers, diffing, agents, and every sandbox control |
| DynamoDB integration | `make test` (via `moto`) | real table schemas, the leaderboard GSI query, handlers on DynamoDB |
| Golden set | `make validate` | 6 golden cases × 5 challenges — the PRD 12.3 acceptance gate |
| Browser end-to-end | see below | select → edit → submit → results → leaderboard in Chrome |

The golden set checks two independent things per case: did the Test Runner
produce the **right** pass/fail, and did the Evaluator Agent's score land in the
band that outcome allows without ever contradicting it.

---

## Demo script (3 minutes)

1. **Home** — five real functions from cpython, humanize, django and werkzeug.
2. **Pick `slugify`** — the editor loads the *buggy* version; the timer starts.
   Say: *"an AI agent injected exactly one bug into this, offline, and a human
   reviewed it."*
3. **Find the bug** — the `+` quantifier is missing from the final `re.sub`.
   Fix it.
4. **Submit** — *"this does not ask a model whether my code looks right. It runs
   four hidden unit tests in a sandboxed Lambda that has no IAM permissions at
   all."*
5. **Results** — pass/fail from the tests, score and two pieces of feedback from
   the Evaluator Agent, per-test breakdown, time taken.
6. **Leaderboard** — updates immediately.

---

## Known deviations from the PRD

| PRD | What was built | Why |
|---|---|---|
| §5.1 "Test Runner Lambda" | Built as a separate Lambda **with an empty IAM policy set** | The submit Lambda can read the Challenges table (hidden tests) and call Bedrock. Running untrusted code there would put those in the blast radius. |
| §5.3 "2–3 repos" | 4 repos across 5 challenges | Better variety for the demo at no extra cost. |
| §6.4 "GSI on score, descending" | GSI is `(leaderboard_pk, score)` with a constant partition key | DynamoDB cannot sort a GSI globally without one. Same read, one query. |
| §7 `POST /sessions` response | Also returns `function_name`, `repo_name`, `language`, `time_limit_seconds` | The editor screen needs them; the alternative is a second round-trip. |
| §8.2 Evaluator scoring | Score is **clamped** to the rubric band the test outcome allows | "Do not contradict the test outcome" is a request to a model; this makes it a guarantee. |
| §6.1 Challenges table | Added `time_limit_seconds`, `repo_url`, `license`, `source_path` | The countdown needs a duration; the rest is attribution. |
| §7 API | Added `GET /stats` | The dashboard headline figures had no real source. Rather than hardcode them, this returns actual counts from DynamoDB and `null` where there is genuinely no data yet. |
| §6.1 Challenges table | Added `tests_total` and `code_preview` | The UI needs the hidden-test *count* and a safe snippet. The assertions and the ground-truth diff are still never served. |
| — | Added a labelled fallback scorer for Bedrock outages | A Bedrock blip during the demo degrades the feedback text instead of breaking submit. Correctness is unaffected. |

## Licence and attribution

The seed functions are faithful reimplementations of public APIs from
[python/cpython](https://github.com/python/cpython) (PSF-2.0),
[python-humanize/humanize](https://github.com/python-humanize/humanize) (MIT),
[django/django](https://github.com/django/django) (BSD-3-Clause) and
[pallets/werkzeug](https://github.com/pallets/werkzeug) (BSD-3-Clause), trimmed
of repo-internal dependencies so they run standalone in the sandbox. Each
challenge's `meta.json` records its source and licence.
