"""Version string helpers."""


def _parts(version: str, width: int) -> tuple[int, ...]:
    nums = [int(p) for p in version.split(".")]
    return tuple(nums + [0] * (width - len(nums)))


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly newer dotted version than ``current``."""
    width = max(candidate.count("."), current.count(".")) + 1
    return _parts(candidate, width) > _parts(current, width)
