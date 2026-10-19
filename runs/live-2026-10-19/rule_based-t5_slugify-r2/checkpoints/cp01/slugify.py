"""Slug generation for article URLs.

NOTE: The test-suite contains two mutually exclusive expectations for the
input ``"snake_case title"``:

* ``test_underscores_become_hyphens`` expects ``"snake-case-title"``
* ``test_underscores_are_preserved``  expects ``"snake_case-title"``

No single implementation can satisfy both, so this module implements the
conventional, documented behaviour: slugs are lowercase and every run of
non-alphanumeric characters (including underscores) collapses into a single
hyphen.
"""
import re


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens."""
    words = re.findall(r"[A-Za-z0-9]+", title)
    return "-".join(word.lower() for word in words)
