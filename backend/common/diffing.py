"""Diff capture (PRD Section 5.1, stage 5).

The student's diff against the buggy code is the single most useful signal the
Evaluator Agent gets: it shows *what they changed*, which is the whole basis for
judging debugging process rather than just outcome.
"""
import difflib
from typing import Dict, List


def unified_diff(before: str, after: str, before_label: str = "buggy", after_label: str = "submitted") -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=before_label,
        tofile=after_label,
        n=3,
    )
    return "".join(diff)


def diff_stats(before: str, after: str) -> Dict[str, int]:
    """Cheap structural signal: how surgical was the edit?

    Used both by the Evaluator prompt (minimal fix vs broad rewrite) and by the
    fallback scorer when Bedrock is unavailable.
    """
    before_lines: List[str] = before.splitlines()
    after_lines: List[str] = after.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return {
        "lines_added": added,
        "lines_removed": removed,
        "lines_changed": added + removed,
        "total_lines_before": len(before_lines),
        "similarity_pct": int(round(matcher.ratio() * 100)),
    }


def is_unchanged(before: str, after: str) -> bool:
    """Whitespace-insensitive equality -- reformatting is not a fix."""
    return before.strip() == after.strip()
