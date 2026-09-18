"""Chooses how to reach the Test Runner.

In AWS the submit Lambda invokes a separate, zero-permission Test Runner Lambda
(TEST_RUNNER_FUNCTION_NAME). Locally -- and in the offline authoring pipeline and
the golden-set validator -- the same `run_tests` function is called in-process.
Identical inputs and outputs either way, so nothing downstream needs to care.
"""
import json
import logging
import os
from typing import Any, Dict, List

from common import config
from test_runner import runner

logger = logging.getLogger(__name__)

TEST_RUNNER_FUNCTION_NAME = os.environ.get("TEST_RUNNER_FUNCTION_NAME", "")


def run(code: str, entry_point: str, test_cases: List[Dict]) -> Dict[str, Any]:
    if not TEST_RUNNER_FUNCTION_NAME:
        return runner.run_tests(code, entry_point, test_cases)

    import boto3
    from botocore.config import Config as BotoConfig

    client = boto3.client(
        "lambda",
        region_name=config.AWS_REGION,
        config=BotoConfig(
            read_timeout=config.SANDBOX_WALL_TIMEOUT_SECONDS + 10,
            retries={"max_attempts": 0},  # never re-run untrusted code on a blip
        ),
    )
    try:
        response = client.invoke(
            FunctionName=TEST_RUNNER_FUNCTION_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(
                {"code": code, "entry_point": entry_point, "test_cases": test_cases}
            ).encode("utf-8"),
        )
        payload = json.loads(response["Payload"].read())
        if response.get("FunctionError"):
            raise RuntimeError(f"Test Runner Lambda error: {payload}")
        return payload
    except Exception as exc:  # noqa: BLE001
        # A Test Runner we cannot reach must not be reported as "correct".
        logger.exception("Test Runner Lambda invocation failed")
        return {
            "tests_passed": 0,
            "tests_total": len(test_cases),
            "per_test": [
                {"index": i, "name": c.get("name", f"test_{i + 1}"), "passed": False,
                 "kind": "error", "error": "The test runner could not be reached."}
                for i, c in enumerate(test_cases)
            ],
            "runner_status": "unavailable",
            "load_error": f"Test Runner unavailable: {exc}",
            "stderr": "",
            "duration_ms": 0,
        }
