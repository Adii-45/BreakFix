"""Fetch a real function out of a real GitHub repository (Part 3, step 1)."""
import ast
import re
import ssl
import urllib.request
from typing import Dict, List, Optional, Tuple

BLOB_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$")
RAW_RE = re.compile(r"^https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$")
MAX_BYTES = 400_000


class FetchError(RuntimeError):
    pass


def parse_url(url: str) -> Dict[str, str]:
    """Accepts a github.com /blob/ link or a raw.githubusercontent.com link."""
    url = (url or "").strip()
    for pattern in (BLOB_RE, RAW_RE):
        match = pattern.match(url)
        if match:
            owner, repo, ref, path = match.groups()
            path = path.split("#")[0].split("?")[0]
            return {
                "owner": owner,
                "repo": repo,
                "ref": ref,
                "path": path,
                "repo_name": f"{owner}/{repo}",
                "repo_url": f"https://github.com/{owner}/{repo}",
                "raw_url": f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}",
                "blob_url": f"https://github.com/{owner}/{repo}/blob/{ref}/{path}",
            }
    raise FetchError(
        "Expected a GitHub file URL such as "
        "https://github.com/owner/repo/blob/main/path/to/file.py"
    )


def _ssl_context() -> ssl.SSLContext:
    """Use certifi's bundle when present; Lambda images often lack a system one."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def fetch_raw(raw_url: str, timeout: float = 15.0) -> str:
    request = urllib.request.Request(raw_url, headers={"User-Agent": "breakfix-authoring"})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
            body = response.read(MAX_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Could not fetch {raw_url}: {type(exc).__name__}: {exc}") from exc
    if len(body) > MAX_BYTES:
        raise FetchError(f"File exceeds the {MAX_BYTES} byte limit.")
    return body.decode("utf-8", "replace")


def _relative_dependencies(tree: ast.Module, func: ast.FunctionDef) -> List[str]:
    """Intra-package imports the function needs.

    These are the single biggest reason a real library function cannot be lifted
    out and run standalone: `from .i18n import _pgettext` has no meaning outside
    its package. We detect them up front and say so, rather than letting the
    sandbox fail later with a bare ImportError.
    """
    used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(func)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}

    blockers = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.level or 0) > 0:
            names = [a.asname or a.name for a in node.names]
            if any(n in used for n in names):
                blockers.append(ast.unparse(node))
    return blockers


def _needed_imports(tree: ast.Module, func: ast.FunctionDef, extra_source: str = "") -> List[str]:
    """Module-level imports the function (and its constants) actually reference.

    A function lifted out of its module usually needs a couple of imports to run
    standalone. Anything nothing references is left behind, so the student sees
    the function and nothing else.
    """
    used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(func)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}

    if extra_source.strip():
        try:
            extra = ast.parse(extra_source)
        except SyntaxError:
            extra = None
        if extra is not None:
            used |= {n.id for n in ast.walk(extra) if isinstance(n, ast.Name)}
            used |= {n.value.id for n in ast.walk(extra)
                     if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}

    lines: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [a.asname or a.name.split(".")[0] for a in node.names]
            if any(n in used for n in names):
                lines.append(ast.unparse(node))
        elif isinstance(node, ast.ImportFrom):
            names = [a.asname or a.name for a in node.names]
            if any(n in used for n in names):
                lines.append(ast.unparse(node))
    return lines


def _module_constants(tree: ast.Module, func: ast.FunctionDef) -> List[str]:
    """Module-level constant assignments the function depends on."""
    used = {n.id for n in ast.walk(func) if isinstance(n, ast.Name)}
    lines: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(t in used for t in targets):
                lines.append(ast.unparse(node))
    return lines


def extract_function(source: str, function_name: str) -> Tuple[str, Dict]:
    """Return standalone, parseable source for `function_name`."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise FetchError(f"The fetched file is not valid Python: {exc}") from exc

    target: Optional[ast.FunctionDef] = None
    available: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            available.append(node.name)
            if node.name == function_name and isinstance(node, ast.FunctionDef):
                target = node
    if target is None:
        raise FetchError(
            f"No plain function named '{function_name}' in that file. Found: {', '.join(sorted(set(available))[:20]) or 'none'}"
        )

    body = ast.get_source_segment(source, target)
    if not body:
        raise FetchError(f"Could not extract the source of '{function_name}'.")

    blockers = _relative_dependencies(tree, target)
    if blockers:
        raise FetchError(
            f"'{function_name}' depends on intra-package imports that cannot run standalone: "
            + "; ".join(blockers)
            + ". Pick a self-contained function, or paste an adapted version of the source instead."
        )

    # Constants are resolved first, then imports -- a constant such as
    # `PATTERN = re.compile(...)` drags in `import re` even though the function
    # body never names `re` directly. Without this closure the extracted code
    # references a module that was left behind.
    constants = _module_constants(tree, target)
    preamble = _needed_imports(tree, target, extra_source="\n".join(constants)) + constants
    standalone = ("\n".join(preamble) + "\n\n\n" + body).lstrip("\n") if preamble else body
    if not standalone.endswith("\n"):
        standalone += "\n"

    ast.parse(standalone)  # must stand on its own
    return standalone, {
        "arg_names": [a.arg for a in target.args.args],
        "preamble_lines": len(preamble),
        "docstring": ast.get_docstring(target) or "",
    }
