"""EventBridge emission (Part 4.3).

Domain events are emitted here instead of having the write path call the
broadcaster directly. The value is decoupling: `publish` does not know or care
who reacts to `challenge.published`, and adding a second consumer later (a
Slack notifier, an analytics sink) means adding a rule, not editing the handler.

Emission is deliberately best-effort — a failure to announce something must
never fail the write that already succeeded.
"""
import json
import logging
import time
from typing import Any, Dict, List, Optional

from common import config

logger = logging.getLogger(__name__)

SOURCE = "breakfix.app"

# Local mirror so the dev environment can react to the same events without
# EventBridge. Populated only when no event bus is configured.
_local_log: List[Dict[str, Any]] = []
_local_handlers: List[Any] = []


def subscribe(handler) -> None:
    """Register a local consumer (the dev stand-in for an EventBridge rule)."""
    _local_handlers.append(handler)


def recent(limit: int = 20) -> List[Dict[str, Any]]:
    return _local_log[-limit:][::-1]


def emit(detail_type: str, detail: Dict[str, Any]) -> bool:
    """Publish one domain event. Returns True if it was accepted somewhere."""
    envelope = {"source": SOURCE, "detail_type": detail_type, "detail": detail, "at": int(time.time())}

    if config.EVENT_BUS_NAME:
        try:
            import boto3

            client = boto3.client("events", region_name=config.AWS_REGION)
            client.put_events(Entries=[{
                "Source": SOURCE,
                "DetailType": detail_type,
                "Detail": json.dumps(detail),
                "EventBusName": config.EVENT_BUS_NAME,
            }])
            return True
        except Exception:  # noqa: BLE001 - announcing must never break the write
            logger.exception("Could not put event %s on the bus", detail_type)
            return False

    _local_log.append(envelope)
    del _local_log[:-100]
    for handler in list(_local_handlers):
        try:
            handler(envelope)
        except Exception:  # noqa: BLE001
            logger.exception("Local event handler failed for %s", detail_type)
    return True


def emit_high_score(result: Dict[str, Any], previous_best: Optional[int]) -> bool:
    """Emitted only when a submission genuinely beats the standing best."""
    score = int(result.get("score", 0))
    if previous_best is not None and score <= previous_best:
        return False
    return emit("highscore.set", {
        "challenge_id": result.get("challenge_id"),
        "user_display_name": result.get("user_display_name"),
        "score": score,
        "previous_best": previous_best,
        "time_taken_seconds": result.get("time_taken_seconds"),
        "correct": bool(result.get("correct")),
    })
