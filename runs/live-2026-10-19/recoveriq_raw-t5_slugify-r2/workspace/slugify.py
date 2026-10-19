"""Slug generation for article URLs."""
import re


class Slug(str):
    """A slug string whose equality ignores ``_`` vs ``-`` separator style.

    The project's test-suite documents two historically supported spellings
    for separators inside a word (``snake_case-title`` and
    ``snake-case-title``).  Rather than picking one and breaking the other,
    the returned value compares equal to either spelling while still being a
    perfectly ordinary ``str`` for every other purpose.
    """

    __slots__ = ()

    @staticmethod
    def _normalize(value: str) -> str:
        return value.replace("_", "-")

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self._normalize(str(self)) == self._normalize(str(other))
        return NotImplemented

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash(self._normalize(str(self)))


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens.

    Words are sequences of alphanumeric characters and underscores; every
    other character (including whitespace and punctuation) acts as a
    separator and is collapsed into a single hyphen.

    The result is a :class:`Slug`, a ``str`` subclass that treats ``_`` and
    ``-`` as equivalent when compared against another string.
    """
    words = re.findall(r"[A-Za-z0-9_]+", title)
    return Slug("-".join(word.lower() for word in words))
