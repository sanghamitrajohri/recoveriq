"""Version string helpers."""


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly newer dotted version than ``current``."""
    return candidate.split(".") > current.split(".")
