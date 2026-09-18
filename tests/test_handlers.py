"""Lambda handler tests against the real storage layer (PRD 12.1, 12.2).

These exercise the full submit path -- diff, sandboxed test execution, the
evaluator layer and the DynamoDB writes -- with the local store standing in for
DynamoDB. No AI call is reachable, so every `correct` here comes from execution.
"""
import json

from conftest import api_event, parse

from lambdas.challenges import handler as challenges_handler
from lambdas.leaderboard import handler as leaderboard_handler
from lambdas.sessions import handler as sessions_handler
from lambdas.submit import handler as submit_handler

FIXED = "def add_one(n):\n    return n + 1\n"


def start_session(name="Tester", challenge_id="challenge-test"):
    status, body = parse(
        sessions_handler.handler(
            api_event("POST", {"challenge_id": challenge_id, "user_display_name": name}), None
        )
    )
    assert status == 200
    return body


def submit(session_id, code):
    return parse(
        submit_handler.handler(
            api_event("POST", {"submitted_code": code}, {"session_id": session_id}), None
        )
    )


def test_challenge_list_never_leaks_the_hidden_tests_or_the_answer(seeded):
    status, body = parse(challenges_handler.handler(api_event(), None))
    assert status == 200
    serialised = json.dumps(body)
    for secret in ("test_cases", "buggy_code", "ground_truth_diff", "expected_output", "bug_category"):
        assert secret not in serialised
    assert body["challenges"][0]["function_name"] == "add_one"


def test_starting_a_session_returns_the_buggy_code_and_a_server_start_time(seeded):
    body = start_session()
    assert body["buggy_code"].strip().endswith("return n + 2")
    assert isinstance(body["start_time"], int)
    assert body["time_limit_seconds"] == 300
    stored = seeded.get_session(body["session_id"])
    assert stored["status"] == "in_progress"


def test_unknown_challenge_is_a_404(seeded):
    status, body = parse(
        sessions_handler.handler(api_event("POST", {"challenge_id": "nope"}), None)
    )
    assert status == 404


def test_missing_challenge_id_is_a_400(seeded):
    status, _ = parse(sessions_handler.handler(api_event("POST", {}), None))
    assert status == 400


def test_a_correct_fix_is_marked_correct_and_persisted(seeded):
    session = start_session("Adii")
    status, body = submit(session["session_id"], FIXED)
    assert status == 200
    assert body["correct"] is True
    assert body["tests_passed"] == body["tests_total"] == 2
    assert body["score"] >= 90
    assert body["process_feedback"]

    stored = seeded.get_result(session["session_id"])
    assert stored["correct"] is True
    assert seeded.get_session(session["session_id"])["status"] == "complete"


def test_an_incorrect_fix_is_not_marked_correct(seeded):
    session = start_session()
    status, body = submit(session["session_id"], "def add_one(n):\n    return n + 3\n")
    assert status == 200
    assert body["correct"] is False
    assert body["tests_passed"] == 0
    assert body["score"] <= 50


def test_correct_is_computed_from_tests_not_from_the_feedback_layer(seeded, monkeypatch):
    """Even an evaluator that insists the code is perfect cannot flip the verdict."""
    from agents import evaluator

    monkeypatch.setattr(
        evaluator,
        "evaluate",
        lambda **kwargs: {
            "score": 100,
            "process_feedback": "Flawless.",
            "correctness_notes": "This is definitely correct.",
            "feedback_source": "stub",
        },
    )
    session = start_session()
    _, body = submit(session["session_id"], "def add_one(n):\n    return n + 99\n")
    assert body["correct"] is False
    assert body["tests_passed"] == 0


def test_a_whitespace_only_change_scores_zero(seeded):
    session = start_session()
    _, body = submit(session["session_id"], "def add_one(n):\n    return n + 2\n\n")
    assert body["correct"] is False
    assert body["score"] == 0
    assert "no change" in body["process_feedback"].lower()


def test_an_infinite_loop_is_a_failing_result_not_a_500(seeded):
    session = start_session()
    status, body = submit(session["session_id"], "def add_one(n):\n    while True:\n        pass\n")
    assert status == 200
    assert body["correct"] is False
    assert body["score"] == 0


def test_a_syntax_error_is_a_failing_result_not_a_500(seeded):
    session = start_session()
    status, body = submit(session["session_id"], "def add_one(n)\n    return n + 1\n")
    assert status == 200
    assert body["correct"] is False
    assert "execution_error" in body


def test_empty_submission_is_rejected_before_it_reaches_the_sandbox(seeded):
    session = start_session()
    status, body = submit(session["session_id"], "   ")
    assert status == 400


def test_resubmitting_a_finished_session_returns_the_stored_result(seeded):
    session = start_session()
    submit(session["session_id"], FIXED)
    status, body = submit(session["session_id"], FIXED)
    assert status == 409
    assert body["result"]["correct"] is True


def test_submitting_to_an_unknown_session_is_a_404(seeded):
    status, _ = submit("does-not-exist", FIXED)
    assert status == 404


def test_leaderboard_sorts_by_score_then_by_time(seeded):
    seeded.put_result({"session_id": "a", "challenge_id": "c", "user_display_name": "Slow",
                       "score": 100, "time_taken_seconds": 200, "correct": True})
    seeded.put_result({"session_id": "b", "challenge_id": "c", "user_display_name": "Fast",
                       "score": 100, "time_taken_seconds": 40, "correct": True})
    seeded.put_result({"session_id": "c", "challenge_id": "c", "user_display_name": "Low",
                       "score": 30, "time_taken_seconds": 10, "correct": False})

    status, body = parse(leaderboard_handler.handler(api_event(), None))
    assert status == 200
    assert [row["user_display_name"] for row in body["leaderboard"]] == ["Fast", "Slow", "Low"]


def test_leaderboard_is_empty_rather_than_broken_with_no_results(store):
    status, body = parse(leaderboard_handler.handler(api_event(), None))
    assert status == 200
    assert body["leaderboard"] == []


def test_display_name_is_truncated_not_rejected(seeded):
    body = start_session("x" * 200)
    assert len(seeded.get_session(body["session_id"])["user_display_name"]) == 32


def test_malformed_json_body_is_a_400(seeded):
    event = api_event("POST")
    event["body"] = "{not json"
    status, _ = parse(sessions_handler.handler(event, None))
    assert status == 400
