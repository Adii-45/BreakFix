"""DynamoDB adapter tests against a simulated DynamoDB (PRD 12.2).

The local JSON store is what the other tests use, so without these the entire
production storage path -- including the leaderboard GSI query that Section 6.4
specifies -- would never be executed before the demo.

The tables here are created with exactly the schema in infra/template.yaml.
"""
import json
import os

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")

REGION = "us-east-1"


@pytest.fixture
def dynamo(monkeypatch):
    from moto import mock_aws

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        ddb.create_table(
            TableName="breakfix-challenges",
            KeySchema=[{"AttributeName": "challenge_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "challenge_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="breakfix-sessions",
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="breakfix-results",
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "leaderboard_pk", "AttributeType": "S"},
                {"AttributeName": "score", "AttributeType": "N"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "score-index",
                    "KeySchema": [
                        {"AttributeName": "leaderboard_pk", "KeyType": "HASH"},
                        {"AttributeName": "score", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        from common import config, storage

        monkeypatch.setattr(config, "STORAGE_BACKEND", "dynamodb")
        monkeypatch.setattr(config, "AWS_REGION", REGION)
        storage.reset_store()
        yield storage.DynamoStore()
        storage.reset_store()


CHALLENGE = {
    "challenge_id": "challenge-01",
    "repo_name": "example/repo",
    "function_name": "add_one",
    "buggy_code": "def add_one(n):\n    return n + 2\n",
    "ground_truth_diff": json.dumps({"diff_summary": "s"}),
    "difficulty": "medium",
    "bug_category": "off-by-one",
    "test_cases": json.dumps([{"name": "t", "input": [1], "expected_output": 2}]),
    "language": "python",
    "time_limit_seconds": 300,
}


def test_challenge_round_trip(dynamo):
    dynamo.put_challenge(CHALLENGE)
    fetched = dynamo.get_challenge("challenge-01")
    assert fetched["buggy_code"] == CHALLENGE["buggy_code"]
    assert json.loads(fetched["test_cases"])[0]["expected_output"] == 2


def test_get_missing_challenge_returns_none(dynamo):
    assert dynamo.get_challenge("nope") is None


def test_list_challenges_projects_public_fields_only(dynamo):
    dynamo.put_challenge(CHALLENGE)
    rows = dynamo.list_challenges()
    assert len(rows) == 1
    # The projection must not carry the answer or the hidden tests.
    for secret in ("buggy_code", "ground_truth_diff", "test_cases", "bug_category"):
        assert secret not in rows[0]
    assert rows[0]["function_name"] == "add_one"
    assert rows[0]["language"] == "python"


def test_session_round_trip_and_status_update(dynamo):
    dynamo.put_session(
        {"session_id": "s1", "challenge_id": "challenge-01", "user_display_name": "Adii",
         "start_time": 1700000000, "status": "in_progress"}
    )
    assert dynamo.get_session("s1")["status"] == "in_progress"
    dynamo.set_session_status("s1", "complete")
    assert dynamo.get_session("s1")["status"] == "complete"
    # Numbers must come back as ints, not Decimals, or json.dumps will explode.
    assert isinstance(dynamo.get_session("s1")["start_time"], int)


def test_results_carry_the_leaderboard_partition_key(dynamo):
    dynamo.put_result({"session_id": "r1", "challenge_id": "c", "score": 90,
                       "time_taken_seconds": 30, "correct": True, "user_display_name": "A"})
    raw = boto3.resource("dynamodb", region_name=REGION).Table("breakfix-results").get_item(
        Key={"session_id": "r1"}
    )["Item"]
    assert raw["leaderboard_pk"] == "GLOBAL"


def test_leaderboard_gsi_query_returns_top_scores_descending(dynamo):
    for i, (sid, score, secs) in enumerate(
        [("a", 40, 10), ("b", 100, 200), ("c", 100, 40), ("d", 70, 5), ("e", 10, 1)]
    ):
        dynamo.put_result({"session_id": sid, "challenge_id": "c", "score": score,
                           "time_taken_seconds": secs, "correct": score == 100,
                           "user_display_name": sid.upper()})

    top = dynamo.top_results(3)
    assert [r["session_id"] for r in top] == ["c", "b", "d"]  # 100/40s, 100/200s, then 70
    assert isinstance(top[0]["score"], int)


def test_float_values_survive_the_round_trip(dynamo):
    dynamo.put_result({"session_id": "f1", "challenge_id": "c", "score": 80,
                       "time_taken_seconds": 12, "correct": True,
                       "user_display_name": "F", "duration_ms": 12.5})
    assert dynamo.get_result("f1")["duration_ms"] == 12.5


def test_handlers_work_end_to_end_against_dynamodb(dynamo, monkeypatch):
    """The real proof: the same handlers, backed by DynamoDB instead of JSON."""
    from common import storage
    monkeypatch.setattr(storage, "_store", dynamo)

    from conftest import api_event, parse
    from lambdas.challenges import handler as challenges_handler
    from lambdas.leaderboard import handler as leaderboard_handler
    from lambdas.sessions import handler as sessions_handler
    from lambdas.submit import handler as submit_handler

    dynamo.put_challenge(CHALLENGE)

    status, listing = parse(challenges_handler.handler(api_event(), None))
    assert status == 200 and len(listing["challenges"]) == 1

    status, session = parse(
        sessions_handler.handler(
            api_event("POST", {"challenge_id": "challenge-01", "user_display_name": "Adii"}), None
        )
    )
    assert status == 200

    status, result = parse(
        submit_handler.handler(
            api_event("POST", {"submitted_code": "def add_one(n):\n    return n + 1\n"},
                      {"session_id": session["session_id"]}),
            None,
        )
    )
    assert status == 200
    assert result["correct"] is True
    assert result["tests_passed"] == 1

    status, board = parse(leaderboard_handler.handler(api_event(), None))
    assert status == 200
    assert board["leaderboard"][0]["user_display_name"] == "Adii"
    assert board["leaderboard"][0]["score"] >= 90
