"""API Gateway (REST, proxy integration) request/response helpers."""
import json
import logging
from typing import Any, Dict, Optional, Tuple

from common import config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_BASE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": config.CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Cache-Control": "no-store",
}


def respond(status: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": dict(_BASE_HEADERS),
        "body": json.dumps(body, default=str),
    }


def ok(body: Any) -> Dict[str, Any]:
    return respond(200, body)


def error(status: int, message: str, **extra: Any) -> Dict[str, Any]:
    payload = {"error": message}
    payload.update(extra)
    return respond(status, payload)


def parse_body(event: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Returns (parsed_body, error_response). Exactly one is non-None."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            return None, error(400, "Request body could not be decoded.")
    if not raw.strip():
        return None, error(400, "Request body is required.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, error(400, "Request body must be valid JSON.")
    if not isinstance(parsed, dict):
        return None, error(400, "Request body must be a JSON object.")
    return parsed, None


def path_param(event: Dict[str, Any], name: str) -> Optional[str]:
    return (event.get("pathParameters") or {}).get(name)


def handle_exceptions(fn):
    """Never leak a stack trace to the client; never return a bare 502."""

    def wrapper(event, context):  # noqa: ANN001
        try:
            return fn(event, context)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Unhandled error in %s", getattr(fn, "__module__", "handler"))
            return error(500, "Internal error. Please retry.")

    wrapper.__name__ = getattr(fn, "__name__", "handler")
    return wrapper
