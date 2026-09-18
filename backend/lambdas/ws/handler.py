"""API Gateway WebSocket route handlers (Part 2).

$connect     -- record the connection id
$disconnect  -- forget it
$default     -- a client asking for a fresh snapshot

On connect the client gets the current snapshot immediately, so it renders real
state without a REST round-trip and without polling.
"""
import json
import logging

from common import realtime, storage

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _connection_id(event):
    return (event.get("requestContext") or {}).get("connectionId")


def connect(event, context):  # noqa: ANN001
    connection_id = _connection_id(event)
    storage.get_store().put_connection(
        connection_id,
        {"connected_at": int((event.get("requestContext") or {}).get("requestTimeEpoch", 0) / 1000)},
    )
    logger.info("ws connect %s", connection_id)
    return {"statusCode": 200, "body": "connected"}


def disconnect(event, context):  # noqa: ANN001
    connection_id = _connection_id(event)
    storage.get_store().delete_connection(connection_id)
    logger.info("ws disconnect %s", connection_id)
    return {"statusCode": 200, "body": "disconnected"}


def default(event, context):  # noqa: ANN001
    """Any inbound frame is treated as "send me the current state"."""
    import boto3

    from common import config

    connection_id = _connection_id(event)
    snapshot = realtime.build_snapshot()

    endpoint = config.WEBSOCKET_ENDPOINT
    if endpoint and connection_id:
        client = boto3.client("apigatewaymanagementapi", endpoint_url=endpoint, region_name=config.AWS_REGION)
        try:
            client.post_to_connection(ConnectionId=connection_id, Data=json.dumps(snapshot).encode("utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("Could not reply to %s", connection_id)
    return {"statusCode": 200, "body": "ok"}
