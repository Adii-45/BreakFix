"""Mission Brief Agent tests (Part 1).

The brief is the only student-facing prose that is derived from the bug, so the
leak check is the thing that matters: a brief must describe the symptom without
letting the student reconstruct the fix.
"""
import json
import pathlib

import pytest

from agents.brief_writer import BriefLeak, assert_no_leak, source_url

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHALLENGES = ROOT / "seed-data" / "challenges"

CLEAN = "def ordinal(value):\n    if value % 100 in (11, 12, 13):\n        return 'th'\n    return SUFFIXES[value % 10]\n"
BUGGY = "def ordinal(value):\n    if value % 100 in (11, 12):\n        return 'th'\n    return SUFFIXES[value % 10]\n"
GT = {
    "bug_category": "wrong-condition",
    "diff_summary": "The teens special case was narrowed from (11, 12, 13) to (11, 12).",
    "correct_line": "    if value % 100 in (11, 12, 13):",
    "buggy_line": "    if value % 100 in (11, 12):",
}


def test_a_behavioural_symptom_passes():
    assert_no_leak(
        {"purpose": "Converts an integer to its English ordinal form.",
         "symptom": "A handful of numbers come back carrying the wrong two-letter ending."},
        GT, CLEAN, BUGGY,
    )


def test_a_brief_that_quotes_the_correct_line_is_rejected():
    with pytest.raises(BriefLeak, match="correct_line"):
        assert_no_leak(
            {"purpose": "Converts a number.",
             "symptom": "It should be    if value % 100 in (11, 12, 13): but is not."},
            GT, CLEAN, BUGGY,
        )


def test_a_brief_that_quotes_the_buggy_line_is_rejected():
    with pytest.raises(BriefLeak):
        assert_no_leak(
            {"purpose": "Converts a number.",
             "symptom": "The line     if value % 100 in (11, 12): is the problem."},
            GT, CLEAN, BUGGY,
        )


def test_a_brief_that_names_the_bug_category_is_rejected():
    with pytest.raises(BriefLeak):
        assert_no_leak(
            {"purpose": "Converts a number.", "symptom": "There is a wrong condition in the branch."},
            GT, CLEAN, BUGGY,
        )


def test_a_brief_naming_the_category_in_the_purpose_is_rejected():
    with pytest.raises(BriefLeak, match="category"):
        assert_no_leak(
            {"purpose": "Converts a number; this one has a wrong condition.", "symptom": "Output differs."},
            GT, CLEAN, BUGGY,
        )


def test_an_empty_diff_summary_does_not_falsely_reject_a_clean_brief():
    """Regression: `"" in blob` is always true, so the guard needs a length check."""
    assert_no_leak(
        {"purpose": "Converts an integer to its English ordinal form, used across the library.",
         "symptom": "A handful of numbers come back carrying the wrong two-letter ending."},
        {"bug_category": "wrong-condition"}, CLEAN, BUGGY,
    )


@pytest.mark.parametrize("symptom", [
    "The comparison should be widened to include another case.",
    "Replace the tuple with a fuller one.",
    "The fix is to add the missing value.",
])
def test_prescriptive_symptoms_are_rejected(symptom):
    with pytest.raises(BriefLeak):
        assert_no_leak({"purpose": "Converts a number.", "symptom": symptom}, GT, CLEAN, BUGGY)


def test_a_brief_naming_an_identifier_unique_to_one_version_is_rejected():
    clean = "def f(items):\n    return sorted(items)\n"
    buggy = "def f(items):\n    return reversed(items)\n"
    with pytest.raises(BriefLeak, match="identifiers"):
        assert_no_leak(
            {"purpose": "Orders things.", "symptom": "The result comes back reversed."},
            {"bug_category": "swapped-variable"}, clean, buggy,
        )


def test_source_url_points_at_the_real_file():
    assert source_url("https://github.com/django/django", "django/utils/text.py") == \
        "https://github.com/django/django/blob/main/django/utils/text.py"


def test_source_url_is_empty_when_metadata_is_missing():
    assert source_url("", "x.py") == ""
    assert source_url("https://github.com/a/b", "") == ""


# --- the shipped seed set -------------------------------------------------

SEED_DIRS = sorted(d for d in CHALLENGES.iterdir() if d.is_dir())


@pytest.mark.parametrize("directory", SEED_DIRS, ids=lambda d: d.name)
def test_every_seeded_brief_passes_the_leak_check(directory):
    brief = json.loads((directory / "brief.json").read_text())
    gt = json.loads((directory / "ground_truth.json").read_text())
    assert_no_leak(
        {"purpose": brief["student_facing_summary"], "symptom": brief["symptom_description"]},
        gt,
        (directory / "clean.py").read_text(),
        (directory / "buggy.py").read_text(),
    )


@pytest.mark.parametrize("directory", SEED_DIRS, ids=lambda d: d.name)
def test_every_seeded_challenge_has_a_usable_brief(directory):
    brief = json.loads((directory / "brief.json").read_text())
    meta = json.loads((directory / "meta.json").read_text())
    assert len(brief["student_facing_summary"]) > 60, "purpose should actually explain something"
    assert len(brief["symptom_description"]) > 25, "symptom should be a real sentence"
    assert meta["repo_url"].startswith("https://github.com/")
    assert source_url(meta["repo_url"], meta["source_path"]).endswith(".py")
