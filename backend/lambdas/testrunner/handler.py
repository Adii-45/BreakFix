"""Test Runner Lambda (PRD Section 5.1 stage 6, Section 8.0).

Deliberately its own function with its own IAM role, and that role grants
NOTHING -- no DynamoDB, no Bedrock, no S3. Submitted code is untrusted, and if
it ever did escape the in-process sandbox it would land in an execution
environment that cannot read the hidden test cases, cannot read other students'
submissions, and cannot call a model.

It is invoked synchronously by the submit Lambda. Input and output are the same
shapes `test_runner.runner.run_tests` uses.
"""
from test_runner import runner


def handler(event, context):  # noqa: ANN001
    return runner.run_tests(
        code=event["code"],
        entry_point=event["entry_point"],
        test_cases=event.get("test_cases", []),
        wall_timeout=event.get("wall_timeout"),
        per_test_timeout=event.get("per_test_timeout"),
        memory_mb=event.get("memory_mb"),
    )
