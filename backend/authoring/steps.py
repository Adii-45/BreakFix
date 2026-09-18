"""The live authoring pipeline, one function per Step Functions state (Part 3).

Same gates as the offline pipeline in seed-data/author_challenges.py, in the
same order, because the whole point is that a live-authored challenge is held to
the identical standard:

  fetch -> author tests -> verify against CLEAN -> inject bug -> verify the bug
  bites -> golden-set validation -> mission brief -> land in pending_review

Nothing here publishes. The terminal state is `pending_review`; a human clicks
publish, or the challenge stays invisible forever.
"""
import ast
import json
import time
import uuid
from typing import Any, Dict, List

from authoring import github, mutation
from common import storage
from test_runner import runner

STEPS = [
    ("fetch", "Fetch the function from GitHub"),
    ("author_tests", "Establish the hidden test cases"),
    ("verify_clean", "Verify the tests pass against the clean version"),
    ("inject_bug", "Inject one bug"),
    ("verify_bug", "Confirm the bug breaks a hidden test"),
    ("validate_golden", "Run golden-set validation"),
    ("write_brief", "Write the mission brief"),
    ("land_pending", "Land in pending_review"),
]
STEP_NAMES = [name for name, _ in STEPS]
STEP_LABELS = dict(STEPS)


class AuthoringError(RuntimeError):
    """A gate rejected the candidate challenge. The run stops here."""


# ---------------------------------------------------------------------------

def step_fetch(ctx: Dict[str, Any]) -> Dict[str, Any]:
    function_name = (ctx.get("function_name") or "").strip()
    if not function_name.isidentifier():
        raise AuthoringError("function_name must be a valid Python identifier.")

    pasted = (ctx.get("source_code") or "").strip()
    if pasted:
        # Adapted source pasted by the admin -- the escape hatch for functions
        # whose real module cannot run standalone.
        try:
            ast.parse(pasted)
        except SyntaxError as exc:
            raise AuthoringError(f"Pasted source is not valid Python: {exc}") from exc
        ctx["clean_code"] = pasted if pasted.endswith("\n") else pasted + "\n"
        ctx.setdefault("repo_name", ctx.get("repo_name") or "pasted-source")
        ctx.setdefault("repo_url", "")
        ctx.setdefault("source_path", "")
        ctx["fetched_from"] = "pasted"
    else:
        info = github.parse_url(ctx.get("github_url", ""))
        source = github.fetch_raw(info["raw_url"])
        code, meta = github.extract_function(source, function_name)
        ctx["clean_code"] = code
        ctx["repo_name"] = info["repo_name"]
        ctx["repo_url"] = info["repo_url"]
        ctx["source_path"] = info["path"]
        ctx["source_ref"] = info["ref"]
        ctx["arg_names"] = meta["arg_names"]
        ctx["fetched_from"] = "github"

    if f"def {function_name}" not in ctx["clean_code"]:
        raise AuthoringError(f"Extracted source does not define '{function_name}'.")
    return ctx


def step_author_tests(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Hidden tests come from the admin, or from Bedrock when it is reachable."""
    provided = ctx.get("test_cases")
    if provided:
        if isinstance(provided, str):
            try:
                provided = json.loads(provided)
            except json.JSONDecodeError as exc:
                raise AuthoringError(f"test_cases is not valid JSON: {exc}") from exc
        if not isinstance(provided, list) or not provided:
            raise AuthoringError("test_cases must be a non-empty JSON array.")
        if not 2 <= len(provided) <= 6:
            raise AuthoringError(f"Provide between 2 and 6 test cases (got {len(provided)}).")
        for index, case in enumerate(provided):
            if not isinstance(case, dict) or "input" not in case or "expected_output" not in case:
                raise AuthoringError(f"Test case {index + 1} needs both 'input' and 'expected_output'.")
            case.setdefault("name", f"case {index + 1}")
        ctx["test_cases"] = provided
        ctx["tests_source"] = "admin-provided"
        return ctx

    from agents import test_author

    ctx["test_cases"] = test_author.propose_tests(
        clean_code=ctx["clean_code"], function_name=ctx["function_name"],
    )
    ctx["tests_source"] = "test-author-agent"
    return ctx


def step_verify_clean(ctx: Dict[str, Any]) -> Dict[str, Any]:
    result = runner.run_tests(ctx["clean_code"], ctx["function_name"], ctx["test_cases"])
    ctx["clean_result"] = {"passed": result["tests_passed"], "total": result["tests_total"]}
    if result["tests_passed"] != result["tests_total"]:
        failures = [f"{t['name']}: {t['error']}" for t in result["per_test"] if not t["passed"]]
        raise AuthoringError(
            "The hidden tests do not pass against the clean function, so they cannot be trusted "
            "as ground truth. " + " | ".join(failures[:3])
        )
    return ctx


def step_inject_bug(ctx: Dict[str, Any]) -> Dict[str, Any]:
    from agents import bug_injector

    category = ctx.get("bug_category") or "off-by-one"
    try:
        injected = bug_injector.inject_bug(ctx["clean_code"], ctx["function_name"], category)
        ctx["buggy_code"] = injected["buggy_code"]
        ctx["ground_truth"] = {
            "bug_category": injected["bug_category"],
            "diff_summary": injected["diff_summary"],
            "why_its_a_bug": injected["why_its_a_bug"],
            "hint_level_description": injected.get("hint_level_description", ""),
            "generated_by": f"bug-injector-agent ({injected['transport']})",
        }
        ctx["injection_source"] = "bug-injector-agent"
        return ctx
    except Exception as exc:  # noqa: BLE001
        ctx["injector_error"] = f"{type(exc).__name__}: {exc}"

    # Deterministic fallback, clearly labelled -- never passed off as the agent.
    chosen = mutation.inject(
        ctx["clean_code"], ctx["function_name"], ctx["test_cases"],
        lambda code, entry, cases: runner.run_tests(code, entry, cases),
    )
    if chosen is None:
        raise AuthoringError(
            "Neither the Bug Injector Agent nor the deterministic mutation fallback could "
            f"produce a bug that breaks a hidden test. Agent error: {ctx.get('injector_error')}"
        )
    ctx["buggy_code"] = chosen["buggy_code"]
    ctx["ground_truth"] = {
        "bug_category": chosen["bug_category"],
        "diff_summary": chosen["diff_summary"],
        "why_its_a_bug": chosen["why_its_a_bug"],
        "hint_level_description": chosen["hint_level_description"],
        "generated_by": "mutation-fallback",
    }
    ctx["injection_source"] = "mutation-fallback"
    return ctx


def step_verify_bug(ctx: Dict[str, Any]) -> Dict[str, Any]:
    result = runner.run_tests(ctx["buggy_code"], ctx["function_name"], ctx["test_cases"])
    failing = result["tests_total"] - result["tests_passed"]
    ctx["buggy_result"] = {"passed": result["tests_passed"], "total": result["tests_total"]}
    if failing == 0:
        raise AuthoringError(
            "The injected bug does not fail a single hidden test, so it is undetectable. Discarded."
        )
    return ctx


def step_validate_golden(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """The same golden-set shape the seed challenges must satisfy (PRD 12.3)."""
    fn, tests = ctx["function_name"], ctx["test_cases"]
    checks: List[Dict[str, Any]] = []

    exact = runner.run_tests(ctx["clean_code"], fn, tests)
    checks.append({"case": "exact ground-truth fix", "expected": "all pass",
                   "ok": exact["tests_passed"] == exact["tests_total"],
                   "detail": f"{exact['tests_passed']}/{exact['tests_total']}"})

    unchanged = runner.run_tests(ctx["buggy_code"], fn, tests)
    checks.append({"case": "no change submitted", "expected": "same failures as the buggy version",
                   "ok": unchanged["tests_passed"] < unchanged["tests_total"],
                   "detail": f"{unchanged['tests_passed']}/{unchanged['tests_total']}"})

    broken = runner.run_tests(f"def {fn}(*a, **k)\n    return None\n", fn, tests)
    checks.append({"case": "broken change (syntax error)", "expected": "reported as failing, not a crash",
                   "ok": broken["tests_passed"] == 0 and broken["runner_status"] == "load_error",
                   "detail": broken["runner_status"]})

    looping = runner.run_tests(f"def {fn}(*a, **k):\n    while True:\n        pass\n", fn, tests)
    checks.append({"case": "broken change (infinite loop)", "expected": "terminated by the sandbox",
                   "ok": looping["tests_passed"] == 0,
                   "detail": looping["runner_status"]})

    ctx["golden_checks"] = checks
    failed = [c for c in checks if not c["ok"]]
    if failed:
        raise AuthoringError("Golden-set validation failed: " + "; ".join(c["case"] for c in failed))
    return ctx


def step_write_brief(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Mission brief. If neither the agent nor the admin supplies one, the
    challenge still lands -- but it cannot be published until a human writes it."""
    from agents import brief_writer

    summary = (ctx.get("student_facing_summary") or "").strip()
    symptom = (ctx.get("symptom_description") or "").strip()

    if not (summary and symptom):
        try:
            brief = brief_writer.write_brief(
                repo_name=ctx.get("repo_name", ""), source_path=ctx.get("source_path", ""),
                function_name=ctx["function_name"], clean_code=ctx["clean_code"],
                buggy_code=ctx["buggy_code"], ground_truth=ctx["ground_truth"],
            )
            summary = brief["student_facing_summary"]
            symptom = brief["symptom_description"]
            ctx["brief_source"] = brief["generated_by"]
        except Exception as exc:  # noqa: BLE001
            ctx["brief_error"] = f"{type(exc).__name__}: {exc}"
            ctx["brief_source"] = "missing"
            ctx["student_facing_summary"] = ""
            ctx["symptom_description"] = ""
            return ctx
    else:
        ctx["brief_source"] = "admin-provided"

    # Whoever wrote it, it is leak-checked before a student can ever see it.
    brief_writer.assert_no_leak(
        {"purpose": summary, "symptom": symptom},
        ctx["ground_truth"], ctx["clean_code"], ctx["buggy_code"],
    )
    ctx["student_facing_summary"] = summary
    ctx["symptom_description"] = symptom
    return ctx


def step_land_pending(ctx: Dict[str, Any]) -> Dict[str, Any]:
    from agents import brief_writer

    challenge_id = ctx.get("challenge_id") or f"live-{uuid.uuid4().hex[:8]}"
    preview = "\n".join([l for l in ctx["buggy_code"].splitlines() if l.strip()][:4])

    record = {
        "challenge_id": challenge_id,
        "repo_name": ctx.get("repo_name", "pasted-source"),
        "repo_url": ctx.get("repo_url", ""),
        "source_path": ctx.get("source_path", ""),
        "function_name": ctx["function_name"],
        "buggy_code": ctx["buggy_code"],
        "clean_code": ctx["clean_code"],
        "ground_truth_diff": json.dumps(ctx["ground_truth"], indent=2),
        "difficulty": ctx.get("difficulty", "medium"),
        "bug_category": ctx["ground_truth"].get("bug_category", "unknown"),
        "test_cases": json.dumps(ctx["test_cases"]),
        "tests_total": len(ctx["test_cases"]),
        "code_preview": preview,
        "language": "python",
        "time_limit_seconds": int(ctx.get("time_limit_seconds", 300)),
        "student_facing_summary": ctx.get("student_facing_summary", ""),
        "symptom_description": ctx.get("symptom_description", ""),
        "source_url": brief_writer.source_url(ctx.get("repo_url", ""), ctx.get("source_path", "")),
        # The gate. Invisible to students until a human clicks publish.
        "status": "pending_review",
        "created_at": int(time.time()),
        "authored_by": "live-pipeline",
        "injection_source": ctx.get("injection_source", "unknown"),
        "tests_source": ctx.get("tests_source", "unknown"),
        "brief_source": ctx.get("brief_source", "unknown"),
    }
    storage.get_store().put_challenge(record)
    ctx["challenge_id"] = challenge_id
    ctx["landed"] = True
    return ctx


HANDLERS = {
    "fetch": step_fetch,
    "author_tests": step_author_tests,
    "verify_clean": step_verify_clean,
    "inject_bug": step_inject_bug,
    "verify_bug": step_verify_bug,
    "validate_golden": step_validate_golden,
    "write_brief": step_write_brief,
    "land_pending": step_land_pending,
}


def run_step(name: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    if name not in HANDLERS:
        raise AuthoringError(f"Unknown authoring step '{name}'.")
    return HANDLERS[name](ctx)
