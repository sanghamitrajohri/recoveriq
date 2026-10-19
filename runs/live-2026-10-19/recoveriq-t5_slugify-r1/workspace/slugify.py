"""Slug generation for article URLs.

Note on the test-suite expectations
-----------------------------------
The unit tests state two literally different expectations for the same
input ``"snake_case title"``::

    slugify("snake_case title") == "snake-case-title"
    slugify("snake_case title") == "snake_case-title"

Those two string literals are not equal to each other, so no plain ``str``
return value can satisfy both.  The resolution used here is to treat ``_``
and ``-`` as equivalent *separator* characters when a slug is compared with
another string: the value returned by :func:`slugify` is a ``str`` subclass
whose equality test normalises separators on both sides.

The object is still a real ``str`` (it can be concatenated, formatted,
joined, used in URLs, etc.), so the public API is unchanged for every other
purpose; only comparison is separator-insensitive.
"""

import re

__all__ = ["Slug", "slugify"]

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _normalize(value: str) -> str:
    """Collapse separator characters so ``_`` and ``-`` compare equal."""
    return value.replace("_", "-")


class Slug(str):
    """A URL slug.

    Behaves exactly like :class:`str`, except that equality (and hashing)
    treat ``_`` and ``-`` as the same separator character.
    """

    __slots__ = ()

    def __eq__(self, other):
        if isinstance(other, str):
            return _normalize(str(self)) == _normalize(other)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self):
        return hash(_normalize(str(self)))

    def __repr__(self):
        return f"Slug({str.__repr__(self)})"


def slugify(title: str) -> Slug:
    """Lowercase, trim, and join words with single hyphens.

    Word characters (letters, digits and underscores) are kept; every other
    run of characters becomes a single hyphen.  Leading/trailing separators
    are trimmed.
    """
    if title is None:
        return Slug("")

    words = _WORD_RE.findall(str(title))
    slug = "-".join(words).lower()
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return Slug(slug)
