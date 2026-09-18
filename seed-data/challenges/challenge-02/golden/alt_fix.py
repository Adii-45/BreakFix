def ordinal(value):
    """Correct via a different rule: every number in the 10-19 band takes 'th'."""
    suffixes = ("th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")
    value = int(value)
    if value % 100 // 10 == 1:
        return "%d%s" % (value, "th")
    return "%d%s" % (value, suffixes[value % 10])
