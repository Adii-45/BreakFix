"""Sandboxed child process that actually executes untrusted student code.

This file is never imported by the Lambda handler -- it is spawned as a separate
`python3 child_runner.py <payload.json>` process so that a crash, an OOM, a
SIGKILL or a runaway loop takes down only the child. PRD Section 8.0 requires,
and this implements:

  * hard execution timeout      -- SIGALRM per test + RLIMIT_CPU + parent wall clock
  * memory limit                -- RLIMIT_AS
  * no network access           -- audit hook on socket.* + neutered socket module
  * no filesystem access beyond -- audit hook on open/os.* restricted to the
    a scratch temp directory       scratch dir (plus read-only stdlib, which the
                                   import machinery needs)
  * no process creation         -- audit hook on subprocess/os.exec/os.fork/RLIMIT_NPROC

Defence in depth, not a claim of perfect isolation: this is a CPython audit-hook
sandbox inside an already-disposable Lambda execution environment. See
README "Sandbox threat model" for exactly what it does and does not stop.
"""
import copy
import json
import math
import os
import signal
import sys


# ---------------------------------------------------------------------------
# Everything in this first section runs BEFORE any untrusted code is compiled.
# ---------------------------------------------------------------------------

BLOCKED_MODULES = {
    "socket", "ssl", "subprocess", "multiprocessing", "ctypes", "http",
    "urllib", "urllib3", "requests", "ftplib", "telnetlib", "smtplib",
    "shutil", "pty", "tty", "webbrowser", "pickle", "marshal", "boto3",
    "botocore", "importlib.util",
}

BLOCKED_AUDIT_EVENTS = (
    "socket.socket", "socket.bind", "socket.connect", "socket.connect_ex",
    "socket.getaddrinfo", "socket.gethostbyname", "socket.sethostname",
    "subprocess.Popen", "os.system", "os.exec", "os.fork", "os.forkpty",
    "os.posix_spawn", "os.spawn", "os.kill", "os.killpg", "os.putenv",
    "os.unsetenv", "os.setuid", "os.setgid", "ctypes.dlopen", "ctypes.dlsym",
    "ctypes.call_function", "ctypes.set_exception", "pty.spawn",
    "resource.setrlimit", "sys.settrace", "sys._getframe.f_back",
    "shutil.copyfile", "shutil.move", "shutil.rmtree", "urllib.Request",
    "http.client.connect", "ftplib.connect", "smtplib.connect", "webbrowser.open",
)

# Path-bearing os.* events -- the path argument must live inside the scratch dir.
PATH_AUDIT_EVENTS = {
    "os.mkdir": 0, "os.rmdir": 0, "os.remove": 0, "os.rename": 0,
    "os.link": 0, "os.symlink": 0, "os.chmod": 0, "os.chown": 0,
    "os.truncate": 0, "os.listdir": 0, "os.scandir": 0, "os.chdir": 0,
    "os.stat": 0, "os.utime": 0,
}


def _read_payload(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _stdlib_roots():
    """Read-only paths the import machinery legitimately needs."""
    import sysconfig

    roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        try:
            p = sysconfig.get_path(key)
        except Exception:
            p = None
        if p:
            roots.add(p)
    for p in sys.path:
        if p and os.path.isdir(p) and ("site-packages" in p or "lib" in p.split(os.sep)):
            roots.add(p)
    return tuple(os.path.realpath(r) for r in roots if r)


class SandboxViolation(PermissionError):
    """Raised inside the student's process when it tries to escape the sandbox."""


def _install_audit_hook(scratch_dir, stdlib_roots):
    scratch_real = os.path.realpath(scratch_dir)

    def _inside(path, roots):
        try:
            real = os.path.realpath(os.fspath(path))
        except Exception:
            return False
        if os.name == "nt":
            real_l = real.lower()
            return any(real_l == r.lower() or real_l.startswith(r.lower() + os.sep) for r in roots)
        return any(real == r or real.startswith(r + os.sep) for r in roots)

    def hook(event, args):
        if event in BLOCKED_AUDIT_EVENTS:
            raise SandboxViolation(f"blocked by sandbox: {event}")

        if event == "import":
            module = args[0] if args else ""
            root = str(module).split(".")[0]
            if root in BLOCKED_MODULES or str(module) in BLOCKED_MODULES:
                raise SandboxViolation(f"blocked by sandbox: import {module}")
            return

        if event == "open":
            path, mode = args[0], (args[1] or "r")
            writing = any(c in str(mode) for c in ("w", "a", "x", "+"))
            if _inside(path, (scratch_real,)):
                return
            if not writing and _inside(path, stdlib_roots):
                return  # stdlib reads only -- required for lazy imports
            raise SandboxViolation(f"blocked by sandbox: filesystem access to {path!r}")

        idx = PATH_AUDIT_EVENTS.get(event)
        if idx is not None and len(args) > idx:
            target = args[idx]
            if isinstance(target, int):
                return  # already-open fd, covered by the open() check above
            if _inside(target, (scratch_real,)) or _inside(target, stdlib_roots):
                return
            raise SandboxViolation(f"blocked by sandbox: {event} on {target!r}")

    sys.addaudithook(hook)


def _apply_rlimits(memory_mb, cpu_seconds):
    """Best-effort resource caps. Some limits are unsupported on some kernels
    (notably RLIMIT_AS on macOS); a failure to set one is logged in the result
    rather than aborting -- the parent's wall-clock kill is the hard backstop."""
    applied, skipped = [], []
    try:
        import resource
    except ImportError:
        return applied, ["resource module unavailable"]

    def setl(name, soft, hard=None):
        try:
            limit = getattr(resource, name)
        except AttributeError:
            skipped.append(name)
            return
        try:
            resource.setrlimit(limit, (soft, hard if hard is not None else soft))
            applied.append(name)
        except (ValueError, OSError) as exc:
            skipped.append(f"{name} ({exc.__class__.__name__})")

    # Address-space cap first; fall back to the data segment where RLIMIT_AS is
    # not lowerable (macOS dev machines). On Lambda's Amazon Linux RLIMIT_AS
    # applies, and the Lambda function's own memory ceiling is the final backstop.
    before = len(applied)
    setl("RLIMIT_AS", memory_mb * 1024 * 1024)
    if len(applied) == before:
        setl("RLIMIT_DATA", memory_mb * 1024 * 1024)
    setl("RLIMIT_CPU", int(math.ceil(cpu_seconds)), int(math.ceil(cpu_seconds)) + 1)
    setl("RLIMIT_NPROC", 0)
    setl("RLIMIT_FSIZE", 5 * 1024 * 1024)
    setl("RLIMIT_CORE", 0)
    return applied, skipped


def _neuter_network():
    """Remove the easy paths to the network before the audit hook even fires."""
    try:
        import socket as _socket

        def _blocked(*_a, **_kw):
            raise SandboxViolation("blocked by sandbox: network access is disabled")

        for attr in ("socket", "create_connection", "socketpair", "getaddrinfo", "gethostbyname"):
            if hasattr(_socket, attr):
                setattr(_socket, attr, _blocked)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test execution
# ---------------------------------------------------------------------------

class TestTimeout(Exception):
    pass


def _alarm(_signum, _frame):
    raise TestTimeout("test exceeded its time limit")


def _call_args(raw_input):
    """Test-case input forms, in order of precedence:
       {"args": [...], "kwargs": {...}}  -- explicit
       [a, b, c]                          -- positional args
       anything else                      -- a single positional arg
    """
    if isinstance(raw_input, dict) and ("args" in raw_input or "kwargs" in raw_input):
        return list(raw_input.get("args", [])), dict(raw_input.get("kwargs", {}))
    if isinstance(raw_input, list):
        return list(raw_input), {}
    return [raw_input], {}


def _outputs_match(actual, expected):
    if isinstance(actual, bool) != isinstance(expected, bool):
        return False
    if isinstance(actual, float) or isinstance(expected, float):
        try:
            return math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    if isinstance(actual, tuple):
        actual = list(actual)
    if isinstance(expected, tuple):
        expected = list(expected)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(_outputs_match(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _truncate(value, limit=300):
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _set_timer(seconds: float) -> None:
    if hasattr(signal, "setitimer") and hasattr(signal, "ITIMER_REAL"):
        signal.setitimer(signal.ITIMER_REAL, seconds)


def _cancel_timer() -> None:
    if hasattr(signal, "setitimer") and hasattr(signal, "ITIMER_REAL"):
        signal.setitimer(signal.ITIMER_REAL, 0)


def main():
    payload_path = sys.argv[1]
    payload = _read_payload(payload_path)

    code = payload["code"]
    entry_point = payload["entry_point"]
    test_cases = payload["test_cases"]
    scratch_dir = payload["scratch_dir"]
    per_test_timeout = float(payload.get("per_test_timeout", 2.0))
    memory_mb = int(payload.get("memory_mb", 256))
    cpu_seconds = float(payload.get("cpu_seconds", 5.0))

    os.chdir(scratch_dir)
    stdlib_roots = _stdlib_roots()

    # Reserve a channel for the result BEFORE fd 1 is pointed at /dev/null, so
    # that anything the student prints cannot corrupt our JSON protocol.
    result_fd = os.dup(1)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull_fd, 1)
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    limits_applied, limits_skipped = _apply_rlimits(memory_mb, cpu_seconds)
    _neuter_network()
    _install_audit_hook(scratch_dir, stdlib_roots)

    result = {
        "tests": [],
        "load_error": None,
        "sandbox": {"limits_applied": limits_applied, "limits_skipped": limits_skipped},
    }

    namespace = {"__name__": "__breakfix_submission__", "__builtins__": __builtins__}
    try:
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _alarm)
        _set_timer(per_test_timeout)
        compiled = compile(code, "<submission>", "exec")
        exec(compiled, namespace)  # noqa: S102 -- this is the whole point of the runner
        _cancel_timer()
    except SyntaxError as exc:
        result["load_error"] = f"SyntaxError: {exc.msg} (line {exc.lineno})"
    except TestTimeout:
        result["load_error"] = "Module-level code timed out before any test could run."
    except SandboxViolation as exc:
        result["load_error"] = str(exc)
    except BaseException as exc:  # noqa: BLE001 - report, never crash
        result["load_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _cancel_timer()

    fn = namespace.get(entry_point)
    if result["load_error"] is None and not callable(fn):
        result["load_error"] = f"Function '{entry_point}' is not defined in the submission."

    for index, case in enumerate(test_cases):
        record = {
            "index": index,
            "name": case.get("name", f"test_{index + 1}"),
            "passed": False,
            "error": None,
            # `kind` separates "your logic is wrong" (mismatch) from "this never
            # ran" (timeout/blocked/error). The distinction drives the scoring
            # band: a broken submission is not a near-miss.
            "kind": "error",
        }
        if result["load_error"]:
            record["error"] = result["load_error"]
            record["kind"] = "timeout" if "timed out" in result["load_error"] else "error"
            result["tests"].append(record)
            continue

        args, kwargs = _call_args(copy.deepcopy(case.get("input")))
        expected = copy.deepcopy(case.get("expected_output"))
        try:
            _set_timer(per_test_timeout)
            actual = fn(*args, **kwargs)
            _cancel_timer()
            record["passed"] = _outputs_match(actual, expected)
            record["kind"] = "pass" if record["passed"] else "mismatch"
            if not record["passed"]:
                record["error"] = f"expected {_truncate(expected)}, got {_truncate(actual)}"
        except TestTimeout:
            record["error"] = f"timed out after {per_test_timeout}s"
            record["kind"] = "timeout"
        except SandboxViolation as exc:
            record["error"] = str(exc)
            record["kind"] = "blocked"
        except RecursionError:
            record["error"] = "RecursionError: maximum recursion depth exceeded"
            record["kind"] = "error"
        except MemoryError:
            record["error"] = "MemoryError: exceeded the sandbox memory limit"
            record["kind"] = "error"
        except BaseException as exc:  # noqa: BLE001
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["kind"] = "error"
        finally:
            _cancel_timer()
        result["tests"].append(record)


    os.write(result_fd, json.dumps(result).encode("utf-8"))
    os.close(result_fd)
    # os._exit skips atexit/GC so nothing the student registered can run.
    os._exit(0)


if __name__ == "__main__":
    main()
