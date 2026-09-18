"""GET /leaderboard -- derived read over Results (PRD Section 6.4, F5).

No write path of its own: top scores come from the Results GSI and the display
name is joined in from Sessions at read time. Top 10 by score, ties broken by
the faster time.
"""
from common import config, http, storage


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    limit = config.LEADERBOARD_LIMIT
    params = event.get("queryStringParameters") or {}
    if params.get("limit", "").isdigit():
        limit = max(1, min(50, int(params["limit"])))

    store = storage.get_store()
    rows = store.top_results(limit)

    entries = []
    for row in rows:
        display_name = row.get("user_display_name")
        if not display_name:
            session = store.get_session(row.get("session_id", "")) or {}
            display_name = session.get("user_display_name", "Anonymous")
        entries.append(
            {
                "user_display_name": display_name,
                "challenge_id": row.get("challenge_id"),
                "score": int(row.get("score", 0)),
                "time_taken_seconds": int(row.get("time_taken_seconds", 0)),
                "correct": bool(row.get("correct")),
            }
        )
    return http.ok({"leaderboard": entries})
