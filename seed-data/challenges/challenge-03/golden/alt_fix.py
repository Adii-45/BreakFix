def naturalsize(value, binary=False, gnu=False):
    """Correct, but replaces the threshold loop with repeated division."""
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

    index = 0
    scaled = abs_bytes / base
    while scaled >= base and index < len(suffixes) - 1:
        scaled /= base
        index += 1

    suffix = suffixes[index]
    scaled = num_bytes / (base ** (index + 1))
    if gnu:
        return "%.1f%s" % (scaled, suffix)
    return "%.1f %s" % (scaled, suffix)
