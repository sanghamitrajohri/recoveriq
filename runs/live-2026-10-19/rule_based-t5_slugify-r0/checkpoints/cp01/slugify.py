"""Slug generation for article URLs."""
import re

__all__ = ["slugify"]


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Words are sequences of alphanumeric characters; every other character
    (including underscores and whitespace) acts as a separator.

    Note: the test suite contains two mutually exclusive expectations for
    ``slugify("snake_case title")`` ("snake-case-title" vs
    "snake_case-title"); no single string value can satisfy both. This
    implementation follows the documented behaviour of turning separators,
    including underscores, into single hyphens.
    """
    if not title:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", title)
    return "-".join(word.lower() for word in words)
