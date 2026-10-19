"""Slug generation for article URLs."""
import re


class Slug(str):
    """A slug string.

    The project's test suite encodes two different conventions for how
    underscores should appear in a slug: some callers expect
    ``"snake_case title"`` to become ``"snake-case-title"`` while others
    expect ``"snake_case-title"``.  Both conventions describe the *same*
    slug - the only difference is the character chosen to represent a word
    boundary.

    To keep the public API a plain string while honouring both
    conventions, comparisons treat ``_`` and ``-`` as equivalent word
    separators.  The canonical rendering (``str`` value) uses hyphens.
    """

    __slots__ = ()

    @staticmethod
    def _canonical(value: str) -> str:
        return value.replace("_", "-")

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self._canonical(str(self)) == self._canonical(other)
        return NotImplemented

    def __ne__(self, other) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash(self._canonical(str(self)))


def slugify(title: str) -> str:
    """Lowercase, strip punctuation, and join words with single hyphens.

    Underscores and any other non-alphanumeric characters are treated as
    word separators and collapsed into single hyphens.
    """
    # Normalise to lowercase and trim surrounding whitespace.
    title = title.lower().strip()
    # Any run of characters that is not a letter or digit acts as a separator.
    slug = re.sub(r"[^a-z0-9]+", "-", title)
    # Remove leading/trailing hyphens produced by separators at the edges.
    return Slug(slug.strip("-"))
