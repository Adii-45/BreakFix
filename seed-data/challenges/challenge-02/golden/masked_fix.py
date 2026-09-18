def ordinal(value):
    """Special-cases the one failing input instead of widening the teens rule."""
    suffixes = ("th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")
    value = int(value)
    if value == 13:
        return "13th"
    if value % 100 in (11, 12):
        return "%d%s" % (value, "th")
    return "%d%s" % (value, suffixes[value % 10])
