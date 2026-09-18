"""Real-time layer tests (Part 2).

The property under test throughout: every number pushed to a client is derived
from rows that exist. Presence counts real in_progress sessions and expires
them; the activity feed is never padded.
"""
import json
import time

import pytest

from common import config, realtime
from lambdas.broadcaster import handler as broadcaster
from lambdas.ws import handler as ws


def _challenge(store, cid="challenge-test", limit=300):
    store.put_challenge({
        "challenge_id": cid, "repo_name": "example/repo", "function_name": "add_one",
        "buggy_code": "def add_one(n):\n    return n + 2\n", "ground_truth_diff": "{}",
        "difficulty": "medium", "bug_category": "off-by-one",
        "test_cases": json.dumps([{"name": "t", "input": [1], "expected_output": 2}]),
        "language": "python", "time_limit_seconds": limit, "tests_total": 1, "status": "published",
    })


def _session(store, sid, cid="challenge-test", status="in_progress", age=0):
    store.put_session({"session_id": sid, "challenge_id": cid, "user_display_name": sid,
                       "start_time": int(time.time()) - age, "status": status})


def _result(store, sid, cid="challenge-test", score=100, correct=True, at=None):
    store.put_result({"session_id": sid, "challenge_id": cid, "user_display_name": sid,
                      "score": score, "correct": correct, "tests_passed": 1, "tests_total": 1,
                      "time_taken_seconds": 42, "submitted_at": at or int(time.time())})


# --- presence --------------------------------------------------------------

def test_presence_is_zero_with_no_sessions(store):
    _challenge(store)
    assert realtime.build_presence(store) == {"challenge-test": 0}


def test_presence_counts_only_in_progress_sessions(store):
    _challenge(store)
    _session(store, "a")
    _session(store, "b")
    _session(store, "c", status="complete")
    assert realtime.build_presence(store)["challenge-test"] == 2


def test_presence_expires_a_session_past_its_time_limit(store):
    """An abandoned tab must stop counting, or presence only ever goes up."""
    _challenge(store, limit=300)
    _session(store, "fresh", age=10)
    _session(store, "stale", age=300 + config.PRESENCE_GRACE_SECONDS + 60)
    assert realtime.build_presence(store)["challenge-test"] == 1


def test_presence_honours_each_challenges_own_time_limit(store):
    _challenge(store, cid="short", limit=60)
    _challenge(store, cid="long", limit=600)
    _session(store, "s1", cid="short", age=200)   # past 60 + grace
    _session(store, "s2", cid="long", age=200)    # well inside 600 + grace
    presence = realtime.build_presence(store)
    assert presence["short"] == 0
    assert presence["long"] == 1


def test_presence_ignores_sessions_for_unknown_challenges(store):
    _challenge(store)
    _session(store, "ghost", cid="deleted-challenge")
    assert realtime.build_presence(store) == {"challenge-test": 0}


# --- activity feed ---------------------------------------------------------

def test_activity_feed_is_empty_when_nothing_has_happened(store):
    _challenge(store)
    assert realtime.build_activity(store) == []


def test_activity_feed_returns_only_real_events_never_padded(store):
    _challenge(store)
    _result(store, "one")
    _result(store, "two", correct=False, score=20)
    events = realtime.build_activity(store, limit=10)
    assert len(events) == 2, "two real results must not be padded to fill the panel"
    assert {e["kind"] for e in events} == {"solved", "attempted"}


def test_activity_feed_is_newest_first_and_capped(store):
    _challenge(store)
    now = int(time.time())
    for i in range(8):
        _result(store, f"s{i}", at=now - i * 10)
    events = realtime.build_activity(store, limit=3)
    assert [e["session_id"] for e in events] == ["s0", "s1", "s2"]


def test_activity_events_carry_the_real_function_name(store):
    _challenge(store)
    _result(store, "one")
    assert realtime.build_activity(store)[0]["function_name"] == "add_one"


# --- snapshot + broadcast --------------------------------------------------

def test_snapshot_bundles_all_three_real_views(store):
    _challenge(store)
    _session(store, "live")
    _result(store, "done")
    snapshot = realtime.build_snapshot(store)
    assert snapshot["type"] == "snapshot"
    assert snapshot["presence"]["challenge-test"] == 1
    assert len(snapshot["activity"]) == 1
    assert len(snapshot["leaderboard"]) == 1


def test_broadcast_uses_the_local_sink_when_one_is_registered(store):
    sent = []
    realtime.set_local_sink(sent.append)
    try:
        realtime.broadcast({"type": "update", "presence": {}})
        assert len(sent) == 1 and sent[0]["type"] == "update"
    finally:
        realtime.set_local_sink(None)


def test_broadcast_is_a_no_op_without_an_endpoint(store, monkeypatch):
    monkeypatch.setattr(config, "WEBSOCKET_ENDPOINT", "")
    realtime.set_local_sink(None)
    assert realtime.broadcast({"type": "update"}) == 0


# --- the stream-triggered broadcaster --------------------------------------

def _stream_event(table):
    return {"Records": [{"eventSourceARN": f"arn:aws:dynamodb:us-east-1:1:table/{table}/stream/x",
                         "eventName": "INSERT"}]}


def test_results_stream_pushes_leaderboard_activity_and_presence(store):
    _challenge(store)
    _result(store, "one")
    sent = []
    realtime.set_local_sink(sent.append)
    try:
        broadcaster.handler(_stream_event("breakfix-results"), None)
    finally:
        realtime.set_local_sink(None)
    payload = sent[0]
    assert set(payload) >= {"type", "leaderboard", "activity", "presence"}
    assert payload["leaderboard"][0]["user_display_name"] == "one"


def test_sessions_stream_pushes_presence_only(store):
    _challenge(store)
    _session(store, "live")
    sent = []
    realtime.set_local_sink(sent.append)
    try:
        broadcaster.handler(_stream_event("breakfix-sessions"), None)
    finally:
        realtime.set_local_sink(None)
    payload = sent[0]
    assert "presence" in payload
    assert "leaderboard" not in payload, "a session write does not change the leaderboard"


def test_broadcaster_ignores_an_empty_batch(store):
    assert broadcaster.handler({"Records": []}, None)["delivered"] == 0


# --- websocket routes ------------------------------------------------------

def test_connect_records_the_connection_and_disconnect_removes_it(store):
    event = {"requestContext": {"connectionId": "abc123", "requestTimeEpoch": 1700000000000}}
    assert ws.connect(event, None)["statusCode"] == 200
    assert "abc123" in store.list_connections()
    assert ws.disconnect(event, None)["statusCode"] == 200
    assert "abc123" not in store.list_connections()


def test_disconnecting_an_unknown_connection_is_harmless(store):
    assert ws.disconnect({"requestContext": {"connectionId": "nope"}}, None)["statusCode"] == 200
