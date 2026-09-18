"""Step Functions task handler (Part 3).

One Lambda, one state per authoring step. The state machine passes `step` in the
payload and threads the context between states, so the ASL definition mirrors
seed-data/author_challenges.py one-for-one and a failure at any gate stops the
execution with a real error.
"""
import logging

from authoring import steps

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):  # noqa: ANN001
    step = event.get("step")
    ctx = event.get("context") or {}
    logger.info("authoring step %s for %s", step, ctx.get("function_name"))
    try:
        ctx = steps.run_step(step, ctx)
    except steps.AuthoringError as exc:
        # Surfaced to the admin screen as a real, readable rejection.
        raise RuntimeError(f"GateRejected: {exc}") from exc
    return {"step": step, "context": ctx}
