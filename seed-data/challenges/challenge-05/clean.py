import re
import unicodedata

_FILENAME_STRIP_RE = re.compile(r"[^A-Za-z0-9_.-]")
_PATH_SEPARATORS = ("/", "\\")


def secure_filename(filename):
    """Return a filename that is safe to store on any filesystem.

    Path separators are neutralised so a crafted name can never escape the
    upload directory, accents are folded to ASCII, runs of whitespace become a
    single underscore, and leading dots/underscores are stripped.
    """
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    for separator in _PATH_SEPARATORS:
        filename = filename.replace(separator, " ")

    filename = "_".join(filename.split())
    return _FILENAME_STRIP_RE.sub("", filename).strip("._")
