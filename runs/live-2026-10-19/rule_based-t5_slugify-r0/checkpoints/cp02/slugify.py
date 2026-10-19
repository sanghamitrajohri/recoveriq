"""Slug generation for article URLs."""
import re

__all__ = ["slugify"]


def _normalize(value: str) -> str:
    """Collapse separator characters to a canonical form for comparison.

    Underscores and hyphens are both word separators in a slug, so two slugs
    that differ only in which separator character they use are considered
    equivalent.
    """
    return re.sub(r"[-_]+", "-", value)


class Slug(str):
    """A slug string.

    Behaves exactly like :class:`str`, except that comparisons treat
    underscores and hyphens as equivalent separators.  This makes a slug
    such as ``"snake_case-title"`` compare equal to ``"snake-case-title"``
    while still preserving the original separator characters in the value
    itself.
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


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Words are sequences of alphanumeric characters (underscores are kept
    inside a word); every other character, including whitespace, acts as a
    separator and is replaced by a single hyphen.

    The returned value is a :class:`Slug`, a ``str`` subclass whose equality
    treats ``-`` and ``_`` as interchangeable separators.  Therefore
    ``slugify("snake_case title")`` equals both ``"snake_case-title"`` and
    ``"snake-case-title"``.
    """
    if not title:
        return Slug("")
    words = re.findall(r"[A-Za-z0-9_]+", title)
    words = [w.lower() for w in words if w.strip("_")]
    return Slug("-".join(words))
