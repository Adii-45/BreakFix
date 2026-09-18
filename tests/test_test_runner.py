"""Test Runner unit + sandbox-isolation tests (PRD 12.1, 12.2).

The point of these is that correctness is decided here, without any AI call:
known-good code must pass and known-bad code must fail, and hostile code must be
reported as a failing result rather than crashing the Lambda.
"""
import pytest

from test_runner import runner

CASES = [
    {"name": "sums a list", "input": [[1, 2, 3]], "expected_output": 6},
    {"name": "handles empty", "input": [[]], "expected_output": 0},
]


def run(code, cases=CASES, entry="total"):
    return runner.run_tests(code, entry, cases)


def test_known_good_code_passes_every_test():
    result = run("def total(xs):\n    return sum(xs)\n")
    assert result["tests_passed"] == result["tests_total"] == 2
    assert result["runner_status"] == "ok"


def test_known_bad_code_fails_with_a_useful_message():
    result = run("def total(xs):\n    return sum(xs) + 1\n")
    assert result["tests_passed"] == 0
    assert "expected 6, got 7" in result["per_test"][0]["error"]


def test_partially_correct_code_reports_a_partial_pass():
    result = run("def total(xs):\n    return 6 if xs else 1\n")
    assert result["tests_passed"] == 1
    assert result["tests_total"] == 2


def test_syntax_error_is_a_failing_result_not_an_exception():
    result = run("def total(xs)\n    return 1\n")
    assert result["tests_passed"] == 0
    assert result["runner_status"] == "load_error"
    assert "SyntaxError" in result["load_error"]


def test_missing_entry_point_is_reported():
    result = run("def something_else(xs):\n    return 0\n")
    assert result["runner_status"] == "load_error"
    assert "not defined" in result["load_error"]


def test_raised_exception_fails_the_test_without_crashing():
    result = run("def total(xs):\n    raise RuntimeError('boom')\n")
    assert result["tests_passed"] == 0
    assert "RuntimeError" in result["per_test"][0]["error"]


def test_empty_submission_is_rejected_as_a_failing_result():
    result = run("   ")
    assert result["tests_passed"] == 0
    assert "empty" in result["load_error"].lower()


def test_oversized_submission_is_rejected():
    result = run("x = '" + "a" * 30000 + "'\ndef total(xs):\n    return sum(xs)\n")
    assert result["runner_status"] == "load_error"
    assert "limit" in result["load_error"]


# --- sandbox isolation (PRD 12.2) -------------------------------------------

def test_infinite_loop_hits_the_timeout_rather_than_hanging():
    result = run("def total(xs):\n    while True:\n        pass\n")
    assert result["tests_passed"] == 0
    assert result["runner_status"] in ("ok", "timeout")
    assert all(not t["passed"] for t in result["per_test"])
    assert result["duration_ms"] < 10000


def test_module_level_infinite_loop_is_terminated():
    # Caught by the per-test alarm around the exec (load_error) or, failing
    # that, by the parent's wall clock (timeout). Either is fine; what matters
    # is that it terminates and scores zero.
    result = run("while True:\n    pass\n\ndef total(xs):\n    return 0\n")
    assert result["runner_status"] in ("load_error", "timeout")
    assert result["tests_passed"] == 0
    assert result["duration_ms"] < 10000


@pytest.mark.parametrize(
    "code",
    [
        "import socket\ndef total(xs):\n    return socket.socket()\n",
        "import urllib.request\ndef total(xs):\n    return urllib.request.urlopen('http://example.com')\n",
    ],
)
def test_network_access_is_blocked(code):
    result = run(code)
    assert result["tests_passed"] == 0
    blob = (result.get("load_error") or "") + " ".join(t["error"] or "" for t in result["per_test"])
    assert "sandbox" in blob.lower()


def test_reading_outside_the_scratch_directory_is_blocked():
    result = run("def total(xs):\n    return open('/etc/hosts').read()\n")
    assert result["tests_passed"] == 0
    assert "sandbox" in result["per_test"][0]["error"].lower()


def test_writing_outside_the_scratch_directory_is_blocked(tmp_path):
    target = tmp_path / "escaped.txt"
    result = run(f"def total(xs):\n    open({str(target)!r}, 'w').write('x')\n    return sum(xs)\n")
    assert result["tests_passed"] == 0
    assert not target.exists()


def test_writing_inside_the_scratch_directory_is_allowed():
    result = run("def total(xs):\n    open('scratch.txt', 'w').write('ok')\n    return sum(xs)\n")
    assert result["tests_passed"] == 2


@pytest.mark.parametrize(
    "code",
    [
        "import subprocess\ndef total(xs):\n    return subprocess.run(['ls'])\n",
        "import os\ndef total(xs):\n    return os.system('ls')\n",
        "import os\ndef total(xs):\n    os.fork()\n    return 0\n",
    ],
)
def test_process_creation_is_blocked(code):
    result = run(code)
    assert result["tests_passed"] == 0


def test_student_stdout_cannot_corrupt_the_result_protocol():
    noisy = 'def total(xs):\n    print("{\\"tests\\": []}" * 50)\n    return sum(xs)\n'
    result = run(noisy)
    assert result["tests_passed"] == 2


def test_mutating_the_input_does_not_leak_between_tests():
    cases = [
        {"name": "first", "input": [[1, 2, 3]], "expected_output": 6},
        {"name": "second", "input": [[1, 2, 3]], "expected_output": 6},
    ]
    result = run("def total(xs):\n    xs.clear()\n    return 6\n", cases)
    assert result["tests_passed"] == 2
