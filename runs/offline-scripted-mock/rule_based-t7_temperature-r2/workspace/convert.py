"""Temperature conversions."""
from constants import F_OFFSET, F_PER_C, K_OFFSET


def to_fahrenheit(celsius: float) -> float:
    return celsius * F_PER_C + F_OFFSET


def to_kelvin(celsius: float) -> float:
    return celsius + K_OFFSET
