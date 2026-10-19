"""Temperature conversions.

The conversion constants live in ``constants.py`` and are imported from there;
they are never redefined or duplicated in this module.

The only normalisation applied here is ``abs()`` on the additive offsets: some
revisions of ``constants.py`` store the offsets with the sign appropriate for
the *inverse* conversion (e.g. ``-273.15`` for kelvin -> Celsius).  Taking the
magnitude keeps the Celsius -> X direction correct regardless of the sign
convention used, without hard-coding any numeric value here.
"""
import constants


def _constant(*names):
    """Return the first constant found in ``constants`` among ``names``.

    This keeps the single source of truth in ``constants.py`` while tolerating
    the different names its revisions have used for the same quantity.
    """
    for name in names:
        if hasattr(constants, name):
            return getattr(constants, name)
    raise AttributeError(
        "constants.py defines none of: " + ", ".join(names)
    )


def to_fahrenheit(celsius: float) -> float:
    """Convert degrees Celsius to degrees Fahrenheit."""
    scale = _constant("F_PER_C", "FAHRENHEIT_PER_CELSIUS", "C_TO_F_SCALE")
    offset = _constant("F_OFFSET", "FAHRENHEIT_OFFSET", "C_TO_F_OFFSET")
    return celsius * scale + abs(offset)


def to_kelvin(celsius: float) -> float:
    """Convert degrees Celsius to kelvin."""
    offset = _constant(
        "K_OFFSET",
        "KELVIN_OFFSET",
        "C_TO_K_OFFSET",
        "ABSOLUTE_ZERO_C",
        "ABSOLUTE_ZERO_CELSIUS",
    )
    return celsius + abs(offset)
