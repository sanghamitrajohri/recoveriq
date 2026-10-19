"""Parse compact duration strings such as '2d4h', '1h30m' or '45s'."""
import re

SECONDS_PER_DAY = 86400
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60

_TOKEN = re.compile(r"(\d+)([dhms])")


def parse_duration(text: str) -> int:
    """Return the total number of seconds represented by ``text``."""
    text = text.strip().lower()
    if not text or _TOKEN.sub("", text):
        raise ValueError(f"invalid duration: {text!r}")
    total = 0
    for amount, unit in _TOKEN.findall(text):
        n = int(amount)
        if unit == "d":
            total += n * SECONDS_PER_DAY
        elif unit == "h":
            total += n * SECONDS_PER_HOUR
        elif unit == "m":
            total += n * SECONDS_PER_MINUTE
        elif unit == "s":
            total += n
    return total
