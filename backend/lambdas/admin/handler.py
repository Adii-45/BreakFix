"""Admin-only authoring API (Part 3).

Gated behind a shared passphrase, and deliberately fail-closed: if
ADMIN_PASSPHRASE is unset every route returns 503, so an unconfigured deploy
exposes nothing rather than defaulting to open.

Routes:
  POST /admin/authoring            start a run
  GET  /admin/authoring            recent runs
  GET  /admin/authoring/{id}       one run's live status
  GET  /admin/pending              challenges awaiting review
  POST /admin/challenges/{id}/publish   the human gate
  POST /admin/challenges/{id}/reject
"""
import hmac
import json
import time

from common import config, events, http, storage


def _authorised(event) -> bool:
    expected = config.ADMIN_PASSPHRASE
    if not expected:
        return False
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    supplied = headers.get("x-admin-passphrase", "")
    return hmac.compare_digest(str(supplied), str(expected))


def _guard(event):
    """Returns an error response, or None when the caller may proceed."""
    if not config.ADMIN_PASSPHRASE:
        return http.error(503, "Live authoring is disabled. Set ADMIN_PASSPHRASE to enable it.")
    if not _authorised(event):
        return http.error(401, "Invalid admin passphrase.")
    return None


# ---------------------------------------------------------------------------

@http.handle_exceptions
def start_authoring(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    denied = _guard(event)
    if denied:
        return denied

    body, err = http.parse_body(event)
    if err:
        return err

    function_name = (body.get("function_name") or "").strip()
    if not function_name:
        return http.error(400, "function_name is required.")
    if not (body.get("github_url") or body.get("source_code")):
        return http.error(400, "Provide either a github_url or pasted source_code.")

    inputs = {
        "function_name": function_name,
        "github_url": (body.get("github_url") or "").strip(),
        "source_code": body.get("source_code") or "",
        "test_cases": body.get("test_cases"),
        "difficulty": body.get("difficulty", "medium"),
        "time_limit_seconds": int(body.get("time_limit_seconds") or 300),
        "bug_category": body.get("bug_category") or "off-by-one",
        "student_facing_summary": body.get("student_facing_summary", ""),
        "symptom_description": body.get("symptom_description", ""),
    }

    if config.STATE_MACHINE_ARN:
        record = _start_step_functions(inputs)
    else:
        from authoring import orchestrator

        record = orchestrator.start_local(inputs)
    return http.ok({"execution": record})


def _start_step_functions(inputs):
    """Kick off the real AWS Step Functions state machine."""
    import boto3

    from authoring import steps

    client = boto3.client("stepfunctions", region_name=config.AWS_REGION)
    response = client.start_execution(
        stateMachineArn=config.STATE_MACHINE_ARN,
        input=json.dumps({"step": steps.STEP_NAMES[0], "context": inputs}),
    )
    return {
        "execution_id": response["executionArn"],
        "status": "RUNNING",
        "started_at": int(time.time()),
        "finished_at": None,
        "function_name": inputs["function_name"],
        "github_url": inputs["github_url"],
        "challenge_id": None,
        "error": None,
        "steps": [{"name": n, "label": steps.STEP_LABELS[n], "status": "PENDING",
                   "started_at": None, "finished_at": None, "detail": None} for n in steps.STEP_NAMES],
    }


@http.handle_exceptions
def get_authoring(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    denied = _guard(event)
    if denied:
        return denied

    execution_id = http.path_param(event, "execution_id")
    if not execution_id:
        from authoring import orchestrator

        return http.ok({"executions": orchestrator.recent()})

    if config.STATE_MACHINE_ARN and execution_id.startswith("arn:"):
        return http.ok({"execution": _describe_step_functions(execution_id)})

    from authoring import orchestrator

    record = orchestrator.get(execution_id)
    if not record:
        return http.error(404, "Unknown execution.")
    return http.ok({"execution": record})


def _describe_step_functions(execution_arn):
    """Project a Step Functions execution onto the same shape the UI renders."""
    import boto3

    from authoring import steps

    client = boto3.client("stepfunctions", region_name=config.AWS_REGION)
    described = client.describe_execution(executionArn=execution_arn)
    history = client.get_execution_history(executionArn=execution_arn, maxResults=200, reverseOrder=False)

    entered, exited, failures = {}, {}, {}
    for entry in history.get("events", []):
        detail = entry.get("stateEnteredEventDetails") or {}
        if detail.get("name"):
            entered[detail["name"]] = int(entry["timestamp"].timestamp())
        detail = entry.get("stateExitedEventDetails") or {}
        if detail.get("name"):
            exited[detail["name"]] = int(entry["timestamp"].timestamp())
        if entry.get("type", "").endswith("Failed"):
            fail = entry.get("taskFailedEventDetails") or entry.get("executionFailedEventDetails") or {}
            if fail.get("cause"):
                failures["__last__"] = fail.get("cause", "")[:400]

    step_rows = []
    for name in steps.STEP_NAMES:
        state_name = name
        if state_name in exited:
            status = "SUCCEEDED"
        elif state_name in entered:
            status = "RUNNING"
        else:
            status = "PENDING"
        step_rows.append({
            "name": name, "label": steps.STEP_LABELS[name], "status": status,
            "started_at": entered.get(state_name), "finished_at": exited.get(state_name),
            "detail": None,
        })

    output = {}
    if described.get("output"):
        try:
            output = json.loads(described["output"]).get("context", {})
        except (json.JSONDecodeError, TypeError):
            output = {}

    return {
        "execution_id": execution_arn,
        "status": described["status"],
        "started_at": int(described["startDate"].timestamp()),
        "finished_at": int(described["stopDate"].timestamp()) if described.get("stopDate") else None,
        "function_name": output.get("function_name", ""),
        "github_url": output.get("github_url", ""),
        "challenge_id": output.get("challenge_id"),
        "error": failures.get("__last__"),
        "steps": step_rows,
    }


@http.handle_exceptions
def list_pending(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    denied = _guard(event)
    if denied:
        return denied

    rows = storage.get_store().list_challenges()
    pending = [c for c in rows if c.get("status") == "pending_review"]
    return http.ok({
        "pending": [
            {
                "challenge_id": c["challenge_id"],
                "repo_name": c.get("repo_name"),
                "function_name": c.get("function_name"),
                "difficulty": c.get("difficulty"),
                "bug_category": c.get("bug_category"),
                "tests_total": c.get("tests_total"),
                "buggy_code": c.get("buggy_code"),
                "ground_truth_diff": c.get("ground_truth_diff"),
                "student_facing_summary": c.get("student_facing_summary", ""),
                "symptom_description": c.get("symptom_description", ""),
                "source_url": c.get("source_url", ""),
                "injection_source": c.get("injection_source"),
                "tests_source": c.get("tests_source"),
                "brief_source": c.get("brief_source"),
                "created_at": c.get("created_at"),
            }
            for c in sorted(pending, key=lambda c: c.get("created_at", 0), reverse=True)
        ]
    })


@http.handle_exceptions
def publish(event, context):  # noqa: ANN001
    """The human gate. Nothing reaches students without passing through here."""
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    denied = _guard(event)
    if denied:
        return denied

    challenge_id = http.path_param(event, "challenge_id")
    store = storage.get_store()
    challenge = store.get_challenge(challenge_id)
    if not challenge:
        return http.error(404, "Unknown challenge.")
    if challenge.get("status") == "published":
        return http.error(409, "That challenge is already published.")

    body, _ = http.parse_body(event)
    body = body or {}
    summary = (body.get("student_facing_summary") or challenge.get("student_facing_summary") or "").strip()
    symptom = (body.get("symptom_description") or challenge.get("symptom_description") or "").strip()

    # A challenge without a brief is exactly the "here's some code, go" problem
    # Part 1 set out to fix, so publication requires one.
    if len(summary) < 40 or len(symptom) < 20:
        return http.error(
            422,
            "A mission brief is required before publishing: write what the function does "
            "and what the observable symptom is.",
        )

    from agents import brief_writer

    ground_truth = challenge.get("ground_truth_diff") or "{}"
    try:
        ground_truth = json.loads(ground_truth) if isinstance(ground_truth, str) else ground_truth
    except json.JSONDecodeError:
        ground_truth = {}
    try:
        brief_writer.assert_no_leak(
            {"purpose": summary, "symptom": symptom},
            ground_truth, challenge.get("clean_code", ""), challenge.get("buggy_code", ""),
        )
    except brief_writer.BriefLeak as exc:
        return http.error(422, f"That brief gives the answer away: {exc}")

    updated = {**challenge, "student_facing_summary": summary, "symptom_description": symptom,
               "status": "published", "published_at": int(time.time())}
    store.put_challenge(updated)

    # Decouple the announcement from the write path (Part 4.3).
    events.emit(
        "challenge.published",
        {"challenge_id": challenge_id, "function_name": challenge.get("function_name"),
         "repo_name": challenge.get("repo_name"), "difficulty": challenge.get("difficulty")},
    )
    return http.ok({"challenge_id": challenge_id, "status": "published"})


@http.handle_exceptions
def reject(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    denied = _guard(event)
    if denied:
        return denied

    challenge_id = http.path_param(event, "challenge_id")
    store = storage.get_store()
    challenge = store.get_challenge(challenge_id)
    if not challenge:
        return http.error(404, "Unknown challenge.")
    store.put_challenge({**challenge, "status": "rejected", "rejected_at": int(time.time())})
    return http.ok({"challenge_id": challenge_id, "status": "rejected"})
