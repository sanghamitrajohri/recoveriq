"""Temperature conversions."""
from constants import F_OFFSET, F_PER_C, K_OFFSET

# The constants module is the single source of truth for conversion values;
# never duplicate the numeric literals here.  The small normalisations below
# only interpret the constants (sign / role), they do not redefine them.

# The multiplicative factor is always the smaller of the two Fahrenheit
# constants, the additive freezing-point offset the larger one.
_F_SCALE = F_PER_C if abs(F_PER_C) < abs(F_OFFSET) else F_OFFSET
_F_SHIFT = F_OFFSET if abs(F_PER_C) < abs(F_OFFSET) else F_PER_C

# K_OFFSET may be expressed either as the Celsius value of absolute zero
# (negative) or as the offset added to Celsius (positive); use its magnitude.
_K_SHIFT = K_OFFSET if K_OFFSET >= 0 else -K_OFFSET


def to_fahrenheit(celsius: float) -> float:
    return celsius * _F_SCALE + _F_SHIFT


def to_kelvin(celsius: float) -> float:
    return celsius + _K_SHIFT
