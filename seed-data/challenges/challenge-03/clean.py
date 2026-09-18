def naturalsize(value, binary=False, gnu=False):
    """Format a byte count as a human-readable string.

    naturalsize(3000) -> '3.0 kB'
    naturalsize(3000, binary=True) -> '2.9 KiB'
    naturalsize(3000, gnu=True) -> '2.9K'
    """
    decimal_suffixes = ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    binary_suffixes = ("KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    gnu_suffixes = ("K", "M", "G", "T", "P", "E", "Z", "Y")

    if gnu:
        suffixes = gnu_suffixes
    elif binary:
        suffixes = binary_suffixes
    else:
        suffixes = decimal_suffixes

    base = 1024 if (binary or gnu) else 1000
    num_bytes = float(value)
    abs_bytes = abs(num_bytes)

    if abs_bytes == 1 and not gnu:
        return "%d Byte" % num_bytes
    if abs_bytes < base and not gnu:
        return "%d Bytes" % num_bytes
    if abs_bytes < base and gnu:
        return "%dB" % num_bytes

    unit = base
    suffix = suffixes[0]
    for index, candidate in enumerate(suffixes):
        unit = base ** (index + 2)
        suffix = candidate
        if abs_bytes < unit:
            break

    if gnu:
        return "%.1f%s" % ((base * num_bytes / unit), suffix)
    return "%.1f %s" % ((base * num_bytes / unit), suffix)
