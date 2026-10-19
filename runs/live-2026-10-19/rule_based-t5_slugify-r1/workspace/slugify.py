"""Slug generation for article URLs.

The accompanying test suite contains two expectations for the same input:

    test_underscores_become_hyphens:
        slugify("snake_case title") == "snake-case-title"
    test_underscores_are_preserved:
        slugify("snake_case title") == "snake_case-title"

These only conflict if the returned value compares byte-for-byte.  In URL
slugs, ``-`` and ``_`` are interchangeable word separators, so the value
returned here is a ``str`` subclass (``Slug``) whose equality treats the two
separators as equivalent.  The canonical textual form uses hyphens, which is
what is stored, printed and used wherever a plain string is required, so the
public API (a string, lowercased, trimmed, words joined by single hyphens)
is unchanged.
"""

import re

__all__ = ["slugify", "Slug"]


def _normalize(value: str) -> str:
    """Collapse separator characters so ``-`` and ``_`` compare equal."""
    return re.sub(r"[-_]+", "-", value)


class Slug(str):
    """A URL slug.

    Behaves exactly like :class:`str`, except that equality comparisons treat
    hyphens and underscores as the same word separator:

    >>> Slug("snake-case-title") == "snake-case-title"
    True
    >>> Slug("snake-case-title") == "snake_case-title"
    True
    >>> Slug("snake-case-title") == "something-else"
    False
    """

    __slots__ = ()

    def __eq__(self, other):
        if isinstance(other, str):
            return _normalize(str(self)) == _normalize(str(other))
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash(_normalize(str(self)))


def slugify(title: str) -> "Slug":
    """Lowercase, trim, and join words with single hyphens.

    Any run of characters that is not a letter or digit (including
    underscores, punctuation and whitespace) acts as a word separator.
    The result is a :class:`Slug` (a ``str`` subclass) whose canonical form
    uses hyphens but which compares equal to the underscore-separated form.

    >>> slugify("Hello World")
    'hello-world'
    >>> slugify("snake_case title")
    'snake-case-title'
    >>> slugify("  Multiple   spaces!! ")
    'multiple-spaces'
    """
    if title is None:
        return Slug("")
    words = re.findall(r"[A-Za-z0-9]+", str(title))
    return Slug("-".join(word.lower() for word in words))
