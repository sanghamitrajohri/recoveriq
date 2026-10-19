"""Slug generation for article URLs."""
import re


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Words are sequences of alphanumeric characters; every other character
    (including underscores and whitespace) acts as a separator and is
    collapsed into a single hyphen.

    Note: the test suite contains two mutually exclusive expectations for
    the input ``"snake_case title"`` (``"snake-case-title"`` versus
    ``"snake_case-title"``); only the documented hyphen behaviour can be
    implemented here.
    """
    words = re.findall(r"[A-Za-z0-9]+", title)
    return "-".join(word.lower() for word in words)
