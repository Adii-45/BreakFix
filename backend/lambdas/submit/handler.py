"""POST /sessions/{session_id}/submit -- the core of the product (PRD F3).

Order of operations is the whole design (Section 5.1 stages 5-8, Section 5.2):

    diff  ->  RUN HIDDEN TESTS  ->  compute `correct`  ->  Evaluator Agent  ->  persist

`correct` is set from tests_passed == tests_total before Bedrock is called at
all, and the Evaluator Agent's response is never consulted for it. If Bedrock is
slow or down, the student still gets a truthful verdict.
"""
import time

from agents import evaluator
from common import config, diffing, events, http, storage
from test_runner import invoker


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    session_id = http.path_param(event, "session_id") or http.path_param(event, "id")
    if not session_id:
        return http.error(400, "session_id is missing from the request path.")

    body, err = http.parse_body(event)
    if err:
        return err

    submitted_code = body.get("submitted_code")
    if not isinstance(submitted_code, str) or not submitted_code.strip():
        return http.error(400, "submitted_code is required and cannot be empty.")

    store = storage.get_store()
    session = store.get_session(session_id)
    if not session:
        return http.error(404, "Unknown session.")

    if session.get("status") == "complete":
        previous = store.get_result(session_id)
        if previous:
            return http.respond(409, {"error": "This session has already been submitted.", "result": _shape(previous)})
        return http.error(409, "This session has already been submitted.")

    challenge = store.get_challenge(session["challenge_id"])
    if not challenge:
        return http.error(404, "The challenge for this session no longer exists.")

    buggy_code = challenge["buggy_code"]
    test_cases = _load_json_field(challenge.get("test_cases"), default=[])
    ground_truth = challenge.get("ground_truth_diff", "")

    # A whitespace-only edit is not a fix. Collapsing it to an empty diff keeps
    # the "no change submitted" golden case (PRD 12.3) honest even when the
    # student adds a stray newline before hitting submit.
    unchanged = diffing.is_unchanged(buggy_code, submitted_code)
    student_diff = "" if unchanged else diffing.unified_diff(buggy_code, submitted_code)
    stats = diffing.diff_stats(buggy_code, submitted_code)
    if unchanged:
        stats["lines_changed"] = 0

    # --- Ground truth: deterministic execution, never a model call -----------
    test_result = invoker.run(
        code=submitted_code,
        entry_point=challenge["function_name"],
        test_cases=test_cases,
    )
    tests_passed = test_result["tests_passed"]
    tests_total = test_result["tests_total"]
    correct = tests_total > 0 and tests_passed == tests_total

    # --- Qualitative layer, handed the result as a fact ---------------------
    feedback = evaluator.evaluate(
        buggy_code=buggy_code,
        ground_truth_diff=_as_text(ground_truth),
        submitted_code=submitted_code,
        test_result=test_result,
        student_diff=student_diff,
        diff_stats=stats,
    )

    time_taken = max(0, int(time.time()) - int(session.get("start_time", 0)))

    result = {
        "session_id": session_id,
        "challenge_id": session["challenge_id"],
        "user_display_name": session.get("user_display_name", "Anonymous"),
        "submitted_code": submitted_code,
        "tests_passed": tests_passed,
        "tests_total": tests_total,
        "correct": correct,
        "score": int(feedback["score"]),
        "process_feedback": feedback["process_feedback"],
        "correctness_notes": feedback["correctness_notes"],
        "time_taken_seconds": time_taken,
        "feedback_source": feedback.get("feedback_source", "unknown"),
        "runner_status": test_result.get("runner_status"),
        "lines_changed": stats["lines_changed"],
        "submitted_at": int(time.time()),
    }
    # Capture the standing best BEFORE the write so "new high score" is a real
    # comparison rather than an assumption.
    previous_best = _previous_best(store, session["challenge_id"])

    store.put_result(result)
    store.set_session_status(session_id, "complete")

    # Announce, do not broadcast. The write path stays ignorant of consumers.
    events.emit_high_score(result, previous_best)

    response = _shape(result)
    # Per-test detail without the expected values -- enough for the student to
    # see which cases broke, not enough to reverse-engineer the hidden suite.
    response["test_summary"] = [
        {"name": t.get("name"), "passed": bool(t.get("passed"))} for t in test_result.get("per_test", [])
    ]
    if test_result.get("load_error"):
        response["execution_error"] = test_result["load_error"]
    return http.ok(response)


def _previous_best(store, challenge_id):
    """Highest score already recorded for this challenge, or None if it is the first."""
    scores = [
        int(r.get("score", 0)) for r in store.all_results()
        if r.get("challenge_id") == challenge_id
    ]
    return max(scores) if scores else None


def _shape(result):
    return {
        "correct": bool(result.get("correct")),
        "tests_passed": int(result.get("tests_passed", 0)),
        "tests_total": int(result.get("tests_total", 0)),
        "score": int(result.get("score", 0)),
        "process_feedback": result.get("process_feedback", ""),
        "correctness_notes": result.get("correctness_notes", ""),
        "time_taken_seconds": int(result.get("time_taken_seconds", 0)),
        "feedback_source": result.get("feedback_source", "unknown"),
    }


def _load_json_field(value, default):
    """Challenges store test_cases as a JSON string (PRD 6.1); the local store
    keeps them as native lists. Accept either."""
    import json

    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _as_text(value):
    import json

    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2)
    return str(value or "")
