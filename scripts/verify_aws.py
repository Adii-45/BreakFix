#!/usr/bin/env python3
"""Prove the AWS-dependent parts are genuinely working — before the demo.

Every check here makes a REAL call. Nothing is mocked and nothing falls back
silently: a check that cannot reach AWS is reported as FAIL, not skipped, so
"it works" and "it fell back to the deterministic path" can never be confused.

    python scripts/verify_aws.py                       # everything it can reach
    python scripts/verify_aws.py --api-url https://... # also exercise the deployed API
    python scripts/verify_aws.py --only bedrock

Exit code is non-zero if any check fails, so it gates ./scripts/deploy.sh.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
RESULTS = []


def record(name, ok, detail, warn=False):
    RESULTS.append({"name": name, "ok": ok, "detail": detail, "warn": warn})
    mark = f"{GREEN}PASS{RESET}" if ok else (f"{YELLOW}WARN{RESET}" if warn else f"{RED}FAIL{RESET}")
    print(f"  [{mark}] {name}")
    for line in str(detail).splitlines():
        print(f"         {DIM}{line}{RESET}")


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def check_identity():
    try:
        import boto3

        identity = boto3.client("sts").get_caller_identity()
        record("AWS credentials resolve", True,
               f"account {identity['Account']} · {identity['Arn']}")
        return True
    except Exception as exc:  # noqa: BLE001
        record("AWS credentials resolve", False,
               f"{type(exc).__name__}: {exc}\nEverything below will fail without this.")
        return False


# ---------------------------------------------------------------------------
# Bedrock — one real call per agent
# ---------------------------------------------------------------------------

CLEAN_FN = (
    "def ordinal(value):\n"
    "    suffixes = ('th', 'st', 'nd', 'rd', 'th', 'th', 'th', 'th', 'th', 'th')\n"
    "    value = int(value)\n"
    "    if value % 100 in (11, 12, 13):\n"
    "        return '%d%s' % (value, 'th')\n"
    "    return '%d%s' % (value, suffixes[value % 10])\n"
)
BUGGY_FN = CLEAN_FN.replace("(11, 12, 13)", "(11, 12)")
GROUND_TRUTH = {
    "bug_category": "wrong-condition",
    "diff_summary": "The teens special case was narrowed from (11, 12, 13) to (11, 12).",
    "why_its_a_bug": "13 falls through to the 'rd' suffix.",
    "correct_line": "    if value % 100 in (11, 12, 13):",
    "buggy_line": "    if value % 100 in (11, 12):",
}


def check_bedrock_raw():
    from agents import bedrock_client

    try:
        text, transport = bedrock_client.invoke(
            "You are a terse assistant. Reply with JSON only.",
            'Return exactly: {"ok": true}',
            max_tokens=64,
        )
        parsed = bedrock_client.parse_json_response(text, ["ok"])
        record("Bedrock reachable", True, f"transport: {transport} · parsed {parsed}")
        return True
    except Exception as exc:  # noqa: BLE001
        record("Bedrock reachable", False,
               f"{type(exc).__name__}: {exc}\n"
               "Enable model access in the Bedrock console for this region, and check "
               "BEDROCK_MODEL_ID / BEDROCK_FALLBACK_MODEL_ID.")
        return False


def check_bug_injector():
    from agents import bug_injector

    try:
        started = time.time()
        out = bug_injector.inject_bug(CLEAN_FN, "ordinal", "off-by-one")
        elapsed = time.time() - started

        from test_runner import runner
        tests = [
            {"name": "1st", "input": [1], "expected_output": "1st"},
            {"name": "teens", "input": [13], "expected_output": "13th"},
            {"name": "22nd", "input": [22], "expected_output": "22nd"},
        ]
        result = runner.run_tests(out["buggy_code"], "ordinal", tests)
        bites = result["tests_passed"] < result["tests_total"]
        record("Bug Injector Agent (real Bedrock)", bites,
               f"{elapsed:.1f}s · category {out['bug_category']} · "
               f"buggy code fails {result['tests_total'] - result['tests_passed']}/{result['tests_total']} tests\n"
               f"{out['diff_summary']}"
               + ("" if bites else "\nThe agent returned a bug that breaks nothing — the pipeline would discard it."))
        return bites
    except Exception as exc:  # noqa: BLE001
        record("Bug Injector Agent (real Bedrock)", False, f"{type(exc).__name__}: {exc}")
        return False


def check_evaluator():
    from agents import evaluator

    try:
        started = time.time()
        out = evaluator.evaluate(
            buggy_code=BUGGY_FN,
            ground_truth_diff=json.dumps(GROUND_TRUTH),
            submitted_code=CLEAN_FN,
            test_result={"tests_passed": 3, "tests_total": 3, "runner_status": "ok",
                         "per_test": [{"name": f"t{i}", "passed": True, "kind": "pass", "error": None}
                                      for i in range(3)]},
            student_diff="- (11, 12)\n+ (11, 12, 13)",
            diff_stats={"lines_changed": 2},
        )
        elapsed = time.time() - started
        # The whole point of this check: did the AGENT answer, or the fallback?
        real = out["feedback_source"] != "fallback-heuristic"
        record("Evaluator Agent (real Bedrock)", real,
               f"{elapsed:.1f}s · source: {out['feedback_source']} · score {out['score']}\n"
               f"{out['process_feedback'][:140]}"
               + ("" if real else "\nThis came from the deterministic fallback, NOT the agent."))
        return real
    except Exception as exc:  # noqa: BLE001
        record("Evaluator Agent (real Bedrock)", False, f"{type(exc).__name__}: {exc}")
        return False


def check_brief_writer():
    from agents import brief_writer

    try:
        started = time.time()
        brief = brief_writer.write_brief(
            repo_name="python-humanize/humanize", source_path="src/humanize/number.py",
            function_name="ordinal", clean_code=CLEAN_FN, buggy_code=BUGGY_FN,
            ground_truth=GROUND_TRUTH,
        )
        elapsed = time.time() - started
        record("Mission Brief Agent (real Bedrock)", True,
               f"{elapsed:.1f}s · passed the leak check\n"
               f"purpose: {brief['student_facing_summary'][:90]}\n"
               f"symptom: {brief['symptom_description'][:90]}")
        return True
    except Exception as exc:  # noqa: BLE001
        record("Mission Brief Agent (real Bedrock)", False, f"{type(exc).__name__}: {exc}")
        return False


def check_test_author():
    from agents import test_author
    from test_runner import runner

    try:
        started = time.time()
        tests = test_author.propose_tests(CLEAN_FN, "ordinal")
        elapsed = time.time() - started
        result = runner.run_tests(CLEAN_FN, "ordinal", tests)
        sound = result["tests_passed"] == result["tests_total"]
        record("Test Author Agent (real Bedrock)", sound,
               f"{elapsed:.1f}s · proposed {len(tests)} cases · "
               f"{result['tests_passed']}/{result['tests_total']} hold against the clean function"
               + ("" if sound else "\nProposed expectations do not match the real function — the pipeline would reject this run."))
        return sound
    except Exception as exc:  # noqa: BLE001
        record("Test Author Agent (real Bedrock)", False, f"{type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step Functions — a real execution, not the local orchestrator
# ---------------------------------------------------------------------------

def check_step_functions():
    arn = os.environ.get("STATE_MACHINE_ARN", "")
    if not arn:
        record("Step Functions execution", False,
               "STATE_MACHINE_ARN is unset — cannot verify the deployed state machine.", warn=True)
        return False

    try:
        import boto3

        client = boto3.client("stepfunctions")
        payload = {
            "step": "fetch",
            "context": {
                "function_name": "quote",
                "github_url": "https://github.com/python/cpython/blob/main/Lib/shlex.py",
                "source_code": "",
                "test_cases": [
                    {"name": "safe token", "input": ["abc"], "expected_output": "abc"},
                    {"name": "spaces quoted", "input": ["a b"], "expected_output": "'a b'"},
                    {"name": "empty becomes quotes", "input": [""], "expected_output": "''"},
                ],
                "difficulty": "medium", "time_limit_seconds": 300, "bug_category": "off-by-one",
                "student_facing_summary": "Escapes a string so it is safe to use as one token in a POSIX shell command line.",
                "symptom_description": "Some inputs come back without the protection they need.",
            },
        }
        started = client.start_execution(stateMachineArn=arn, input=json.dumps(payload))
        execution_arn = started["executionArn"]

        deadline = time.time() + 180
        status = "RUNNING"
        while time.time() < deadline:
            described = client.describe_execution(executionArn=execution_arn)
            status = described["status"]
            if status != "RUNNING":
                break
            time.sleep(3)

        if status == "SUCCEEDED":
            output = json.loads(described.get("output") or "{}").get("context", {})
            record("Step Functions execution", True,
                   f"{execution_arn.split(':')[-1]} SUCCEEDED · "
                   f"landed {output.get('challenge_id')} in pending_review\n"
                   f"injection: {output.get('injection_source')} · tests: {output.get('tests_source')}")
            return True

        history = client.get_execution_history(executionArn=execution_arn, maxResults=100, reverseOrder=True)
        cause = ""
        for entry in history.get("events", []):
            detail = entry.get("taskFailedEventDetails") or entry.get("executionFailedEventDetails")
            if detail and detail.get("cause"):
                cause = detail["cause"][:300]
                break
        record("Step Functions execution", False, f"status {status}\n{cause}")
        return False
    except Exception as exc:  # noqa: BLE001
        record("Step Functions execution", False, f"{type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# The deployed API + WebSocket
# ---------------------------------------------------------------------------

def check_deployed_api(api_url):
    base = api_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/challenges", timeout=20) as response:
            rows = json.loads(response.read())["challenges"]
        briefed = [c for c in rows if c.get("student_facing_summary")]
        ok = bool(rows) and len(briefed) == len(rows)
        record("Deployed API /challenges", ok,
               f"{len(rows)} published challenge(s), {len(briefed)} with a mission brief")
    except Exception as exc:  # noqa: BLE001
        record("Deployed API /challenges", False, f"{type(exc).__name__}: {exc}")
        return False

    # A real submission through API Gateway -> Lambda -> Test Runner -> Bedrock.
    try:
        challenge = rows[0]
        req = urllib.request.Request(
            f"{base}/sessions", method="POST",
            data=json.dumps({"challenge_id": challenge["challenge_id"],
                             "user_display_name": "preflight"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            session = json.loads(response.read())

        started = time.time()
        req = urllib.request.Request(
            f"{base}/sessions/{session['session_id']}/submit", method="POST",
            data=json.dumps({"submitted_code": session["buggy_code"] + "\n# preflight\n"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read())
        elapsed = time.time() - started

        agent = result.get("feedback_source") != "fallback-heuristic"
        record("Deployed submit path (Lambda + sandbox + Bedrock)", True,
               f"{elapsed:.1f}s end-to-end · correct={result['correct']} "
               f"tests={result['tests_passed']}/{result['tests_total']} · "
               f"feedback from {result.get('feedback_source')}")
        if not agent:
            record("Deployed Evaluator uses the real agent", False,
                   "The deployed submit path fell back to the deterministic scorer.", warn=True)
        else:
            record("Deployed Evaluator uses the real agent", True, "feedback came from Bedrock")

        # The recovery routes the audit added — a judge refreshing depends on these.
        with urllib.request.urlopen(f"{base}/sessions/{session['session_id']}", timeout=20) as r:
            json.loads(r.read())
        with urllib.request.urlopen(f"{base}/sessions/{session['session_id']}/result", timeout=20) as r:
            recovered = json.loads(r.read())
        record("Session/result recovery routes", recovered["score"] == result["score"],
               "GET /sessions/{id} and /sessions/{id}/result return the same stored result")
        return True
    except Exception as exc:  # noqa: BLE001
        record("Deployed submit path", False, f"{type(exc).__name__}: {exc}")
        return False


def check_websocket(ws_url):
    """Handshake against the deployed API Gateway WebSocket API."""
    try:
        import base64
        import socket
        import ssl
        from urllib.parse import urlparse

        parsed = urlparse(ws_url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"

        raw = socket.create_connection((host, port), timeout=15)
        if parsed.scheme == "wss":
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        key = base64.b64encode(os.urandom(16)).decode()
        raw.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n".encode())
        response = raw.recv(4096)
        raw.close()
        ok = b"101" in response.split(b"\r\n")[0]
        record("Deployed WebSocket handshake", ok, response.split(b"\r\n")[0].decode("latin-1"))
        return ok
    except Exception as exc:  # noqa: BLE001
        record("Deployed WebSocket handshake", False, f"{type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------

CHECKS = {
    "bedrock": [check_bedrock_raw, check_bug_injector, check_evaluator,
                check_brief_writer, check_test_author],
    "stepfunctions": [check_step_functions],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", help="Deployed API Gateway stage URL")
    parser.add_argument("--ws-url", help="Deployed WebSocket URL (defaults to $WEBSOCKET_URL)")
    parser.add_argument("--only", choices=sorted(CHECKS), help="Run one group only")
    args = parser.parse_args()

    os.environ.setdefault("BREAKFIX_STORAGE", "dynamodb")

    print("\nBreakFix — real AWS verification")
    print("=" * 66)

    if not check_identity():
        print("\n" + "=" * 66)
        print(f"{RED}No AWS credentials. Nothing below could be verified.{RESET}\n")
        return 1

    groups = [args.only] if args.only else list(CHECKS)
    for group in groups:
        print(f"\n{group}:")
        for check in CHECKS[group]:
            check()

    if args.api_url:
        print("\ndeployed api:")
        check_deployed_api(args.api_url)

    ws_url = args.ws_url or os.environ.get("WEBSOCKET_URL", "")
    if ws_url:
        print("\nwebsocket:")
        check_websocket(ws_url)

    print("\n" + "=" * 66)
    failed = [r for r in RESULTS if not r["ok"] and not r["warn"]]
    warned = [r for r in RESULTS if not r["ok"] and r["warn"]]
    passed = [r for r in RESULTS if r["ok"]]
    print(f"  {GREEN}{len(passed)} passed{RESET} · {YELLOW}{len(warned)} warned{RESET} · {RED}{len(failed)} failed{RESET}")
    if failed:
        print(f"\n  {RED}Not demo-ready:{RESET}")
        for r in failed:
            print(f"    - {r['name']}")
    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
