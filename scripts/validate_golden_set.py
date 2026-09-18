#!/usr/bin/env python3
"""Golden-set validation (PRD Section 12.3).

Two separate things are checked for every seed challenge, and a challenge is not
accepted into the final seed set until BOTH hold:

  1. Did the Test Runner produce the RIGHT pass/fail?  (a factual check)
  2. Was the Evaluator Agent's feedback sound, in-band, and never contradictory
     to that result?                                    (a judgment check)

The five golden case types come straight from the PRD table. The two "broken
change" variants are generated from each challenge's function name rather than
checked in per challenge -- they are identical in shape for every challenge.

Usage:
    python scripts/validate_golden_set.py
    python scripts/validate_golden_set.py --only challenge-03
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "seed-data"))

CHALLENGE_ROOT = os.path.join(ROOT, "seed-data", "challenges")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def broken_syntax_source(function_name):
    return f"def {function_name}(*args, **kwargs)\n    return None\n"


def infinite_loop_source(function_name):
    return f"def {function_name}(*args, **kwargs):\n    while True:\n        pass\n"


def golden_cases(directory, meta):
    """(label, source, expected_outcome, score_lo, score_hi)."""
    fn = meta["function_name"]
    golden = os.path.join(directory, "golden")
    return [
        ("exact ground-truth fix", _read(os.path.join(directory, "clean.py")), "all_pass", 90, 100),
        ("correct fix, different approach", _read(os.path.join(golden, "alt_fix.py")), "all_pass", 70, 100),
        ("masks the symptom", _read(os.path.join(golden, "masked_fix.py")), "some_fail", 20, 50),
        ("no change submitted", _read(os.path.join(directory, "buggy.py")), "same_as_buggy", 0, 0),
        ("broken change (syntax error)", broken_syntax_source(fn), "all_fail", 0, 0),
        ("broken change (infinite loop)", infinite_loop_source(fn), "all_fail", 0, 0),
    ]


def check_outcome(expected, result, buggy_baseline):
    passed, total = result["tests_passed"], result["tests_total"]
    if expected == "all_pass":
        return passed == total, f"{passed}/{total} passed"
    if expected == "some_fail":
        return 0 < passed < total, f"{passed}/{total} passed (expected a partial pass)"
    if expected == "all_fail":
        ok = passed == 0 and result["runner_status"] != "ok" or passed == 0
        return ok, f"{passed}/{total} passed, status={result['runner_status']}"
    if expected == "same_as_buggy":
        same = [t["passed"] for t in result["per_test"]] == [t["passed"] for t in buggy_baseline["per_test"]]
        return same, f"{passed}/{total} passed (buggy baseline {buggy_baseline['tests_passed']}/{total})"
    raise ValueError(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only")
    parser.add_argument("--skip-agent", action="store_true", help="test-runner checks only")
    args = parser.parse_args()
    os.environ.setdefault("BREAKFIX_STORAGE", "local")

    from agents import evaluator
    from common import diffing
    from test_runner import runner

    failures = []
    sources_seen = set()

    directories = sorted(
        os.path.join(CHALLENGE_ROOT, d)
        for d in os.listdir(CHALLENGE_ROOT)
        if os.path.isdir(os.path.join(CHALLENGE_ROOT, d)) and (not args.only or d == args.only)
    )

    for directory in directories:
        meta = _read_json(os.path.join(directory, "meta.json"))
        tests = _read_json(os.path.join(directory, "tests.json"))
        buggy_code = _read(os.path.join(directory, "buggy.py"))
        ground_truth = json.dumps(_read_json(os.path.join(directory, "ground_truth.json")), indent=2)
        fn = meta["function_name"]

        baseline = runner.run_tests(buggy_code, fn, tests)
        print(f"\n=== {meta['challenge_id']} :: {fn} ===")
        print(f"  {'case':<34} {'runner':<10} {'tests':<10} {'score':<7} evaluator")

        feedback_texts = []
        for label, source, expected, lo, hi in golden_cases(directory, meta):
            result = runner.run_tests(source, fn, tests)
            ok, detail = check_outcome(expected, result, baseline)

            eval_out = {"score": 0, "process_feedback": "(skipped)", "correctness_notes": "", "feedback_source": "skipped"}
            if not args.skip_agent:
                eval_out = evaluator.evaluate(
                    buggy_code=buggy_code,
                    ground_truth_diff=ground_truth,
                    submitted_code=source,
                    test_result=result,
                    student_diff=diffing.unified_diff(buggy_code, source),
                    diff_stats=diffing.diff_stats(buggy_code, source),
                )
                sources_seen.add(eval_out["feedback_source"])
                feedback_texts.append(eval_out["process_feedback"])

            score = eval_out["score"]
            all_passed = result["tests_total"] > 0 and result["tests_passed"] == result["tests_total"]
            score_ok = args.skip_agent or lo <= score <= hi
            # The hard invariant: the score can never imply the wrong verdict.
            contradicts = (not args.skip_agent) and ((all_passed and score < 60) or (not all_passed and score > 50))

            status = "OK " if (ok and score_ok and not contradicts) else "BAD"
            print(f"  {status} {label:<32} {result['runner_status']:<10} {detail:<22} {score:<5} {eval_out['feedback_source']}")
            if not ok:
                failures.append(f"{meta['challenge_id']} / {label}: wrong test outcome -- {detail}")
            if not score_ok:
                failures.append(f"{meta['challenge_id']} / {label}: score {score} outside expected {lo}-{hi}")
            if contradicts:
                failures.append(f"{meta['challenge_id']} / {label}: score {score} contradicts the test outcome")

        # "never generic praise or generic criticism" -- at minimum, the six
        # cases must not all receive the same sentence.
        if feedback_texts and len(set(feedback_texts)) < 4:
            failures.append(f"{meta['challenge_id']}: evaluator feedback is not specific enough across golden cases")

    print("\n" + "=" * 78)
    if sources_seen:
        print(f"Evaluator transport(s) exercised: {', '.join(sorted(sources_seen))}")
    if failures:
        print(f"GOLDEN SET FAILED -- {len(failures)} problem(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("GOLDEN SET PASSED -- every seed challenge is accepted (PRD 12.3).")


if __name__ == "__main__":
    main()
