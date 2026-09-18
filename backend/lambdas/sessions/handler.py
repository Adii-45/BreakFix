"""POST /sessions -- start a timed attempt (PRD Section 7, Section 5.1 stage 3).

Writes the Sessions row that makes elapsed time server-authoritative: the
client's countdown is cosmetic, `start_time` here is what counts (F2).
"""
import time
import uuid

from common import config, http, storage


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    body, err = http.parse_body(event)
    if err:
        return err

    challenge_id = (body.get("challenge_id") or "").strip()
    if not challenge_id:
        return http.error(400, "challenge_id is required.")

    display_name = (body.get("user_display_name") or "").strip() or "Anonymous"
    display_name = display_name[: config.MAX_DISPLAY_NAME_LENGTH]

    store = storage.get_store()
    challenge = store.get_challenge(challenge_id)
    if not challenge:
        return http.error(404, f"Unknown challenge '{challenge_id}'.")

    session_id = str(uuid.uuid4())
    start_time = int(time.time())
    store.put_session(
        {
            "session_id": session_id,
            "challenge_id": challenge_id,
            "user_display_name": display_name,
            "start_time": start_time,
            "status": "in_progress",
        }
    )

    return http.ok(
        {
            "session_id": session_id,
            "buggy_code": challenge["buggy_code"],
            "start_time": start_time,
            # Context the editor screen needs. Not in the PRD's minimal response
            # spec, but the alternative is a second round-trip per session start.
            "challenge_id": challenge_id,
            "function_name": challenge.get("function_name"),
            "repo_name": challenge.get("repo_name"),
            "language": challenge.get("language", "python"),
            "difficulty": challenge.get("difficulty", "medium"),
            "time_limit_seconds": int(challenge.get("time_limit_seconds", 300)),
            "tests_total": int(challenge.get("tests_total") or 0),
        }
    )
