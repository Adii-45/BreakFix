"""Execution tracking for the authoring pipeline (Part 3).

In AWS the state machine is AWS Step Functions; each state invokes the authoring
Lambda with a step name, and progress is read back with DescribeExecution /
GetExecutionHistory.

Locally the same `steps.run_step` functions are driven in order on a background
thread. Either way the execution record has the same shape, so the admin screen
does not care which one produced it — and every step transition is pushed over
the same WebSocket channel the rest of the live layer uses.
"""
import threading
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional

from authoring import steps
from common import realtime

_EXECUTIONS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()
MAX_RETAINED = 25


def new_execution(inputs: Dict[str, Any]) -> Dict[str, Any]:
    execution_id = f"exec-{uuid.uuid4().hex[:10]}"
    record = {
        "execution_id": execution_id,
        "status": "RUNNING",
        "started_at": int(time.time()),
        "finished_at": None,
        "function_name": inputs.get("function_name", ""),
        "github_url": inputs.get("github_url", ""),
        "challenge_id": None,
        "error": None,
        "steps": [
            {"name": name, "label": steps.STEP_LABELS[name], "status": "PENDING",
             "started_at": None, "finished_at": None, "detail": None}
            for name in steps.STEP_NAMES
        ],
    }
    with _LOCK:
        _EXECUTIONS[execution_id] = record
        if len(_EXECUTIONS) > MAX_RETAINED:
            for stale in sorted(_EXECUTIONS, key=lambda k: _EXECUTIONS[k]["started_at"])[:-MAX_RETAINED]:
                _EXECUTIONS.pop(stale, None)
    return record


def get(execution_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        record = _EXECUTIONS.get(execution_id)
        return dict(record) if record else None


def recent(limit: int = 10) -> List[Dict[str, Any]]:
    with _LOCK:
        rows = sorted(_EXECUTIONS.values(), key=lambda r: r["started_at"], reverse=True)
        return [dict(r) for r in rows[:limit]]


def _publish(record: Dict[str, Any]) -> None:
    """Push the execution state to the admin screen over the live channel."""
    try:
        realtime.broadcast({"type": "authoring", "execution": record})
    except Exception:  # noqa: BLE001
        pass


def _update_step(execution_id: str, index: int, **fields) -> Dict[str, Any]:
    with _LOCK:
        record = _EXECUTIONS[execution_id]
        record["steps"][index].update(fields)
        snapshot = dict(record)
    _publish(snapshot)
    return snapshot


def _finish(execution_id: str, status: str, error: Optional[str], challenge_id: Optional[str]) -> Dict[str, Any]:
    with _LOCK:
        record = _EXECUTIONS[execution_id]
        record["status"] = status
        record["error"] = error
        record["challenge_id"] = challenge_id
        record["finished_at"] = int(time.time())
        snapshot = dict(record)
    _publish(snapshot)
    return snapshot


def run_locally(execution_id: str, ctx: Dict[str, Any]) -> None:
    """Drive every step in order, stopping at the first gate that rejects."""
    for index, name in enumerate(steps.STEP_NAMES):
        _update_step(execution_id, index, status="RUNNING", started_at=int(time.time()))
        try:
            ctx = steps.run_step(name, ctx)
        except steps.AuthoringError as exc:
            _update_step(execution_id, index, status="FAILED", finished_at=int(time.time()), detail=str(exc))
            _finish(execution_id, "FAILED", str(exc), None)
            return
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            _update_step(execution_id, index, status="FAILED", finished_at=int(time.time()), detail=detail)
            _finish(execution_id, "FAILED", detail, None)
            return
        _update_step(execution_id, index, status="SUCCEEDED", finished_at=int(time.time()),
                     detail=_detail_for(name, ctx))
    _finish(execution_id, "SUCCEEDED", None, ctx.get("challenge_id"))


def _detail_for(name: str, ctx: Dict[str, Any]) -> str:
    if name == "fetch":
        return f"{ctx.get('repo_name')} · {len(ctx.get('clean_code', ''))} bytes ({ctx.get('fetched_from')})"
    if name == "author_tests":
        return f"{len(ctx.get('test_cases', []))} hidden tests ({ctx.get('tests_source')})"
    if name == "verify_clean":
        r = ctx.get("clean_result", {})
        return f"clean passes {r.get('passed')}/{r.get('total')}"
    if name == "inject_bug":
        return f"{ctx['ground_truth'].get('bug_category')} via {ctx.get('injection_source')}"
    if name == "verify_bug":
        r = ctx.get("buggy_result", {})
        return f"buggy passes {r.get('passed')}/{r.get('total')} — bug confirmed"
    if name == "validate_golden":
        return f"{len(ctx.get('golden_checks', []))}/{len(ctx.get('golden_checks', []))} golden cases OK"
    if name == "write_brief":
        return f"brief: {ctx.get('brief_source')}"
    if name == "land_pending":
        return f"{ctx.get('challenge_id')} → pending_review"
    return ""


def start_local(inputs: Dict[str, Any]) -> Dict[str, Any]:
    record = new_execution(inputs)
    thread = threading.Thread(target=run_locally, args=(record["execution_id"], dict(inputs)), daemon=True)
    thread.start()
    return record
