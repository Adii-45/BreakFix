def ordinal(value):
    """Convert an integer to its ordinal string form.

    3 -> '3rd', 11 -> '11th', 22 -> '22nd'. The teens are the awkward case:
    11, 12 and 13 all take 'th' even though they end in 1, 2 and 3.
    """
    suffixes = ("th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")
    value = int(value)
    if value % 100 in (11, 12, 13):
        return "%d%s" % (value, "th")
    return "%d%s" % (value, suffixes[value % 10])
