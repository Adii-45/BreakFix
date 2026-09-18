import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

os.environ["BREAKFIX_STORAGE"] = "local"
# Never let a test accidentally reach the network looking for Bedrock.
os.environ.setdefault("ALLOW_EVALUATOR_FALLBACK", "true")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A fresh, isolated local store per test."""
    from common import config, storage

    monkeypatch.setattr(config, "LOCAL_STORE_PATH", str(tmp_path / "db"))
    storage.reset_store()
    yield storage.get_store()
    storage.reset_store()


@pytest.fixture
def seeded(store):
    """One challenge, seeded, with a known bug and known hidden tests."""
    store.put_challenge(
        {
            "challenge_id": "challenge-test",
            "repo_name": "example/repo",
            "function_name": "add_one",
            "buggy_code": "def add_one(n):\n    return n + 2\n",
            "ground_truth_diff": json.dumps({"diff_summary": "n + 1 became n + 2"}),
            "difficulty": "medium",
            "bug_category": "off-by-one",
            "test_cases": json.dumps(
                [
                    {"name": "adds one to 1", "input": [1], "expected_output": 2},
                    {"name": "adds one to 10", "input": [10], "expected_output": 11},
                ]
            ),
            "language": "python",
            "time_limit_seconds": 300,
            # Written by the authoring pipeline alongside test_cases so the
            # serving projection never has to read the assertions themselves.
            "tests_total": 2,
            "code_preview": "def add_one(n):",
        }
    )
    return store


def api_event(method="GET", body=None, path_params=None, query=None):
    return {
        "httpMethod": method,
        "body": json.dumps(body) if body is not None else None,
        "pathParameters": path_params or {},
        "queryStringParameters": query or {},
        "headers": {},
    }


def parse(response):
    return response["statusCode"], json.loads(response["body"] or "{}")
