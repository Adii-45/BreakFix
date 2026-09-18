"""Real-time payloads and the broadcast transport (Part 2).

Every payload here is assembled from rows that actually exist in DynamoDB.
There is no synthetic presence, no seeded activity and no padding: an empty
table produces an empty list, and the UI is expected to say so.

Transport:
  * In AWS  -- API Gateway Management API `post_to_connection`, fanned out to
               the connection ids in the Connections table. The broadcaster is
               triggered by DynamoDB Streams, so nothing polls.
  * Locally -- an in-process hub (backend/local_ws.py) registers itself via
               `set_local_sink`, so the same payloads flow over a real
               WebSocket during development.
"""
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from common import config, storage

logger = logging.getLogger(__name__)

# Set by the local dev WebSocket hub. Unused in Lambda.
_local_sink: Optional[Callable[[Dict[str, Any]], None]] = None


def set_local_sink(sink: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    global _local_sink
    _local_sink = sink


# ---------------------------------------------------------------------------
# Payload builders -- all real reads
# ---------------------------------------------------------------------------

def build_presence(store=None) -> Dict[str, int]:
    """How many people are genuinely mid-attempt on each challenge, right now.

    Counts Sessions rows with status == in_progress whose clock has not yet run
    out (their challenge's own time limit plus a grace period). A tab left open
    overnight stops counting, which is the difference between a real presence
    number and a number that only ever goes up.
    """
    store = store or storage.get_store()
    now = int(time.time())
    limits = {c["challenge_id"]: int(c.get("time_limit_seconds") or 300) for c in store.list_challenges()}

    counts: Dict[str, int] = {cid: 0 for cid in limits}
    for session in store.all_sessions():
        if session.get("status") != "in_progress":
            continue
        cid = session.get("challenge_id")
        if cid not in counts:
            continue
        window = limits.get(cid, 300) + config.PRESENCE_GRACE_SECONDS
        if now - int(session.get("start_time") or 0) <= window:
            counts[cid] += 1
    return counts


def build_activity(store=None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Genuine recent submissions, newest first. Never padded to a target length."""
    store = store or storage.get_store()
    limit = limit or config.ACTIVITY_FEED_LIMIT
    functions = {c["challenge_id"]: c.get("function_name") for c in store.list_challenges()}

    events = []
    for row in store.recent_results(limit):
        events.append(
            {
                "kind": "solved" if row.get("correct") else "attempted",
                "session_id": row.get("session_id"),
                "user_display_name": row.get("user_display_name") or "Anonymous",
                "challenge_id": row.get("challenge_id"),
                "function_name": functions.get(row.get("challenge_id")),
                "score": int(row.get("score", 0)),
                "correct": bool(row.get("correct")),
                "tests_passed": int(row.get("tests_passed", 0)),
                "tests_total": int(row.get("tests_total", 0)),
                "time_taken_seconds": int(row.get("time_taken_seconds", 0)),
                "at": int(row.get("submitted_at", 0)),
            }
        )
    return events


def build_leaderboard(store=None) -> List[Dict[str, Any]]:
    store = store or storage.get_store()
    rows = store.top_results(config.LEADERBOARD_LIMIT)
    return [
        {
            "user_display_name": r.get("user_display_name") or "Anonymous",
            "challenge_id": r.get("challenge_id"),
            "score": int(r.get("score", 0)),
            "time_taken_seconds": int(r.get("time_taken_seconds", 0)),
            "correct": bool(r.get("correct")),
        }
        for r in rows
    ]


def build_snapshot(store=None) -> Dict[str, Any]:
    """Everything a freshly-connected client needs, in one message."""
    store = store or storage.get_store()
    return {
        "type": "snapshot",
        "at": int(time.time()),
        "leaderboard": build_leaderboard(store),
        "presence": build_presence(store),
        "activity": build_activity(store),
    }


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def broadcast(payload: Dict[str, Any]) -> int:
    """Fan a payload out to every open connection. Returns the delivery count."""
    if _local_sink is not None:
        _local_sink(payload)
        return 1

    endpoint = config.WEBSOCKET_ENDPOINT
    if not endpoint:
        logger.info("No WEBSOCKET_ENDPOINT configured; dropping %s broadcast", payload.get("type"))
        return 0

    import boto3

    store = storage.get_store()
    client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint, region_name=config.AWS_REGION)
    body = json.dumps(payload).encode("utf-8")

    delivered = 0
    for connection_id in store.list_connections():
        try:
            client.post_to_connection(ConnectionId=connection_id, Data=body)
            delivered += 1
        except client.exceptions.GoneException:
            # The client went away without a clean $disconnect. Reap it.
            store.delete_connection(connection_id)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to deliver to connection %s", connection_id)
    return delivered


def broadcast_snapshot() -> int:
    return broadcast(build_snapshot())
