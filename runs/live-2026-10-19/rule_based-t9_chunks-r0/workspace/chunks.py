"""Sequence chunking."""


def chunk(items: list, size: int) -> list[list]:
    """Split ``items`` into consecutive lists of length ``size`` (the last may be shorter)."""
    if not isinstance(size, int) or size <= 0:
        raise ValueError("size must be a positive integer")
    return [items[i:i + size] for i in range(0, len(items), size)]
