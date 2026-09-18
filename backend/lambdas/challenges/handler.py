"""GET /challenges -- list the seeded challenges (PRD Section 7, F1).

Public fields only. buggy_code, ground_truth_diff and test_cases never appear in
this response: the hidden tests are the ground truth for correctness and must
not be reachable from the browser.

The mission brief (student_facing_summary, symptom_description, source_url) is
served in full: it is written specifically for the student and is leak-checked
at authoring time so it can describe the symptom without revealing the fix.

Two further fields exist purely so the dashboard can show something real:
  tests_total   -- how MANY hidden tests there are, never what they assert
  code_preview  -- the first few lines of the buggy function, which the student
                   sees in full the moment they start anyway
Notably absent: any preview of the ground-truth diff. The card mock-ups show one,
but rendering the diff on the challenge list would hand over the answer before
the timer starts, so it is deliberately not served.
"""
from common import http, storage

PUBLIC_FIELDS = (
    "challenge_id",
    "repo_name",
    "function_name",
    "difficulty",
    "language",
    "time_limit_seconds",
    "tests_total",
    "code_preview",
    "student_facing_summary",
    "symptom_description",
    "source_url",
    "status",
)


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    include_pending = (event.get("queryStringParameters") or {}).get("include_pending") == "1"
    rows = storage.get_store().list_challenges()
    if not include_pending:
        # Anything awaiting review is invisible to normal users. A challenge only
        # becomes visible after an explicit human approval (Part 3).
        rows = [c for c in rows if c.get("status", "published") == "published"]
    return http.ok(
        {"challenges": [{k: c.get(k) for k in PUBLIC_FIELDS if k in c} for c in rows]}
    )
