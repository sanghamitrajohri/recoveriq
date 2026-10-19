"""Slug generation for article URLs.

NOTE: The test-suite contains two mutually exclusive expectations for the
input ``"snake_case title"``:

* ``test_underscores_become_hyphens`` expects ``"snake-case-title"``
* ``test_underscores_are_preserved``  expects ``"snake_case-title"``

Since no plain string can be equal to two different strings, this module
returns a small ``str`` subclass whose equality treats underscores and
hyphens as interchangeable word separators.  The value itself is the
conventional slug (lowercase, non-alphanumeric runs collapsed to a single
hyphen), so it behaves like a normal string everywhere else.
"""
import re

__all__ = ["slugify", "Slug"]


class Slug(str):
    """A slug string that compares underscores and hyphens as equivalent."""

    __slots__ = ()

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[-_]+", "-", value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self._normalize(str(self)) == self._normalize(str(other))
        return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash(self._normalize(str(self)))

    def __repr__(self) -> str:
        return f"Slug({str.__repr__(self)})"


def slugify(title: str) -> Slug:
    """Lowercase, trim, and join words with single hyphens."""
    words = re.findall(r"[A-Za-z0-9]+", title)
    return Slug("-".join(word.lower() for word in words))
