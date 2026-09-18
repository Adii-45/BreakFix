"""Evaluator Agent (PRD Section 8.2).

Runs live on every submission, but ONLY after the Test Runner has already
produced a deterministic pass/fail. This module cannot change `correct` -- that
value is computed upstream in the submit handler as tests_passed == tests_total
and is never passed back through here.

Two mechanical guarantees on top of the prompt's "Do NOT contradict the test
outcome" instruction, because a prompt is a request and this is a demo:

  1. The agent returns no `correct` field, and the handler ignores it if one
     appears anyway.
  2. `score` is clamped into the band the test outcome allows (Section 8.2
     rubric): tests passing -> 60..100, tests failing -> 0..50. A model that
     tries to award 95 to a failing submission is corrected in code.
"""
import logging
from typing import Any, Dict, List, Optional

from agents import bedrock_client
from common import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """A student attempted to fix an injected bug. Hidden unit tests have
ALREADY been run against their submission - you are given the result as
fact, not something to judge yourself. You are given: the buggy code, the
ground-truth explanation of the bug, the student's submitted code, and
the test outcome (tests_passed / tests_total, per-test detail).
Your job is ONLY to explain and score quality, using the test outcome
as ground truth:
  1) If tests passed: is the fix minimal and targeted (good) or a broad
     rewrite that happens to work (lower quality signal)?
  2) If tests failed: does the diff show they misdiagnosed the bug
     entirely, masked a symptom without fixing the root cause, or were
     on the right track but incomplete?
Do NOT contradict the given test outcome. Return JSON:
{ score, process_feedback, correctness_notes }
process_feedback and correctness_notes must each be 1-2 sentences,
specific to this submission - never generic praise or generic criticism.

Scoring rubric:
  100    = tests pass with a minimal, targeted fix
  60-80  = tests pass but the fix is broader than necessary
  20-50  = tests fail but the approach was on the right track
  0      = tests fail and the approach missed the actual bug entirely"""

USER_TEMPLATE = """TEST OUTCOME (ground truth, not open to your judgement):
  tests_passed: {tests_passed} / {tests_total}
  per-test detail:
{per_test_block}
{runner_note}
GROUND-TRUTH BUG (hidden from the student):
{ground_truth_diff}

BUGGY CODE THE STUDENT WAS GIVEN:
```python
{buggy_code}
```

STUDENT'S SUBMISSION:
```python
{submitted_code}
```

STUDENT'S DIFF AGAINST THE BUGGY CODE ({lines_changed} line(s) touched):
```diff
{student_diff}
```

Return ONLY the JSON object described in your instructions."""

REQUIRED_KEYS = ["score", "process_feedback", "correctness_notes"]


def _per_test_block(per_test: List[Dict]) -> str:
    if not per_test:
        return "    (no tests ran)"
    lines = []
    for t in per_test:
        status = "PASS" if t.get("passed") else f"FAIL/{t.get('kind', 'error')}"
        detail = f" - {t['error']}" if t.get("error") else ""
        lines.append(f"    [{status}] {t.get('name', 'test')}{detail}")
    return "\n".join(lines)


def _clamp_to_outcome(score: int, all_passed: bool) -> int:
    """Enforce the rubric bands so the score can never imply the wrong verdict."""
    score = max(0, min(100, score))
    return max(60, score) if all_passed else min(50, score)


def evaluate(
    buggy_code: str,
    ground_truth_diff: str,
    submitted_code: str,
    test_result: Dict[str, Any],
    student_diff: str,
    diff_stats: Dict[str, int],
) -> Dict[str, Any]:
    """Qualitative layer only. Always returns a usable dict -- never raises."""
    tests_passed = int(test_result.get("tests_passed", 0))
    tests_total = int(test_result.get("tests_total", 0))
    all_passed = tests_total > 0 and tests_passed == tests_total

    runner_status = test_result.get("runner_status")
    runner_note = ""
    if runner_status == "timeout":
        runner_note = "\nNOTE: the submission was terminated by the sandbox timeout (likely an infinite loop).\n"
    elif runner_status in ("load_error", "crashed"):
        runner_note = f"\nNOTE: the submission could not be loaded or run: {test_result.get('load_error')}\n"

    user_text = USER_TEMPLATE.format(
        tests_passed=tests_passed,
        tests_total=tests_total,
        per_test_block=_per_test_block(test_result.get("per_test", [])),
        runner_note=runner_note,
        ground_truth_diff=ground_truth_diff,
        buggy_code=buggy_code,
        submitted_code=submitted_code or "(empty submission)",
        student_diff=student_diff or "(no changes made to the buggy code)",
        lines_changed=diff_stats.get("lines_changed", 0),
    )

    try:
        raw, transport = bedrock_client.invoke(SYSTEM_PROMPT, user_text)
        parsed = bedrock_client.parse_json_response(raw, REQUIRED_KEYS)
        return {
            "score": _clamp_to_outcome(_as_int(parsed["score"]), all_passed),
            "process_feedback": _clean(parsed["process_feedback"]),
            "correctness_notes": _clean(parsed["correctness_notes"]),
            "feedback_source": transport,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Evaluator Agent unavailable (%s); using deterministic fallback", exc)
        if not config.ALLOW_EVALUATOR_FALLBACK:
            raise
        result = fallback_evaluate(test_result, diff_stats, student_diff)
        result["feedback_source"] = "fallback-heuristic"
        return result


def _as_int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _clean(value: Any) -> str:
    text = str(value).strip()
    return text if text else "No feedback was produced for this submission."


def fallback_evaluate(
    test_result: Dict[str, Any],
    diff_stats: Dict[str, int],
    student_diff: str,
) -> Dict[str, Any]:
    """Deterministic stand-in used when Bedrock cannot be reached.

    This is NOT the Evaluator Agent and is labelled as such in the API response
    (`feedback_source: "fallback-heuristic"`). It exists so that a Bedrock
    outage during the live demo degrades the feedback text rather than breaking
    the submit flow. Correctness is unaffected either way -- it comes from the
    Test Runner.
    """
    passed = int(test_result.get("tests_passed", 0))
    total = int(test_result.get("tests_total", 0))
    all_passed = total > 0 and passed == total
    changed = diff_stats.get("lines_changed", 0)
    status = test_result.get("runner_status")

    # A submission is "broken" when nothing ran -- it timed out, was blocked by
    # the sandbox, or raised before producing an answer. That is a different
    # thing from a wrong answer, and PRD 12.3 scores it 0 rather than partial
    # credit. Keyed off the per-test kinds because a per-test alarm can fire
    # without the whole run hitting the wall-clock timeout.
    kinds = [t.get("kind") for t in test_result.get("per_test", [])]
    broken = bool(kinds) and passed == 0 and not any(k == "mismatch" for k in kinds)
    broken_kind = next((k for k in kinds if k in ("timeout", "blocked", "error")), "error")

    if all_passed:
        if changed <= 2:
            score, process = 100, (
                f"All {total} hidden tests pass and the fix touched only {changed} line(s) -- "
                "a minimal, targeted change that points straight at the root cause."
            )
        elif changed <= 6:
            score, process = 80, (
                f"All {total} hidden tests pass, but the change spans {changed} lines; "
                "a tighter edit would show a sharper diagnosis."
            )
        else:
            # Still >= 70: a correct fix by a different valid approach is a good
            # outcome, just a weaker signal about the diagnosis (PRD 12.3).
            score, process = 72, (
                f"All {total} hidden tests pass, but {changed} lines were rewritten -- "
                "closer to a rewrite than a targeted fix, so it says less about the diagnosis."
            )
        notes = f"Every hidden test passed ({passed}/{total}), so the submitted behaviour matches the reference."
    elif not student_diff.strip():
        score = 0
        process = "No change was made to the buggy code, so there is no debugging process to assess."
        notes = f"The submission is identical to the buggy version; the same {total - passed} test(s) still fail."
    elif broken or status in ("timeout", "crashed", "unavailable") or test_result.get("load_error"):
        score = 0
        reason = {
            "timeout": "it never terminated -- the sandbox timed it out",
            "blocked": "it tried to do something the sandbox blocks (network, filesystem or process access)",
            "error": "it raised before returning a value",
        }.get(broken_kind, "it could not be executed")
        process = (
            f"This submission is broken rather than merely incorrect: {reason}. "
            "No hidden test got far enough to judge the diagnosis."
        )
        detail = test_result.get("load_error") or next(
            (t.get("error") for t in test_result.get("per_test", []) if t.get("error")), "execution was terminated"
        )
        notes = f"The sandbox reported: {detail}"
    elif passed > 0:
        score = 40
        process = (
            f"{passed} of {total} hidden tests pass, so the change moved in the right direction "
            "but did not fully resolve the defect."
        )
        notes = f"{total - passed} test(s) still fail -- part of the faulty behaviour remains."
    else:
        score = 20
        process = (
            f"The code was changed across {changed} line(s), but no hidden test passes -- "
            "the edit does not appear to target the real defect."
        )
        notes = f"All {total} hidden tests still fail after the change."

    return {"score": score, "process_feedback": process, "correctness_notes": notes}
