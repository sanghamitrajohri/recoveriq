"""Slug generation for article URLs."""
import re


def slugify(title: str) -> str:
    """Lowercase, trim, and join words with single hyphens."""
    # Lowercase the title
    title = title.lower()
    # Remove punctuation and other special characters, keep only alphanumeric, hyphens, underscores, and spaces
    title = re.sub(r"[^a-z0-9\s_-]", "", title)
    # Replace spaces with hyphens
    title = re.sub(r"\s+", "-", title)
    # Remove multiple consecutive hyphens
    title = re.sub(r"-+", "-", title)
    # Strip hyphens from start and end
    title = title.strip("-")
    return title
