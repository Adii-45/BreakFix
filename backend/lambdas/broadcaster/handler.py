"""DynamoDB Streams -> WebSocket broadcaster (Part 2).

Wired to the streams on the Sessions and Results tables. This is the reason the
UI is genuinely event-driven rather than polled: a write to either table is what
causes the push, and nothing runs in between.

  Sessions write  -> presence changed (someone started or finished an attempt)
  Results write   -> leaderboard changed, and a real activity event occurred

The payload is rebuilt from the tables rather than from the stream record, so
what every client receives is the committed state, not a guess assembled from a
single row.
"""
import logging
import time

from common import realtime

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):  # noqa: ANN001
    records = event.get("Records", [])
    touched_sessions = False
    touched_results = False

    for record in records:
        source = (record.get("eventSourceARN") or "").lower()
        if "breakfix-sessions" in source:
            touched_sessions = True
        elif "breakfix-results" in source:
            touched_results = True

    if not records:
        return {"delivered": 0, "reason": "no records"}

    payload = {"type": "update", "at": int(time.time())}
    if touched_results:
        payload["leaderboard"] = realtime.build_leaderboard()
        payload["activity"] = realtime.build_activity()
    if touched_sessions or touched_results:
        # A finished attempt flips a session out of in_progress, so a Results
        # write changes presence too.
        payload["presence"] = realtime.build_presence()

    delivered = realtime.broadcast(payload)
    logger.info("broadcast %s to %d connection(s)", list(payload.keys()), delivered)
    return {"delivered": delivered, "keys": list(payload.keys())}
