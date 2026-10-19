"""Slug generation for article URLs."""
import re


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens."""
    # Lowercase the title
    title = title.lower()
    # Split on whitespace and join with hyphens
    words = title.split()
    return "-".join(words)
