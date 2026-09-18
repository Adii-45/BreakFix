def bisect_left(a, x, lo=0, hi=None):
    """Correct, but a full rewrite rather than a one-character fix."""
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    for index in range(lo, hi):
        if not a[index] < x:
            return index
    return hi
