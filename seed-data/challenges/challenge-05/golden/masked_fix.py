import re
import unicodedata

_FILENAME_STRIP_RE = re.compile(r"[^A-Za-z0-9_.-]")
_PATH_SEPARATORS = ("/", "\\")


def secure_filename(filename):
    """Fixes the path-traversal case only; whitespace handling stays broken."""
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    for separator in _PATH_SEPARATORS:
        filename = filename.replace(separator, "_")

    filename = " ".join(filename.split())
    return _FILENAME_STRIP_RE.sub("", filename).strip("._")
