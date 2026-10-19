"""Sequence chunking."""


def chunk(items: list, size: int) -> list[list]:
    """Split ``items`` into consecutive lists of length ``size`` (the last may be shorter)."""
    return [items[i:i + size] for i in range(0, len(items) - size + 1, size)]
