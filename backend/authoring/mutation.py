"""Deterministic bug injection — the fallback when Bedrock is unavailable.

This is classic mutation testing, not a model: it walks the AST, applies one
mechanical change at a time (flip a comparison, shift a constant, invert a
boolean operator), and keeps the first mutation that makes at least one hidden
test fail while leaving at least one passing.

It is always labelled `mutation-fallback` in the stored record so nobody can
mistake it for Bug Injector Agent output. The agent remains the primary path.
"""
import ast
import copy
from typing import Any, Callable, Dict, List, Optional, Tuple

# Boundary slips (`<` -> `<=`) are the subtlest and are tried first; direction
# flips (`<` -> `>`) are the fallback for functions where a boundary slip changes
# nothing observable.
COMPARISON_FLIPS = {
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
}
COMPARISON_REVERSALS = {
    ast.Lt: ast.Gt, ast.Gt: ast.Lt,
    ast.LtE: ast.GtE, ast.GtE: ast.LtE,
}
ARITHMETIC_SWAPS = {
    ast.Add: ast.Sub, ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv, ast.FloorDiv: ast.Mult,
}
ARITH_LABEL = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.FloorDiv: "//"}
FLIP_LABEL = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
}


class _Mutator(ast.NodeTransformer):
    """Applies exactly one mutation, identified by ordinal position."""

    def __init__(self, target_index: int, mode: str = "flip"):
        self.target_index = target_index
        self.mode = mode
        self.seen = 0
        self.description = ""
        self.category = ""

    def _hit(self) -> bool:
        hit = self.seen == self.target_index
        self.seen += 1
        return hit

    def visit_Compare(self, node):  # noqa: N802
        self.generic_visit(node)
        table = COMPARISON_REVERSALS if self.mode == "reverse" else COMPARISON_FLIPS
        if len(node.ops) == 1 and type(node.ops[0]) in table:
            if self._hit():
                old = type(node.ops[0])
                new = table[old]
                node.ops[0] = new()
                self.description = f"A comparison was changed from `{FLIP_LABEL[old]}` to `{FLIP_LABEL[new]}`."
                self.category = "wrong-operator" if self.mode == "reverse" else "incorrect-boundary"
        return node

    def visit_BinOp(self, node):  # noqa: N802
        self.generic_visit(node)
        if type(node.op) in ARITHMETIC_SWAPS:
            if self._hit():
                old = type(node.op)
                new = ARITHMETIC_SWAPS[old]
                node.op = new()
                self.description = (
                    f"An arithmetic operator was changed from `{ARITH_LABEL[old]}` to `{ARITH_LABEL[new]}`."
                )
                self.category = "wrong-operator"
        return node

    def visit_Constant(self, node):  # noqa: N802
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            if self._hit():
                node.value = node.value + 1
                self.description = f"An integer constant was shifted from {node.value - 1} to {node.value}."
                self.category = "off-by-one"
        return node

    def visit_BoolOp(self, node):  # noqa: N802
        self.generic_visit(node)
        if self._hit():
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            self.description = "A boolean operator was inverted between `and` and `or`."
            self.category = "inverted-logic"
        return node


def _count_targets(tree: ast.Module, mode: str) -> int:
    counter = _Mutator(-1, mode)
    counter.visit(copy.deepcopy(tree))
    return counter.seen


def generate_candidates(clean_code: str, limit: int = 60) -> List[Dict[str, str]]:
    """Every single-point mutation of the function, as source.

    Subtle mutations (boundary slips, arithmetic swaps) come first; comparison
    direction reversals are appended as a fallback for functions where nothing
    subtler changes observable behaviour.
    """
    tree = ast.parse(clean_code)
    baseline = ast.unparse(ast.parse(clean_code)).strip()
    candidates: List[Dict[str, str]] = []
    seen_sources = set()

    for mode in ("flip", "reverse"):
        total = _count_targets(tree, mode)
        for index in range(min(total, limit)):
            mutator = _Mutator(index, mode)
            mutated = mutator.visit(copy.deepcopy(tree))
            if not mutator.description:
                continue
            ast.fix_missing_locations(mutated)
            try:
                source = ast.unparse(mutated)
            except Exception:  # noqa: BLE001
                continue
            if source.strip() == baseline or source in seen_sources:
                continue
            seen_sources.add(source)
            candidates.append({
                "buggy_code": source + "\n",
                "diff_summary": mutator.description,
                "bug_category": mutator.category,
            })
    return candidates


def inject(
    clean_code: str,
    function_name: str,
    test_cases: List[Dict],
    run_tests: Callable[[str, str, List[Dict]], Dict[str, Any]],
) -> Optional[Dict[str, str]]:
    """Pick the first mutation that breaks some -- but not all -- hidden tests.

    Preferring a partial break is deliberate: a mutation that fails every test is
    usually a crash, which is a worse puzzle than one that only misbehaves on an
    edge case.
    """
    partial: Optional[Tuple[Dict[str, str], int]] = None
    total_break: Optional[Dict[str, str]] = None

    for candidate in generate_candidates(clean_code):
        result = run_tests(candidate["buggy_code"], function_name, test_cases)
        passed, total = result["tests_passed"], result["tests_total"]
        if passed == total:
            continue                                  # too weak, discard
        if result.get("runner_status") not in ("ok", "load_error") and passed == 0:
            continue                                  # crashed outright
        if passed > 0:
            if partial is None or passed > partial[1]:
                partial = (candidate, passed)
        elif total_break is None:
            total_break = candidate

    chosen = partial[0] if partial else total_break
    if chosen is None:
        return None
    return {
        **chosen,
        "why_its_a_bug": (
            f"{chosen['diff_summary']} The function still parses and runs, but at least one "
            "hidden test now observes different behaviour from the reference implementation."
        ),
        "hint_level_description": "The change is a single token. Compare the edge cases against what the docstring promises.",
        "generated_by": "mutation-fallback",
    }
