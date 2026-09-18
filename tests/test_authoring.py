"""Live authoring pipeline tests (Part 3).

The gates are the product here. Each one must reject bad input rather than let a
half-baked challenge through, and the terminal state must be pending_review --
never published.
"""
import json

import pytest

from authoring import github, mutation, steps
from test_runner import runner

CLEAN = (
    "def clamp(value, low, high):\n"
    "    if value < low:\n"
    "        return low\n"
    "    if value > high:\n"
    "        return high\n"
    "    return value\n"
)
TESTS = [
    {"name": "below the floor", "input": [-5, 0, 10], "expected_output": 0},
    {"name": "inside the range", "input": [5, 0, 10], "expected_output": 5},
    {"name": "above the ceiling", "input": [50, 0, 10], "expected_output": 10},
]


def ctx(**overrides):
    base = {"function_name": "clamp", "source_code": CLEAN, "test_cases": [dict(t) for t in TESTS]}
    base.update(overrides)
    return base


# --- URL parsing -----------------------------------------------------------

def test_parses_a_github_blob_url():
    info = github.parse_url("https://github.com/python/cpython/blob/main/Lib/shlex.py")
    assert info["repo_name"] == "python/cpython"
    assert info["path"] == "Lib/shlex.py"
    assert info["raw_url"].startswith("https://raw.githubusercontent.com/")


def test_parses_a_raw_github_url():
    info = github.parse_url("https://raw.githubusercontent.com/django/django/main/django/utils/text.py")
    assert info["repo_name"] == "django/django"


@pytest.mark.parametrize("url", ["", "not a url", "https://gitlab.com/a/b/blob/main/x.py"])
def test_rejects_a_non_github_url(url):
    with pytest.raises(github.FetchError):
        github.parse_url(url)


# --- function extraction ---------------------------------------------------

SOURCE = (
    "import re\n"
    "from . helpers import thing\n"
    "UNUSED = 1\n"
    "PATTERN = re.compile('x')\n"
    "\n"
    "def wanted(a):\n"
    "    return PATTERN.sub('', a)\n"
    "\n"
    "def other(b):\n"
    "    return thing(b)\n"
)


def test_extraction_pulls_in_only_the_imports_and_constants_it_needs():
    code, meta = github.extract_function(SOURCE, "wanted")
    assert "import re" in code
    assert "PATTERN = re.compile" in code
    assert "UNUSED" not in code, "unrelated module constants stay behind"
    assert "def other" not in code
    assert meta["arg_names"] == ["a"]


def test_extraction_reports_a_missing_function_with_the_available_names():
    with pytest.raises(github.FetchError, match="wanted2"):
        github.extract_function(SOURCE, "wanted2")


def test_extraction_refuses_a_function_needing_intra_package_imports():
    """The single most common reason a real library function cannot run standalone."""
    with pytest.raises(github.FetchError, match="intra-package"):
        github.extract_function(SOURCE, "other")


# --- mutation fallback -----------------------------------------------------

def test_mutation_finds_a_bug_that_breaks_some_but_not_all_tests():
    chosen = mutation.inject(CLEAN, "clamp", TESTS, runner.run_tests)
    assert chosen is not None
    assert chosen["generated_by"] == "mutation-fallback"
    result = runner.run_tests(chosen["buggy_code"], "clamp", TESTS)
    assert 0 < result["tests_passed"] < result["tests_total"]


def test_mutation_candidates_are_all_parseable_and_different():
    import ast
    candidates = mutation.generate_candidates(CLEAN)
    assert len(candidates) >= 3
    for candidate in candidates:
        ast.parse(candidate["buggy_code"])
        assert candidate["buggy_code"].strip() != CLEAN.strip()


# --- the gates -------------------------------------------------------------

def test_fetch_accepts_pasted_source(store):
    out = steps.step_fetch(ctx())
    assert "def clamp" in out["clean_code"]
    assert out["fetched_from"] == "pasted"


def test_fetch_rejects_a_bad_identifier(store):
    with pytest.raises(steps.AuthoringError, match="identifier"):
        steps.step_fetch(ctx(function_name="not a name"))


def test_fetch_rejects_unparseable_pasted_source(store):
    with pytest.raises(steps.AuthoringError, match="not valid Python"):
        steps.step_fetch(ctx(source_code="def broken(:\n  pass\n"))


def test_fetch_rejects_source_missing_the_named_function(store):
    with pytest.raises(steps.AuthoringError, match="does not define"):
        steps.step_fetch(ctx(source_code="def something_else():\n    return 1\n"))


def test_author_tests_rejects_too_few_cases(store):
    with pytest.raises(steps.AuthoringError, match="between 2 and 6"):
        steps.step_author_tests(ctx(test_cases=[TESTS[0]]))


def test_author_tests_rejects_a_case_missing_expected_output(store):
    with pytest.raises(steps.AuthoringError, match="expected_output"):
        steps.step_author_tests(ctx(test_cases=[{"input": [1]}, {"input": [2], "expected_output": 2}]))


def test_author_tests_accepts_a_json_string(store):
    out = steps.step_author_tests(ctx(test_cases=json.dumps(TESTS)))
    assert len(out["test_cases"]) == 3
    assert out["tests_source"] == "admin-provided"


def test_verify_clean_rejects_tests_that_do_not_hold(store):
    bad = [{"name": "wrong", "input": [5, 0, 10], "expected_output": 999},
           {"name": "ok", "input": [5, 0, 10], "expected_output": 5}]
    state = steps.step_author_tests(steps.step_fetch(ctx(test_cases=bad)))
    with pytest.raises(steps.AuthoringError, match="cannot be trusted"):
        steps.step_verify_clean(state)


def test_verify_bug_rejects_a_bug_that_breaks_nothing(store):
    state = steps.step_verify_clean(steps.step_author_tests(steps.step_fetch(ctx())))
    state["buggy_code"] = CLEAN                      # identical -> undetectable
    with pytest.raises(steps.AuthoringError, match="undetectable"):
        steps.step_verify_bug(state)


def test_golden_validation_runs_all_four_cases(store):
    state = steps.step_verify_clean(steps.step_author_tests(steps.step_fetch(ctx())))
    state = steps.step_verify_bug(steps.step_inject_bug(state))
    state = steps.step_validate_golden(state)
    assert len(state["golden_checks"]) == 4
    assert all(c["ok"] for c in state["golden_checks"])


def test_a_full_run_lands_in_pending_review_not_published(store):
    state = ctx(
        student_facing_summary="Constrains a number so it never falls outside the given range, which is what the caller relies on.",
        symptom_description="Values at the extremes come back with an unexpected result.",
    )
    for name in steps.STEP_NAMES:
        state = steps.run_step(name, state)

    stored = store.get_challenge(state["challenge_id"])
    assert stored["status"] == "pending_review", "a live-authored challenge must never self-publish"
    assert stored["tests_total"] == 3
    assert stored["injection_source"] in ("bug-injector-agent", "mutation-fallback")
    assert stored["student_facing_summary"]


def test_a_pending_challenge_is_absent_from_the_public_catalogue(store):
    state = ctx(
        student_facing_summary="Constrains a number so it never falls outside the given range, which is what the caller relies on.",
        symptom_description="Values at the extremes come back with an unexpected result.",
    )
    for name in steps.STEP_NAMES:
        state = steps.run_step(name, state)

    from conftest import api_event, parse
    from lambdas.challenges import handler as challenges_handler

    _, body = parse(challenges_handler.handler(api_event(), None))
    assert state["challenge_id"] not in [c["challenge_id"] for c in body["challenges"]]
