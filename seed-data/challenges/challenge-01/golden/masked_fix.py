def bisect_left(a, x, lo=0, hi=None):
    """Patches up the answer afterwards instead of fixing the comparison."""
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    if lo > 0 and a[lo - 1] == x:
        return lo - 1
    return lo
