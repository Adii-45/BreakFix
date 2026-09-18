"""Mission Brief Agent.

Runs OFFLINE, once per seed challenge, alongside the Bug Injector. It answers
the two questions a student actually needs before they start reading code:

  * what does this function do in the real codebase?  -> student_facing_summary
  * what goes wrong, observably?                      -> symptom_description

It must never reveal the fix. That is not left to the prompt alone: every
generated brief goes through `assert_no_leak()`, which rejects text containing
the changed line, the identifiers that differ between the correct and buggy
versions, or the bug category name. A brief that fails the check is discarded
exactly like a bug that fails to break a test (PRD 5.3).
"""
import ast
import re
from typing import Any, Dict, List

from agents import bedrock_client

SYSTEM_PROMPT = """You write short mission briefs for a debugging practice tool.
You are given a real open-source function, the bug that was deliberately
injected into it, and the ground-truth explanation of that bug.

Write two things for the student:

1. purpose - what this function does in the real codebase, in plain English,
   for someone who has never seen the project. Name a concrete input and
   output. Mention where the project uses it. 2 sentences maximum.

2. symptom - what the student would OBSERVE going wrong, described as a user
   of the function would experience it. Describe the wrong BEHAVIOUR only.

Hard constraints on the symptom:
  - NEVER name the line, expression, variable, operator or constant involved
  - NEVER say what the fix is, or which direction a comparison should go
  - NEVER name the bug category (off-by-one, wrong condition, etc.)
  - Describe the observable effect, not the cause. "Returns the wrong suffix
    for numbers in the teens" is good. "The membership test is missing 13" is
    not - that gives it away.
  - 1 sentence, maximum 25 words.

Return JSON: { purpose, symptom }"""

USER_TEMPLATE = """Repository: {repo_name}
File: {source_path}
Function: {function_name}

Correct implementation:
```python
{clean_code}
```

Ground truth of the injected bug (for YOUR understanding only - the student
must not be able to reconstruct it from what you write):
{ground_truth}

Return ONLY the JSON object."""

REQUIRED_KEYS = ["purpose", "symptom"]

# Words that would give the game away if they appeared in a symptom description.
BANNED_IN_SYMPTOM = {
    "off-by-one", "off by one", "wrong condition", "swapped variable",
    "incorrect boundary", "wrong operator", "inverted logic", "missing update",
    "should be", "instead of using", "change the", "replace the", "the fix",
}


class BriefLeak(ValueError):
    """Raised when a brief would hand the student the answer."""


def _identifiers(text: str) -> set:
    """Real code identifiers only.

    Parsed from the AST rather than scraped from the raw text, so prose inside
    docstrings and comments is not mistaken for code. Scraping produced false
    rejections: a mutation reformats the source, the docstring's wording lands
    in the diff, and an entirely innocent brief gets blocked for "naming an
    identifier" that was only ever an English word.
    """
    names: set = set()
    try:
        tree = ast.parse(text or "")
    except SyntaxError:
        return {tok for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or "")}

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            for arg in getattr(getattr(node, "args", None), "args", []) or []:
                names.add(arg.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return {n for n in names if len(n) >= 3}


def assert_no_leak(brief: Dict[str, str], ground_truth: Dict[str, Any], clean_code: str, buggy_code: str) -> None:
    """Reject a brief that reproduces the changed line or its distinguishing tokens.

    The check is deliberately blunt: it compares the brief against the exact
    lines recorded in ground_truth, and against the set of identifiers that
    appear in one version of the function but not the other. Anything that
    survives this is describing behaviour, not implementation.
    """
    blob = f"{brief.get('purpose', '')} {brief.get('symptom', '')}".lower()

    for key in ("correct_line", "buggy_line"):
        line = (ground_truth.get(key) or "").strip().lower()
        if line and len(line) > 8 and line in blob:
            raise BriefLeak(f"brief reproduces the {key}: {line!r}")

    # Guard the length explicitly: an empty diff_summary would otherwise make
    # `"" in blob` true and reject every brief.
    summary = (ground_truth.get("diff_summary") or "").strip().lower()
    if len(summary) >= 40 and summary[:40] in blob:
        raise BriefLeak("brief reproduces the diff summary verbatim")

    symptom = (brief.get("symptom") or "").lower()
    for phrase in BANNED_IN_SYMPTOM:
        if phrase in symptom:
            raise BriefLeak(f"symptom names the cause, not the effect: {phrase!r}")

    category = (ground_truth.get("bug_category") or "").replace("-", " ").lower()
    if category and category in blob:
        raise BriefLeak(f"brief names the bug category: {category!r}")

    # Identifiers unique to one side of the diff point straight at the change.
    delta = _identifiers(clean_code) ^ _identifiers(buggy_code)
    leaked = [tok for tok in delta if len(tok) > 3 and tok.lower() in blob]
    if leaked:
        raise BriefLeak(f"brief names identifiers that differ between versions: {leaked}")


def write_brief(
    repo_name: str,
    source_path: str,
    function_name: str,
    clean_code: str,
    buggy_code: str,
    ground_truth: Dict[str, Any],
) -> Dict[str, str]:
    """Ask Bedrock for a brief. Raises BriefLeak if it gives the answer away."""
    import json

    user_text = USER_TEMPLATE.format(
        repo_name=repo_name,
        source_path=source_path,
        function_name=function_name,
        clean_code=clean_code.strip(),
        ground_truth=json.dumps(ground_truth, indent=2),
    )
    raw, transport = bedrock_client.invoke(SYSTEM_PROMPT, user_text, max_tokens=600)
    parsed = bedrock_client.parse_json_response(raw, REQUIRED_KEYS)

    brief = {
        "student_facing_summary": str(parsed["purpose"]).strip(),
        "symptom_description": str(parsed["symptom"]).strip(),
        "generated_by": f"brief-writer-agent ({transport})",
    }
    assert_no_leak(
        {"purpose": brief["student_facing_summary"], "symptom": brief["symptom_description"]},
        ground_truth, clean_code, buggy_code,
    )
    return brief


def source_url(repo_url: str, source_path: str, branch: str = "main") -> str:
    """Permalink to the real function in the real repository, for credibility."""
    if not repo_url or not source_path:
        return ""
    return f"{repo_url.rstrip('/')}/blob/{branch}/{source_path.lstrip('/')}"
