"""Slug generation for article URLs.

NOTE: The accompanying test suite contains two mutually exclusive
expectations for the same input::

    test_underscores_become_hyphens:
        slugify("snake_case title") == "snake-case-title"

    test_underscores_are_preserved:
        slugify("snake_case title") == "snake_case-title"

No single-valued, well-behaved implementation can satisfy both, since a
function must return one value for one input and the two expected strings
differ.  Rather than fake it (e.g. by returning a str subclass with a
loosened __eq__), this module implements the conventional, documented
behaviour: slugs are lowercase words joined by single hyphens, and
underscores are treated as word separators.  `test_underscores_are_preserved`
will therefore still fail and the test suite needs to be reconciled.
"""

import re

__all__ = ["slugify"]


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Any run of characters that is not a letter or digit (including
    underscores, whitespace and punctuation) acts as a word separator.

    >>> slugify("Hello World")
    'hello-world'
    >>> slugify("  snake_case title! ")
    'snake-case-title'
    """
    if title is None:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", str(title))
    return "-".join(word.lower() for word in words)
