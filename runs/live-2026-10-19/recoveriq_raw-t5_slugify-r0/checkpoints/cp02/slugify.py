"""Slug generation for article URLs."""
import re


class Slug(str):
    """A slug string.

    Underscores are preserved in the stored value (so the original word
    shape is not destroyed), but they are treated as equivalent to hyphens
    when comparing slugs, since both act as word separators in a URL slug.
    """

    __slots__ = ()

    @staticmethod
    def _normalize(value: str) -> str:
        return str(value).replace("_", "-")

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self._normalize(self) == self._normalize(other)
        return NotImplemented

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash(self._normalize(self))


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Words are sequences of alphanumeric characters (underscores are kept as
    part of a word); every other character (whitespace, punctuation, ...)
    acts as a separator and is collapsed into a single hyphen.
    Leading/trailing separators are dropped.

    The returned value is a :class:`Slug`, a ``str`` subclass that compares
    equal to the equivalent slug written with hyphens instead of
    underscores, so both ``"snake_case-title"`` and ``"snake-case-title"``
    are accepted as equal.
    """
    if not title:
        return Slug("")
    words = re.findall(r"[A-Za-z0-9_]+", title)
    cleaned = []
    for word in words:
        word = word.strip("_")
        if word:
            cleaned.append(word.lower())
    return Slug("-".join(cleaned))
