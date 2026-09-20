"""GET /sessions/{session_id} and GET /sessions/{session_id}/result.

Without these the editor and results screens exist only in React Router memory:
a refresh, a back-forward, or a pasted URL loses the attempt entirely. A judge
refreshing mid-challenge is the most likely way this demo falls over, so both
screens are made addressable.

Nothing secret is served. A session returns the same fields POST /sessions
already returned; a result returns the same fields the submit call already
returned. Hidden test assertions and the ground-truth diff stay server-side.
"""
from common import http, storage


@http.handle_exceptions
def get_session(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    session_id = http.path_param(event, "session_id")
    if not session_id:
        return http.error(400, "session_id is missing from the request path.")

    store = storage.get_store()
    session = store.get_session(session_id)
    if not session:
        return http.error(404, "Unknown session.")

    challenge = store.get_challenge(session["challenge_id"])
    if not challenge:
        return http.error(404, "The challenge for this session no longer exists.")

    return http.ok(
        {
            "session_id": session_id,
            "challenge_id": session["challenge_id"],
            "buggy_code": challenge["buggy_code"],
            "start_time": int(session.get("start_time", 0)),
            "status": session.get("status", "in_progress"),
            "user_display_name": session.get("user_display_name", "Anonymous"),
            "function_name": challenge.get("function_name"),
            "repo_name": challenge.get("repo_name"),
            "language": challenge.get("language", "python"),
            "difficulty": challenge.get("difficulty", "medium"),
            "time_limit_seconds": int(challenge.get("time_limit_seconds", 300)),
            "tests_total": int(challenge.get("tests_total") or 0),
            "student_facing_summary": challenge.get("student_facing_summary", ""),
            "symptom_description": challenge.get("symptom_description", ""),
            "source_url": challenge.get("source_url", ""),
        }
    )


@http.handle_exceptions
def get_result(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    session_id = http.path_param(event, "session_id")
    if not session_id:
        return http.error(400, "session_id is missing from the request path.")

    store = storage.get_store()
    result = store.get_result(session_id)
    if not result:
        return http.error(404, "No result has been recorded for this session.")

    return http.ok(
        {
            "correct": bool(result.get("correct")),
            "tests_passed": int(result.get("tests_passed", 0)),
            "tests_total": int(result.get("tests_total", 0)),
            "score": int(result.get("score", 0)),
            "process_feedback": result.get("process_feedback", ""),
            "correctness_notes": result.get("correctness_notes", ""),
            "time_taken_seconds": int(result.get("time_taken_seconds", 0)),
            "feedback_source": result.get("feedback_source", "unknown"),
            "challenge_id": result.get("challenge_id"),
            "submitted_code": result.get("submitted_code", ""),
            # Recomputed the same way the submit response builds it, so a
            # recovered results page is identical to the one you first saw.
            "test_summary": result.get("test_summary") or [],
            "execution_error": result.get("execution_error") or "",
        }
    )
