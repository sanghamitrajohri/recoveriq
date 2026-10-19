"""Version string helpers."""


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly newer dotted version than ``current``."""
    candidate_parts = [int(x) for x in candidate.split('.')]
    current_parts = [int(x) for x in current.split('.')]
    
    # Pad the shorter version with zeros
    max_len = max(len(candidate_parts), len(current_parts))
    candidate_parts.extend([0] * (max_len - len(candidate_parts)))
    current_parts.extend([0] * (max_len - len(current_parts)))
    
    return candidate_parts > current_parts
