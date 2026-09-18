import re
import unicodedata


def slugify(value, allow_unicode=False):
    """Convert a string to a URL-safe slug.

    Strips accents, removes anything that is not a word character, whitespace or
    a hyphen, lowercases, and collapses runs of whitespace and hyphens down to a
    single hyphen.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]", "-", value).strip("-_")
