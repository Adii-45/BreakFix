"""Bug Injector Agent (PRD Section 8.1).

Runs OFFLINE, once per seed challenge, from seed-data/author_challenges.py.
It is never on the live request path, and its output is never trusted
unsupervised: every generated bug must (a) make at least one hidden test fail
and (b) survive human review before it reaches the seed set (Section 5.3).
"""
from typing import Any, Dict, List

from agents import bedrock_client

BUG_CATEGORIES = [
    "off-by-one",
    "wrong-condition",
    "swapped-variable",
    "incorrect-boundary",
    "wrong-operator",
    "inverted-logic",
    "missing-update",
]

SYSTEM_PROMPT = """You are a careful software bug-injection assistant for a coding
practice tool. Given a correct function, introduce exactly ONE realistic,
non-trivial bug of the requested category. The bug must:
  - compile / parse without errors
  - not be detectable by a linter or type-checker alone
  - represent a mistake a real engineer could plausibly make
  - have a single, unambiguous correct fix
Do not change formatting, comments, or unrelated logic.
Return JSON: { buggy_code, diff_summary, bug_category, why_its_a_bug }"""

# hint_level_description is listed in the PRD's Output field list for this agent
# but not in its prompt skeleton's Return JSON line. We ask for it explicitly so
# the two agree; it feeds the post-MVP hint system (Section 10, priority 3).
USER_TEMPLATE = """Language: python
Function name: {function_name}
Requested bug category: {bug_category}

Clean, correct source:
```python
{clean_code}
```

Return ONLY a JSON object with these keys:
  buggy_code              - the full function source with the bug applied, nothing else
  diff_summary            - one sentence naming the exact line/expression you changed
  bug_category            - echo the requested category
  why_its_a_bug           - 1-2 sentences on the incorrect behaviour this produces
  hint_level_description  - a nudge toward the right area WITHOUT naming the fix

The buggy_code must define a function named exactly `{function_name}` and must be
valid, parseable Python."""

REQUIRED_KEYS = ["buggy_code", "diff_summary", "bug_category", "why_its_a_bug"]


def inject_bug(clean_code: str, function_name: str, bug_category: str) -> Dict[str, Any]:
    """Ask Bedrock for one injected bug. Raises on an unusable response.

    The caller (the authoring pipeline) is responsible for verifying that the
    returned code actually fails the hidden tests -- this function only checks
    that the response is well-formed and parseable Python.
    """
    user_text = USER_TEMPLATE.format(
        function_name=function_name,
        bug_category=bug_category,
        clean_code=clean_code.strip(),
    )
    raw, transport = bedrock_client.invoke(SYSTEM_PROMPT, user_text)
    result = bedrock_client.parse_json_response(raw, REQUIRED_KEYS)

    buggy_code = _strip_fences(str(result["buggy_code"]))
    _assert_parses(buggy_code, function_name)

    return {
        "buggy_code": buggy_code,
        "diff_summary": str(result["diff_summary"]).strip(),
        "bug_category": str(result.get("bug_category", bug_category)).strip(),
        "why_its_a_bug": str(result["why_its_a_bug"]).strip(),
        "hint_level_description": str(result.get("hint_level_description", "")).strip(),
        "transport": transport,
    }


def _strip_fences(code: str) -> str:
    text = code.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip() + "\n"


def _assert_parses(code: str, function_name: str) -> None:
    import ast

    tree = ast.parse(code)  # raises SyntaxError, which the pipeline reports
    names: List[str] = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if function_name not in names:
        raise ValueError(f"Injected code does not define '{function_name}' (found {names}).")
