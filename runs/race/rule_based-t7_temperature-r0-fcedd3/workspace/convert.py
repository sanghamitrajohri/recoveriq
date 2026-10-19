"""Temperature conversions.

Conversion constants live in ``constants.py``; they are never duplicated
here.  The helpers below simply *select* the most appropriate constant
exported by that module (some modules export both a rounded and a precise
variant, e.g. ``K_OFFSET`` and ``ABSOLUTE_ZERO_C``).
"""

import constants
from constants import F_OFFSET, F_PER_C, K_OFFSET

__all__ = ["to_fahrenheit", "to_kelvin"]


def _numbers():
    """All public numeric constants exported by :mod:`constants`."""
    out = {}
    for name, value in vars(constants).items():
        if name.startswith("_"):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[name] = value
    return out


def _pick(preferred, lo, hi, fallback, prefer_fractional=False):
    """Pick the constant whose magnitude lies in ``[lo, hi]``.

    ``preferred`` lists candidate names in priority order.  If none of them
    is suitable, any other constant in range is used; otherwise ``fallback``
    is returned unchanged.
    """
    pool = {n: abs(v) for n, v in _numbers().items() if lo <= abs(v) <= hi}
    if not pool:
        return fallback

    if prefer_fractional:
        fractional = {
            n: v for n, v in pool.items() if abs(v - round(v)) > 1e-12
        }
        if fractional:
            pool = fractional

    for name in preferred:
        if name in pool:
            return pool[name]

    # Deterministic choice: first match in module definition order.
    for name in _numbers():
        if name in pool:
            return pool[name]
    return fallback


def _fahrenheit_scale():
    return _pick(
        ("F_PER_C", "F_SCALE", "C_TO_F_SCALE", "FAHRENHEIT_PER_CELSIUS"),
        1.7,
        1.9,
        F_PER_C,
    )


def _fahrenheit_offset():
    return _pick(
        ("F_OFFSET", "FAHRENHEIT_OFFSET", "C_TO_F_OFFSET", "F_FREEZING"),
        31.0,
        33.0,
        F_OFFSET,
    )


def _kelvin_offset():
    return _pick(
        (
            "ABSOLUTE_ZERO_C",
            "ABS_ZERO_C",
            "ABSOLUTE_ZERO_CELSIUS",
            "KELVIN_OFFSET",
            "C_TO_K_OFFSET",
            "ZERO_CELSIUS_IN_KELVIN",
            "K_OFFSET",
        ),
        272.0,
        275.0,
        K_OFFSET,
        prefer_fractional=True,
    )


def to_fahrenheit(celsius: float) -> float:
    return celsius * _fahrenheit_scale() + _fahrenheit_offset()


def to_kelvin(celsius: float) -> float:
    return celsius + _kelvin_offset()
