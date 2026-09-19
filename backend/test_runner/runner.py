"""Test Runner (PRD Section 8.0) -- the parent half.

This is the component that decides correctness. It is deterministic execution,
not a model call: `run_tests()` returns tests_passed / tests_total and a per-test
pass/fail list, and NOTHING downstream is allowed to overrule it.

The parent's jobs are (a) hand the child a scratch directory it can't escape,
(b) enforce the wall-clock kill that survives anything the child does to itself,
and (c) turn a crashed / killed / silent child into a *failing test result*
rather than a 500 (PRD Section 9, F3).
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from common import config

_CHILD_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "child_runner.py")

# Lambda only guarantees /tmp is writable. On Windows, use system tempdir.
_SCRATCH_ROOT = os.environ.get("BREAKFIX_SCRATCH_ROOT", tempfile.gettempdir() if os.name == "nt" else "/tmp")


def _blank_results(test_cases: List[Dict], error: str, status: str) -> Dict[str, Any]:
    return {
        "tests_passed": 0,
        "tests_total": len(test_cases),
        "per_test": [
            {
                "index": i,
                "name": c.get("name", f"test_{i + 1}"),
                "passed": False,
                "error": error,
                "kind": "timeout" if status == "timeout" else "error",
            }
            for i, c in enumerate(test_cases)
        ],
        "runner_status": status,
        "load_error": error,
        "stderr": "",
        "duration_ms": 0,
    }


def run_tests(
    code: str,
    entry_point: str,
    test_cases: List[Dict],
    wall_timeout: Optional[float] = None,
    per_test_timeout: Optional[float] = None,
    memory_mb: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute `code` against `test_cases` in a sandboxed child process.

    Never raises for bad student input -- a submission that is empty, oversized,
    syntactically broken, malicious or infinite-looping comes back as a normal
    all-tests-failed result with an explanation.
    """
    wall_timeout = wall_timeout if wall_timeout is not None else config.SANDBOX_WALL_TIMEOUT_SECONDS
    per_test_timeout = per_test_timeout if per_test_timeout is not None else config.SANDBOX_PER_TEST_TIMEOUT_SECONDS
    memory_mb = memory_mb if memory_mb is not None else config.SANDBOX_MEMORY_LIMIT_MB

    if not test_cases:
        return _blank_results([], "This challenge has no test cases configured.", "misconfigured")
    if not code or not code.strip():
        return _blank_results(test_cases, "Submission was empty.", "load_error")
    if len(code.encode("utf-8")) > config.SANDBOX_MAX_CODE_BYTES:
        return _blank_results(
            test_cases,
            f"Submission exceeds the {config.SANDBOX_MAX_CODE_BYTES} byte limit.",
            "load_error",
        )

    scratch_dir = tempfile.mkdtemp(prefix="breakfix-", dir=_SCRATCH_ROOT)
    started = time.time()
    try:
        payload_path = os.path.join(scratch_dir, "payload.json")
        with open(payload_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "code": code,
                    "entry_point": entry_point,
                    "test_cases": test_cases,
                    "scratch_dir": scratch_dir,
                    "per_test_timeout": per_test_timeout,
                    "memory_mb": memory_mb,
                    "cpu_seconds": wall_timeout,
                },
                fh,
            )

        # Isolated interpreter (-I): ignores PYTHONPATH, PYTHONHOME and the user
        # site directory, so the student cannot pre-load a shim. -B: no .pyc writes.
        argv = [sys.executable, "-I", "-B", _CHILD_SCRIPT, payload_path]
        env = {
            # Locked down on POSIX (which is what Lambda runs). Windows cannot
            # start the interpreter without the inherited PATH, and that path is
            # local dev only -- it never applies in production.
            "PATH": os.environ.get("PATH", "") if os.name == "nt" else "/usr/bin:/bin",
            "HOME": scratch_dir,
            "TMPDIR": scratch_dir,
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }

        proc = subprocess.Popen(
            argv,
            cwd=scratch_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True if os.name != "nt" else False,  # own process group on POSIX
        )
        try:
            stdout, stderr = proc.communicate(timeout=wall_timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            stdout, stderr = proc.communicate()
            timed_out = True

        duration_ms = int((time.time() - started) * 1000)
        stderr_text = (stderr or b"").decode("utf-8", "replace")[-2000:]

        if timed_out:
            out = _blank_results(
                test_cases,
                f"Execution exceeded the {wall_timeout}s sandbox limit and was terminated.",
                "timeout",
            )
            out["duration_ms"] = duration_ms
            out["stderr"] = stderr_text
            return out

        raw = (stdout or b"")[: config.SANDBOX_MAX_OUTPUT_BYTES].decode("utf-8", "replace").strip()
        if not raw:
            reason = "Submitted code crashed the sandbox process before any result was produced."
            if proc.returncode and proc.returncode < 0:
                reason = f"Sandbox process was killed by signal {-proc.returncode} (likely memory or CPU limit)."
            out = _blank_results(test_cases, reason, "crashed")
            out["duration_ms"] = duration_ms
            out["stderr"] = stderr_text
            return out

        try:
            child = json.loads(raw)
        except json.JSONDecodeError:
            out = _blank_results(test_cases, "Sandbox produced unreadable output.", "crashed")
            out["duration_ms"] = duration_ms
            out["stderr"] = (stderr_text + "\n" + raw[-500:]).strip()
            return out

        per_test = child.get("tests", [])
        return {
            "tests_passed": sum(1 for t in per_test if t.get("passed")),
            "tests_total": len(test_cases),
            "per_test": per_test,
            "runner_status": "load_error" if child.get("load_error") else "ok",
            "load_error": child.get("load_error"),
            "stderr": stderr_text,
            "duration_ms": duration_ms,
            "sandbox": child.get("sandbox", {}),
        }
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _kill_group(proc: "subprocess.Popen") -> None:
    if hasattr(os, "killpg") and hasattr(os, "getpgid") and hasattr(signal, "SIGKILL"):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except Exception:  # pragma: no cover
        pass
