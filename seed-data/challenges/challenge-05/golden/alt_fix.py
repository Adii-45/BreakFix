import re
import unicodedata

_FILENAME_STRIP_RE = re.compile(r"[^A-Za-z0-9_.-]")
_PATH_SEPARATORS = ("/", "\\")


def secure_filename(filename):
    """Correct, but collapses whitespace with a regex instead of split/join."""
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    for separator in _PATH_SEPARATORS:
        filename = filename.replace(separator, " ")

    filename = re.sub(r"\s+", "_", filename.strip())
    return _FILENAME_STRIP_RE.sub("", filename).strip("._")
