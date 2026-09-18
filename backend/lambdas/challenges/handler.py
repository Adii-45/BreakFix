"""GET /challenges -- list the seeded challenges (PRD Section 7, F1).

Public fields only. buggy_code, ground_truth_diff and test_cases never appear in
this response: the hidden tests are the ground truth for correctness and must
not be reachable from the browser.

Two fields exist purely so the dashboard can show something real:
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
)


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})
    rows = storage.get_store().list_challenges()
    return http.ok(
        {"challenges": [{k: c.get(k) for k in PUBLIC_FIELDS if k in c} for c in rows]}
    )
