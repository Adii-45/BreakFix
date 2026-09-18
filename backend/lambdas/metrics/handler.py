"""GET /system-status — real CloudWatch metrics (Part 4.2).

Reads actual CloudWatch metrics for the deployed Lambdas. There is no synthetic
fallback: when CloudWatch cannot be reached, or the functions have never been
invoked, the response says so explicitly and the UI renders "unavailable"
rather than a plausible-looking number.
"""
import logging
from datetime import datetime, timedelta, timezone

from common import config, http

logger = logging.getLogger()
logger.setLevel(logging.INFO)

WATCHED = [
    ("breakfix-submit", "Submit pipeline"),
    ("breakfix-test-runner", "Test Runner"),
    ("breakfix-broadcaster", "Live broadcaster"),
]


def _series(client, function_name, metric, stat, start, end, period):
    response = client.get_metric_statistics(
        Namespace="AWS/Lambda",
        MetricName=metric,
        Dimensions=[{"Name": "FunctionName", "Value": function_name}],
        StartTime=start,
        EndTime=end,
        Period=period,
        Statistics=[stat],
    )
    points = sorted(response.get("Datapoints", []), key=lambda d: d["Timestamp"])
    return [p[stat] for p in points]


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    if not config.METRICS_ENABLED:
        return http.ok({"available": False, "reason": "Metrics collection is disabled."})

    try:
        import boto3

        client = boto3.client("cloudwatch", region_name=config.AWS_REGION)
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=config.METRICS_WINDOW_MINUTES)
        period = 300

        functions = []
        for name, label in WATCHED:
            invocations = _series(client, name, "Invocations", "Sum", start, end, period)
            durations = _series(client, name, "Duration", "Average", start, end, period)
            errors = _series(client, name, "Errors", "Sum", start, end, period)
            functions.append({
                "function_name": name,
                "label": label,
                "invocations": int(sum(invocations)) if invocations else 0,
                "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
                "errors": int(sum(errors)) if errors else 0,
                "has_data": bool(invocations or durations),
            })

        return http.ok({
            "available": True,
            "window_minutes": config.METRICS_WINDOW_MINUTES,
            "region": config.AWS_REGION,
            "functions": functions,
        })
    except Exception as exc:  # noqa: BLE001
        logger.warning("CloudWatch unavailable: %s", exc)
        return http.ok({
            "available": False,
            "reason": f"CloudWatch metrics are not reachable from this environment ({type(exc).__name__}).",
        })
