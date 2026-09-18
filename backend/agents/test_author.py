"""Test Author Agent — proposes hidden test cases for a live-authored challenge.

Only used when the admin has not supplied test cases. Whatever it returns is
immediately run against the CLEAN function (step_verify_clean) and the whole run
is rejected if a single case fails, so a hallucinated expectation stops the
pipeline rather than becoming ground truth.
"""
import json
from typing import Dict, List

from agents import bedrock_client

SYSTEM_PROMPT = """You write hidden unit tests for a debugging practice tool.

Given a correct Python function, propose 3 or 4 test cases that pin down its
behaviour, including at least one edge case. Every expected_output must be
exactly what the given implementation returns - you are describing the
function as written, not as you think it should behave.

Inputs and outputs must be JSON-serialisable. `input` is the argument list.

Return JSON: { "tests": [ { "name": str, "input": [...], "expected_output": ... } ] }"""

USER_TEMPLATE = """Function name: {function_name}

```python
{clean_code}
```

Return ONLY the JSON object."""


def propose_tests(clean_code: str, function_name: str) -> List[Dict]:
    user_text = USER_TEMPLATE.format(function_name=function_name, clean_code=clean_code.strip())
    raw, _transport = bedrock_client.invoke(SYSTEM_PROMPT, user_text, max_tokens=1200)
    parsed = bedrock_client.parse_json_response(raw, ["tests"])

    tests = parsed["tests"]
    if not isinstance(tests, list) or not 2 <= len(tests) <= 6:
        raise ValueError(f"Expected 2-6 test cases, got {len(tests) if isinstance(tests, list) else tests!r}")
    for index, case in enumerate(tests):
        if not isinstance(case, dict) or "input" not in case or "expected_output" not in case:
            raise ValueError(f"Test case {index + 1} is missing input or expected_output")
        case.setdefault("name", f"case {index + 1}")
        json.dumps(case)  # must be serialisable for the sandbox payload
    return tests
