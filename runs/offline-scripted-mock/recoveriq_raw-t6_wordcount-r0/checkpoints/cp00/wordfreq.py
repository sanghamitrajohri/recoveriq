"""Word frequency utilities."""
import re
from collections import Counter


def top_words(text: str, n: int) -> list[tuple[str, int]]:
    """Return the ``n`` most common lowercase words, ties broken alphabetically."""
    words = re.findall(r"[a-z']+", text.lower())
    counts = Counter(words)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[: n - 1]
