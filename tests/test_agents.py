"""Agent-layer tests (PRD 8.1, 8.2, 12.2).

The central property under test: the Evaluator Agent cannot change the verdict.
Whatever a model returns, the score it produces must stay inside the band the
test outcome allows.
"""
import json

import pytest

from agents import bedrock_client, evaluator
from common import diffing


def result(passed, total, kinds=None):
    kinds = kinds or (["pass"] * passed + ["mismatch"] * (total - passed))
    return {
        "tests_passed": passed,
        "tests_total": total,
        "runner_status": "ok",
        "per_test": [
            {"index": i, "name": f"t{i}", "passed": i < passed, "kind": kinds[i], "error": None}
            for i in range(total)
        ],
    }


# --- structured output parsing ---------------------------------------------

def test_parses_a_bare_json_object():
    parsed = bedrock_client.parse_json_response('{"score": 90, "a": 1}', ["score"])
    assert parsed["score"] == 90


def test_parses_json_inside_a_fenced_block():
    text = 'Here you go:\n```json\n{"score": 70, "process_feedback": "x"}\n```\nHope that helps.'
    assert bedrock_client.parse_json_response(text, ["score", "process_feedback"])["score"] == 70


def test_parses_json_surrounded_by_prose():
    text = 'Sure. {"score": 40, "note": "y"} Let me know if you need more.'
    assert bedrock_client.parse_json_response(text, ["score"])["score"] == 40


def test_missing_required_key_is_an_error():
    with pytest.raises(ValueError, match="missing required keys"):
        bedrock_client.parse_json_response('{"score": 10}', ["score", "process_feedback"])


def test_non_json_response_is_an_error():
    with pytest.raises(ValueError):
        bedrock_client.parse_json_response("I am afraid I cannot do that.", ["score"])


# --- the evaluator can never contradict the tests --------------------------

@pytest.mark.parametrize("model_score", [0, 10, 55, 100, 9999, -50])
def test_a_passing_submission_never_scores_below_the_pass_band(model_score, monkeypatch):
    monkeypatch.setattr(
        bedrock_client, "invoke",
        lambda *a, **k: (json.dumps({"score": model_score, "process_feedback": "p", "correctness_notes": "c"}), "stub"),
    )
    out = evaluator.evaluate("buggy", "gt", "fixed", result(3, 3), "diff", {"lines_changed": 1})
    assert 60 <= out["score"] <= 100


@pytest.mark.parametrize("model_score", [0, 51, 90, 100])
def test_a_failing_submission_never_scores_above_the_fail_band(model_score, monkeypatch):
    monkeypatch.setattr(
        bedrock_client, "invoke",
        lambda *a, **k: (json.dumps({"score": model_score, "process_feedback": "p", "correctness_notes": "c"}), "stub"),
    )
    out = evaluator.evaluate("buggy", "gt", "broken", result(1, 3), "diff", {"lines_changed": 1})
    assert 0 <= out["score"] <= 50


def test_a_model_that_returns_garbage_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setattr(bedrock_client, "invoke", lambda *a, **k: ("not json at all", "stub"))
    out = evaluator.evaluate("buggy", "gt", "fixed", result(3, 3), "d", {"lines_changed": 1})
    assert out["feedback_source"] == "fallback-heuristic"
    assert out["score"] >= 60


def test_a_bedrock_outage_falls_back_instead_of_raising(monkeypatch):
    def boom(*a, **k):
        raise bedrock_client.BedrockUnavailable("no credentials")

    monkeypatch.setattr(bedrock_client, "invoke", boom)
    out = evaluator.evaluate("buggy", "gt", "fixed", result(2, 2), "d", {"lines_changed": 1})
    assert out["feedback_source"] == "fallback-heuristic"
    assert out["score"] == 100


def test_the_evaluator_is_never_asked_for_a_correct_field(monkeypatch):
    """Section 8.2: there is no `correct` in the agent's output contract."""
    captured = {}

    def capture(system, user, *a, **k):
        captured["system"] = system
        return json.dumps({"score": 80, "process_feedback": "p", "correctness_notes": "c"}), "stub"

    monkeypatch.setattr(bedrock_client, "invoke", capture)
    out = evaluator.evaluate("buggy", "gt", "fixed", result(2, 2), "d", {"lines_changed": 1})
    assert "correct" not in out
    assert "Do NOT contradict the given test outcome" in captured["system"]


# --- fallback scoring bands (PRD 12.3) -------------------------------------

def test_minimal_passing_fix_scores_100():
    out = evaluator.fallback_evaluate(result(2, 2), {"lines_changed": 1}, "diff")
    assert out["score"] == 100


def test_broad_passing_rewrite_stays_in_the_pass_band_but_scores_lower():
    out = evaluator.fallback_evaluate(result(2, 2), {"lines_changed": 20}, "diff")
    assert 70 <= out["score"] < 100


def test_no_change_scores_zero():
    out = evaluator.fallback_evaluate(result(1, 3), {"lines_changed": 0}, "")
    assert out["score"] == 0
    assert "no change" in out["process_feedback"].lower()


def test_partial_pass_lands_in_the_right_track_band():
    out = evaluator.fallback_evaluate(result(2, 3), {"lines_changed": 2}, "diff")
    assert 20 <= out["score"] <= 50


def test_a_broken_submission_is_flagged_as_broken_not_just_incorrect():
    out = evaluator.fallback_evaluate(result(0, 2, ["timeout", "timeout"]), {"lines_changed": 3}, "diff")
    assert out["score"] == 0
    assert "broken" in out["process_feedback"].lower()


def test_a_sandbox_violation_is_also_flagged_as_broken():
    out = evaluator.fallback_evaluate(result(0, 2, ["blocked", "blocked"]), {"lines_changed": 3}, "diff")
    assert out["score"] == 0
    assert "sandbox" in out["process_feedback"].lower() or "blocked" in out["correctness_notes"].lower()


def test_wrong_answers_are_not_treated_as_broken():
    out = evaluator.fallback_evaluate(result(0, 2, ["mismatch", "mismatch"]), {"lines_changed": 3}, "diff")
    assert out["score"] == 20
    assert "broken" not in out["process_feedback"].lower()


# --- diff helpers -----------------------------------------------------------

def test_whitespace_only_change_counts_as_unchanged():
    assert diffing.is_unchanged("def f():\n    pass\n", "def f():\n    pass\n\n")


def test_real_change_is_not_unchanged():
    assert not diffing.is_unchanged("def f():\n    return 1\n", "def f():\n    return 2\n")


def test_diff_stats_counts_a_one_line_edit_as_one_line_each_way():
    stats = diffing.diff_stats("a\nb\nc\n", "a\nX\nc\n")
    assert stats["lines_added"] == 1 and stats["lines_removed"] == 1
    assert stats["lines_changed"] == 2


def test_unified_diff_labels_the_two_sides():
    text = diffing.unified_diff("a\n", "b\n")
    assert "--- buggy" in text and "+++ submitted" in text


# --- bug injector validation -----------------------------------------------

def test_bug_injector_rejects_code_that_does_not_define_the_function(monkeypatch):
    from agents import bug_injector

    monkeypatch.setattr(
        bedrock_client, "invoke",
        lambda *a, **k: (json.dumps({
            "buggy_code": "def something_else():\n    pass\n",
            "diff_summary": "s", "bug_category": "off-by-one", "why_its_a_bug": "w",
        }), "stub"),
    )
    with pytest.raises(ValueError, match="does not define"):
        bug_injector.inject_bug("def target():\n    pass\n", "target", "off-by-one")


def test_bug_injector_rejects_unparseable_code(monkeypatch):
    from agents import bug_injector

    monkeypatch.setattr(
        bedrock_client, "invoke",
        lambda *a, **k: (json.dumps({
            "buggy_code": "def target(:\n    pass\n",
            "diff_summary": "s", "bug_category": "off-by-one", "why_its_a_bug": "w",
        }), "stub"),
    )
    with pytest.raises(SyntaxError):
        bug_injector.inject_bug("def target():\n    pass\n", "target", "off-by-one")


def test_bug_injector_strips_markdown_fences(monkeypatch):
    from agents import bug_injector

    monkeypatch.setattr(
        bedrock_client, "invoke",
        lambda *a, **k: (json.dumps({
            "buggy_code": "```python\ndef target():\n    return 2\n```",
            "diff_summary": "s", "bug_category": "off-by-one", "why_its_a_bug": "w",
            "hint_level_description": "h",
        }), "stub"),
    )
    out = bug_injector.inject_bug("def target():\n    return 1\n", "target", "off-by-one")
    assert out["buggy_code"].startswith("def target()")
    assert "```" not in out["buggy_code"]
