"""Slug generation for article URLs.

NOTE: The accompanying test suite contains two mutually exclusive
expectations for the same input:

    test_underscores_become_hyphens:
        slugify("snake_case title") == "snake-case-title"
    test_underscores_are_preserved:
        slugify("snake_case title") == "snake_case-title"

A single deterministic function cannot satisfy both, so it is impossible
to make every test pass without changing the tests (which is out of
scope).  This implementation follows the conventional URL-slug behaviour
documented in the public API (lowercase, trim, join words with single
hyphens), which satisfies test_basic and test_underscores_become_hyphens.
The remaining test documents a conflicting requirement and should be
reconciled with the product owner.
"""

import re

__all__ = ["slugify"]


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Any run of characters that is not a letter or digit (including
    underscores, punctuation and whitespace) acts as a word separator.

    >>> slugify("Hello World")
    'hello-world'
    >>> slugify("snake_case title")
    'snake-case-title'
    >>> slugify("  Multiple   spaces!! ")
    'multiple-spaces'
    """
    if title is None:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", str(title))
    return "-".join(word.lower() for word in words)
