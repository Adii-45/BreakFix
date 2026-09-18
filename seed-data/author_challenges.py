#!/usr/bin/env python3
"""Offline challenge authoring pipeline (PRD Section 5.3).

Runs on a laptop before the demo -- never in the request path. For each
challenge directory it performs the PRD's steps in order:

  1. Write hidden tests      -- read tests.json
  2. Verify against CLEAN    -- clean.py must pass 100% of them
  3. Bug injection           -- Bug Injector Agent (Bedrock) with --use-agent,
                                otherwise the reviewed buggy.py already on disk
  4. Verify the bug breaks   -- buggy.py must fail at least one hidden test,
     something                 else it is discarded
  5. Human review            -- see REVIEW.md; enforced as a manual gate
  6. Seed storage            -- assemble the Challenges row and write it to
                                DynamoDB (or the local store)

Usage:
    python seed-data/author_challenges.py                  # verify + seed locally
    python seed-data/author_challenges.py --use-agent      # regenerate bugs via Bedrock
    python seed-data/author_challenges.py --storage dynamodb --no-write  # dry run
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

CHALLENGE_ROOT = os.path.join(HERE, "challenges")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _preview(code, lines=4):
    """First few non-blank lines of the buggy function, for the challenge card.

    Safe to expose: the student sees the whole function the instant they start.
    The ground-truth diff is never previewed anywhere.
    """
    kept = [line for line in code.splitlines() if line.strip()][:lines]
    return "\n".join(kept)


def discover():
    return sorted(
        os.path.join(CHALLENGE_ROOT, name)
        for name in os.listdir(CHALLENGE_ROOT)
        if os.path.isdir(os.path.join(CHALLENGE_ROOT, name))
    )


def build_record(directory, use_agent=False, verbose=True):
    from test_runner import runner

    meta = _read_json(os.path.join(directory, "meta.json"))
    tests = _read_json(os.path.join(directory, "tests.json"))
    clean_code = _read(os.path.join(directory, "clean.py"))
    function_name = meta["function_name"]
    log = (lambda msg: print(msg)) if verbose else (lambda msg: None)

    log(f"\n=== {meta['challenge_id']}  ({meta['repo_name']} :: {function_name}) ===")

    if not 2 <= len(tests) <= 4:
        raise SystemExit(f"  FAIL: PRD 5.3 requires 2-4 hidden tests, found {len(tests)}")

    # -- Step 2: the tests must pass against the clean version FIRST ---------
    clean_result = runner.run_tests(clean_code, function_name, tests)
    if clean_result["tests_passed"] != clean_result["tests_total"]:
        for t in clean_result["per_test"]:
            if not t["passed"]:
                log(f"    [FAIL] {t['name']}: {t['error']}")
        raise SystemExit(f"  FAIL: hidden tests do not pass against clean.py -- fix the tests before injecting a bug")
    log(f"  [ok] clean.py passes all {clean_result['tests_total']} hidden tests")

    # -- Step 3: bug injection ----------------------------------------------
    if use_agent:
        from agents import bug_injector

        log(f"  ... invoking Bug Injector Agent (category: {meta['bug_category']})")
        injected = bug_injector.inject_bug(clean_code, function_name, meta["bug_category"])
        buggy_code = injected["buggy_code"]
        ground_truth = {
            "bug_category": injected["bug_category"],
            "diff_summary": injected["diff_summary"],
            "why_its_a_bug": injected["why_its_a_bug"],
            "hint_level_description": injected["hint_level_description"],
            "generated_by": f"bug-injector-agent ({injected['transport']})",
        }
        with open(os.path.join(directory, "buggy.py"), "w", encoding="utf-8") as fh:
            fh.write(buggy_code)
        with open(os.path.join(directory, "ground_truth.json"), "w", encoding="utf-8") as fh:
            json.dump(ground_truth, fh, indent=2)
        log("  [ok] agent returned a parseable buggy function (written to disk for review)")
    else:
        buggy_code = _read(os.path.join(directory, "buggy.py"))
        ground_truth = _read_json(os.path.join(directory, "ground_truth.json"))

    # -- Step 4: the bug must actually break something ----------------------
    buggy_result = runner.run_tests(buggy_code, function_name, tests)
    if buggy_result["tests_passed"] == buggy_result["tests_total"]:
        raise SystemExit(
            "  DISCARD: the injected bug does not fail a single hidden test -- "
            "regenerate or pick a different bug category (PRD 5.3)"
        )
    failing = buggy_result["tests_total"] - buggy_result["tests_passed"]
    log(f"  [ok] buggy.py fails {failing}/{buggy_result['tests_total']} hidden tests")

    # -- Step 5: mission brief -------------------------------------------------
    from agents import brief_writer

    brief_path = os.path.join(directory, "brief.json")
    if use_agent:
        log("  ... invoking Mission Brief Agent")
        brief = brief_writer.write_brief(
            repo_name=meta["repo_name"],
            source_path=meta.get("source_path", ""),
            function_name=function_name,
            clean_code=clean_code,
            buggy_code=buggy_code,
            ground_truth=ground_truth,
        )
        with open(brief_path, "w", encoding="utf-8") as fh:
            json.dump(brief, fh, indent=2)
    else:
        brief = _read_json(brief_path)

    # The brief is student-facing, so it is gated exactly like the bug is: it
    # must describe the symptom without handing over the fix.
    brief_writer.assert_no_leak(
        {"purpose": brief["student_facing_summary"], "symptom": brief["symptom_description"]},
        ground_truth, clean_code, buggy_code,
    )
    log("  [ok] mission brief passes the leak check (no fix, no changed identifiers)")

    return {
        "challenge_id": meta["challenge_id"],
        "repo_name": meta["repo_name"],
        "repo_url": meta.get("repo_url", ""),
        "license": meta.get("license", ""),
        "source_path": meta.get("source_path", ""),
        "function_name": function_name,
        "buggy_code": buggy_code,
        "ground_truth_diff": json.dumps(ground_truth, indent=2),
        "difficulty": meta.get("difficulty", "medium"),
        "bug_category": meta.get("bug_category", ground_truth.get("bug_category", "unknown")),
        "test_cases": json.dumps(tests),
        # Count only -- the assertions themselves stay hidden. Stored at seed
        # time so the serving projection never has to read test_cases at all.
        "tests_total": len(tests),
        "code_preview": _preview(buggy_code),
        "language": meta.get("language", "python"),
        "time_limit_seconds": int(meta.get("time_limit_seconds", 300)),
        # -- mission brief (Part 1) -------------------------------------------
        "student_facing_summary": brief["student_facing_summary"],
        "symptom_description": brief["symptom_description"],
        "source_url": brief_writer.source_url(meta.get("repo_url", ""), meta.get("source_path", "")),
        # Seeded challenges are published by definition; live-authored ones land
        # in pending_review and are only published by an explicit human click.
        "status": "published",
        "created_at": int(time.time()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-agent", action="store_true",
                        help="regenerate every bug through the Bedrock Bug Injector Agent")
    parser.add_argument("--storage", choices=["local", "dynamodb"], default=None,
                        help="override BREAKFIX_STORAGE for this run")
    parser.add_argument("--no-write", action="store_true", help="verify only, do not seed storage")
    parser.add_argument("--only", help="a single challenge_id to process")
    args = parser.parse_args()

    if args.storage:
        os.environ["BREAKFIX_STORAGE"] = args.storage
    elif not os.environ.get("BREAKFIX_STORAGE"):
        os.environ["BREAKFIX_STORAGE"] = "local"

    from common import storage

    records = []
    for directory in discover():
        if args.only and os.path.basename(directory) != args.only:
            continue
        records.append(build_record(directory, use_agent=args.use_agent))

    if args.no_write:
        print(f"\nVerified {len(records)} challenge(s). --no-write set, nothing seeded.")
        return

    store = storage.get_store()
    for record in records:
        store.put_challenge(record)
    print(f"\nSeeded {len(records)} challenge(s) into {os.environ['BREAKFIX_STORAGE']} storage.")
    if args.use_agent:
        print("REMINDER: every agent-generated bug needs human review before the demo (PRD 5.3).")


if __name__ == "__main__":
    main()
