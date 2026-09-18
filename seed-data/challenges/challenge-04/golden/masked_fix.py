import re
import unicodedata


def slugify(value, allow_unicode=False):
    """Normalises whitespace up front instead of restoring the quantifier."""
    value = str(value)
    value = " ".join(value.split())
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]", "-", value).strip("-_")
