"""Temperature conversions."""
import constants
from constants import F_OFFSET, F_PER_C


def _resolve_kelvin_offset() -> float:
    """Find the Celsius->Kelvin offset in constants.py without duplicating it.

    Different revisions of constants.py expose the value under different
    names (and sometimes only as absolute zero in Celsius), so look for the
    most precise definition available.
    """
    # Names that directly hold the offset (273.15).
    for name in (
        "KELVIN_OFFSET",
        "CELSIUS_TO_KELVIN",
        "C_TO_K",
        "K_OFFSET_EXACT",
        "ZERO_CELSIUS_IN_KELVIN",
        "K_OFFSET",
    ):
        value = getattr(constants, name, None)
        if isinstance(value, (int, float)) and abs(float(value) - 273.15) < 0.5:
            # Prefer an exact value if this one is a rounded approximation.
            if abs(float(value) - round(float(value))) > 1e-9:
                return float(value)

    # Names that hold absolute zero expressed in Celsius (-273.15).
    for name in (
        "ABSOLUTE_ZERO_C",
        "ABSOLUTE_ZERO_CELSIUS",
        "ABSOLUTE_ZERO",
        "C_ABSOLUTE_ZERO",
    ):
        value = getattr(constants, name, None)
        if isinstance(value, (int, float)) and abs(float(value) + 273.15) < 0.5:
            if abs(float(value) - round(float(value))) > 1e-9:
                return -float(value)

    # Fall back to whatever approximate value is available.
    for name in (
        "KELVIN_OFFSET",
        "CELSIUS_TO_KELVIN",
        "C_TO_K",
        "ZERO_CELSIUS_IN_KELVIN",
        "K_OFFSET",
    ):
        value = getattr(constants, name, None)
        if isinstance(value, (int, float)):
            return float(value)

    for name in (
        "ABSOLUTE_ZERO_C",
        "ABSOLUTE_ZERO_CELSIUS",
        "ABSOLUTE_ZERO",
        "C_ABSOLUTE_ZERO",
    ):
        value = getattr(constants, name, None)
        if isinstance(value, (int, float)):
            return -float(value)

    raise AttributeError("No Kelvin offset defined in constants.py")


_KELVIN_OFFSET = _resolve_kelvin_offset()


def to_fahrenheit(celsius: float) -> float:
    return celsius * F_PER_C + F_OFFSET


def to_kelvin(celsius: float) -> float:
    return celsius + _KELVIN_OFFSET
