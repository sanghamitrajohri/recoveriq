"""Slug generation for article URLs."""
import re

# NOTE: test_underscores_become_hyphens and test_underscores_are_preserved
# make mutually exclusive assertions about slugify("snake_case title"):
# one expects "snake-case-title", the other "snake_case-title".
# No implementation can satisfy both; this module implements the documented
# behaviour (all non-alphanumeric runs become single hyphens).


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens."""
    words = re.findall(r"[A-Za-z0-9]+", title)
    return "-".join(word.lower() for word in words)
