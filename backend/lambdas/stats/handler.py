"""GET /stats -- real aggregate counts for the dashboard headline figures.

Every number here is derived from rows that actually exist in DynamoDB. There is
no synthetic traffic, no seeded activity and no padding: if nobody has submitted
anything yet, `submissions` is 0 and the UI is expected to say so rather than
invent a figure. Values that would be meaningless with no data (average solve
time with zero solves) come back as null, not as a placeholder number.
"""
from typing import Dict, List

from common import config, http, storage


def _observed_difficulty(pass_rate):
    """Map a real pass rate onto the same vocabulary as the curated label."""
    if pass_rate is None:
        return None
    if pass_rate >= 0.7:
        return "easy"
    if pass_rate >= 0.35:
        return "medium"
    return "hard"


def _percentile(values: List[int], pct: float):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * pct)))
    return ordered[index]


@http.handle_exceptions
def handler(event, context):  # noqa: ANN001
    if event.get("httpMethod") == "OPTIONS":
        return http.respond(204, {})

    store = storage.get_store()
    challenges = store.list_challenges()
    results = store.all_results()

    solved = [r for r in results if r.get("correct")]
    solve_times = [int(r["time_taken_seconds"]) for r in solved if r.get("time_taken_seconds") is not None]

    per_challenge: Dict[str, Dict] = {}
    for challenge in challenges:
        cid = challenge["challenge_id"]
        attempts = [r for r in results if r.get("challenge_id") == cid]
        wins = [r for r in attempts if r.get("correct")]
        win_times = [int(r["time_taken_seconds"]) for r in wins if r.get("time_taken_seconds") is not None]

        # --- difficulty calibration (Part 4.1) ----------------------------
        # A pass rate off one or two attempts is noise, so it is only reported
        # once there is a real sample. Below that, `calibrated` is false and the
        # UI keeps the curated static label.
        sample = len(attempts)
        calibrated = sample >= config.CALIBRATION_MIN_SAMPLE
        pass_rate = round(len(wins) / sample, 3) if sample else None

        per_challenge[cid] = {
            "attempts": sample,
            "solved": len(wins),
            "best_score": max((int(r.get("score", 0)) for r in attempts), default=None),
            "best_time_seconds": min(win_times, default=None),
            "sample_size": sample,
            "min_sample": config.CALIBRATION_MIN_SAMPLE,
            "calibrated": calibrated,
            "static_difficulty": challenge.get("difficulty", "medium"),
            # Only populated once the sample is meaningful.
            "pass_rate": pass_rate if calibrated else None,
            "median_solve_seconds": _percentile(win_times, 0.5) if calibrated else None,
            "observed_difficulty": _observed_difficulty(pass_rate) if calibrated else None,
        }

    return http.ok(
        {
            "challenges_available": len(challenges),
            "hidden_tests_total": sum(int(c.get("tests_total") or 0) for c in challenges),
            "repos_covered": len({c.get("repo_name") for c in challenges if c.get("repo_name")}),
            "sessions_started": store.count_sessions(),
            "submissions_evaluated": len(results),
            "submissions_solved": len(solved),
            "median_solve_seconds": _percentile(solve_times, 0.5),
            "fastest_solve_seconds": min(solve_times) if solve_times else None,
            "per_challenge": per_challenge,
        }
    )
