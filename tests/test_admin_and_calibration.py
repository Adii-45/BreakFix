"""Admin gating (Part 3) and difficulty calibration (Part 4.1)."""
import json
import time

import pytest

from common import config, events
from conftest import api_event, parse
from lambdas.admin import handler as admin
from lambdas.stats import handler as stats

PASS = "test-passphrase"


@pytest.fixture
def admin_on(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSPHRASE", PASS)
    monkeypatch.setattr(config, "STATE_MACHINE_ARN", "")
    yield


def auth_event(method="GET", body=None, path_params=None, passphrase=PASS):
    event = api_event(method, body, path_params)
    event["headers"] = {"X-Admin-Passphrase": passphrase} if passphrase is not None else {}
    return event


def _pending(store, cid="live-x", **overrides):
    record = {
        "challenge_id": cid, "repo_name": "python/cpython", "function_name": "quote",
        "buggy_code": "def quote(s):\n    return s\n", "clean_code": "def quote(s):\n    return s\n",
        "ground_truth_diff": json.dumps({"bug_category": "wrong-operator", "diff_summary": "changed a thing"}),
        "difficulty": "medium", "bug_category": "wrong-operator",
        "test_cases": json.dumps([{"name": "t", "input": ["a"], "expected_output": "a"}]),
        "tests_total": 2, "language": "python", "time_limit_seconds": 300,
        "student_facing_summary": "", "symptom_description": "",
        "status": "pending_review", "created_at": int(time.time()),
        "injection_source": "mutation-fallback", "tests_source": "admin-provided", "brief_source": "missing",
    }
    record.update(overrides)
    store.put_challenge(record)
    return record


# --- auth ------------------------------------------------------------------

def test_admin_routes_are_disabled_when_no_passphrase_is_configured(store, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSPHRASE", "")
    status, body = parse(admin.list_pending(auth_event(), None))
    assert status == 503
    assert "disabled" in body["error"].lower()


def test_a_wrong_passphrase_is_rejected(store, admin_on):
    status, _ = parse(admin.list_pending(auth_event(passphrase="nope"), None))
    assert status == 401


def test_a_missing_passphrase_is_rejected(store, admin_on):
    status, _ = parse(admin.list_pending(auth_event(passphrase=None), None))
    assert status == 401


def test_the_correct_passphrase_is_accepted(store, admin_on):
    status, body = parse(admin.list_pending(auth_event(), None))
    assert status == 200 and body["pending"] == []


# --- starting a run --------------------------------------------------------

def test_starting_a_run_requires_a_function_name(store, admin_on):
    status, _ = parse(admin.start_authoring(auth_event("POST", {"github_url": "x"}), None))
    assert status == 400


def test_starting_a_run_requires_a_source(store, admin_on):
    status, body = parse(admin.start_authoring(auth_event("POST", {"function_name": "f"}), None))
    assert status == 400
    assert "github_url" in body["error"]


# --- the publish gate ------------------------------------------------------

def test_a_pending_challenge_is_listed_for_review(store, admin_on):
    _pending(store)
    _, body = parse(admin.list_pending(auth_event(), None))
    assert [p["challenge_id"] for p in body["pending"]] == ["live-x"]
    assert body["pending"][0]["injection_source"] == "mutation-fallback"


def test_publishing_without_a_brief_is_refused(store, admin_on):
    _pending(store)
    status, body = parse(admin.publish(auth_event("POST", {}, {"challenge_id": "live-x"}), None))
    assert status == 422
    assert "mission brief" in body["error"].lower()
    assert store.get_challenge("live-x")["status"] == "pending_review"


def test_publishing_with_a_leaky_brief_is_refused(store, admin_on):
    _pending(store, ground_truth_diff=json.dumps({
        "bug_category": "wrong-operator",
        "correct_line": "    return s.upper()",
        "diff_summary": "changed a thing",
    }))
    status, body = parse(admin.publish(auth_event("POST", {
        "student_facing_summary": "Escapes a string for safe use as a single shell token in commands.",
        "symptom_description": "It should be     return s.upper() but is not, which breaks things.",
    }, {"challenge_id": "live-x"}), None))
    assert status == 422
    assert "gives the answer away" in body["error"]
    assert store.get_challenge("live-x")["status"] == "pending_review"


def test_publishing_with_a_sound_brief_succeeds(store, admin_on):
    _pending(store)
    status, body = parse(admin.publish(auth_event("POST", {
        "student_facing_summary": "Escapes a string so it can be used safely as one token in a shell command line.",
        "symptom_description": "Some inputs come back without the protection they need.",
    }, {"challenge_id": "live-x"}), None))
    assert status == 200 and body["status"] == "published"
    assert store.get_challenge("live-x")["status"] == "published"


def test_publishing_emits_a_domain_event(store, admin_on):
    _pending(store)
    seen = []
    events.subscribe(seen.append)
    admin.publish(auth_event("POST", {
        "student_facing_summary": "Escapes a string so it can be used safely as one token in a shell command line.",
        "symptom_description": "Some inputs come back without the protection they need.",
    }, {"challenge_id": "live-x"}), None)
    assert any(e["detail_type"] == "challenge.published" for e in seen)


def test_republishing_is_refused(store, admin_on):
    _pending(store, status="published")
    status, _ = parse(admin.publish(auth_event("POST", {}, {"challenge_id": "live-x"}), None))
    assert status == 409


def test_rejecting_marks_the_challenge_rejected(store, admin_on):
    _pending(store)
    status, _ = parse(admin.reject(auth_event("POST", {}, {"challenge_id": "live-x"}), None))
    assert status == 200
    assert store.get_challenge("live-x")["status"] == "rejected"


# --- high-score events -----------------------------------------------------

def test_a_first_result_counts_as_a_high_score():
    assert events.emit_high_score({"challenge_id": "c", "score": 50}, None) is True


def test_beating_the_standing_best_emits():
    assert events.emit_high_score({"challenge_id": "c", "score": 90}, 80) is True


def test_failing_to_beat_the_best_does_not_emit():
    assert events.emit_high_score({"challenge_id": "c", "score": 70}, 80) is False
    assert events.emit_high_score({"challenge_id": "c", "score": 80}, 80) is False


# --- difficulty calibration ------------------------------------------------

def _results(store, cid, outcomes):
    for index, (correct, secs) in enumerate(outcomes):
        store.put_result({"session_id": f"{cid}-{index}", "challenge_id": cid,
                          "user_display_name": f"u{index}", "score": 100 if correct else 20,
                          "correct": correct, "time_taken_seconds": secs,
                          "tests_passed": 1 if correct else 0, "tests_total": 1,
                          "submitted_at": int(time.time())})


def test_calibration_is_withheld_below_the_sample_threshold(seeded):
    _results(seeded, "challenge-test", [(True, 30), (False, 40)])
    _, body = parse(stats.handler(api_event(), None))
    row = body["per_challenge"]["challenge-test"]
    assert row["calibrated"] is False
    assert row["pass_rate"] is None, "a pass rate off 2 attempts would be misleading"
    assert row["static_difficulty"] == "medium"


def test_calibration_reports_a_real_pass_rate_once_the_sample_is_big_enough(seeded):
    _results(seeded, "challenge-test", [(True, 30), (True, 50), (False, 20), (True, 40), (False, 60)])
    _, body = parse(stats.handler(api_event(), None))
    row = body["per_challenge"]["challenge-test"]
    assert row["calibrated"] is True
    assert row["sample_size"] == 5
    assert row["pass_rate"] == 0.6
    assert row["median_solve_seconds"] == 40      # median of the three solve times
    assert row["observed_difficulty"] == "medium"


def test_a_challenge_nobody_solves_calibrates_as_hard(seeded):
    _results(seeded, "challenge-test", [(False, 10)] * 5)
    _, body = parse(stats.handler(api_event(), None))
    row = body["per_challenge"]["challenge-test"]
    assert row["pass_rate"] == 0.0
    assert row["observed_difficulty"] == "hard"
    assert row["median_solve_seconds"] is None, "no solves means no median solve time"


def test_a_challenge_everyone_solves_calibrates_as_easy(seeded):
    _results(seeded, "challenge-test", [(True, 10)] * 5)
    _, body = parse(stats.handler(api_event(), None))
    assert body["per_challenge"]["challenge-test"]["observed_difficulty"] == "easy"
