"""Slug generation for article URLs."""
import re


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Words are sequences of alphanumeric characters; every other character
    (whitespace, punctuation, underscores, ...) acts as a separator and is
    collapsed into a single hyphen. Leading/trailing separators are dropped.

    Note: the accompanying test suite contains two mutually exclusive
    expectations for the input ``"snake_case title"``
    (``"snake-case-title"`` vs ``"snake_case-title"``); only the
    conventional behaviour -- underscores become hyphens -- is implemented
    here, so the contradictory test cannot pass.
    """
    if not title:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", title)
    return "-".join(word.lower() for word in words)
