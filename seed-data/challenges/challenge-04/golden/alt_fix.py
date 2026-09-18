import re
import unicodedata


def slugify(value, allow_unicode=False):
    """Correct, but rebuilds the slug by splitting rather than substituting."""
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value.lower())
    parts = [part for part in re.split(r"[-\s]+", value) if part]
    return "-".join(parts).strip("-_")
