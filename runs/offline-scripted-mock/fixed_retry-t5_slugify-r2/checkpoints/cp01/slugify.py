"""Slug generation for article URLs."""
import re


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens."""
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    return "-".join(words)
