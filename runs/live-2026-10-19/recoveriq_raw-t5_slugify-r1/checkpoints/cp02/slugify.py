"""Slug generation for article URLs."""
import re


def slugify(title: str) -> str:
    """Lowercase, strip punctuation, and join words with single hyphens.

    Underscores and any other non-alphanumeric characters are treated as
    word separators and collapsed into single hyphens.

    Note: the test suite contains two mutually exclusive expectations for
    underscores (``test_underscores_become_hyphens`` and
    ``test_underscores_are_preserved``); only one of them can hold. This
    implementation follows the conventional slug behaviour of turning
    underscores into hyphens.
    """
    # Normalise to lowercase and trim surrounding whitespace.
    title = title.lower().strip()
    # Any run of characters that is not a letter or digit acts as a separator.
    slug = re.sub(r"[^a-z0-9]+", "-", title)
    # Remove leading/trailing hyphens produced by separators at the edges.
    return slug.strip("-")
