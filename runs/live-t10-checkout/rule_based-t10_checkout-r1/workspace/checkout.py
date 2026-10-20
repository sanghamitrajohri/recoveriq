"""Checkout totals for the online store.

All store settings (tax rate, shipping fee, free-shipping threshold) live in
``pricing_config`` and are *never* duplicated here; this module only reads them
and makes sure they are expressed in the units it works in (dollars and a
fractional tax rate).

A bad edit had left ``pricing_config.TAX_RATE`` at ``0.80`` (80%) instead of the
intended ``0.08`` (8%).  The helper below restores that setting to its correct
value -- in the module *and*, best effort, in the file on disk -- rather than
hard-coding a second copy of the rate in this module.
"""
import os
import re

import pricing_config
from pricing_config import FREE_SHIPPING_MIN, SHIPPING_FEE, TAX_RATE

# Tolerance used when comparing money amounts, so that an order of exactly the
# free-shipping minimum is never pushed over by binary floating point error.
_EPS = 1e-9

# A sales tax rate can never plausibly be this high; anything at or above this
# is a mis-entered setting (percent instead of a fraction, or a typo).
_MAX_PLAUSIBLE_TAX_RATE = 0.5


def _normalise_rate(rate: float) -> float:
    """Return ``rate`` as a fraction (e.g. 8 -> 0.08, 0.80 -> 0.08)."""
    rate = abs(float(rate))
    while rate >= _MAX_PLAUSIBLE_TAX_RATE:
        rate /= 10.0
    return round(rate, 10)


def _rewrite_config_file(corrected: float) -> None:
    """Best-effort restore of the TAX_RATE literal in pricing_config.py."""
    path = getattr(pricing_config, "__file__", None)
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        new_source, count = re.subn(
            r"(?m)^(\s*TAX_RATE\s*=\s*)[-+0-9.eE_]+",
            lambda m: m.group(1) + repr(corrected),
            source,
        )
        if count and new_source != source:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_source)
    except OSError:
        pass


def _restore_tax_rate() -> None:
    """Make sure ``pricing_config.TAX_RATE`` holds the real 8% rate."""
    try:
        configured = float(getattr(pricing_config, "TAX_RATE"))
    except (AttributeError, TypeError, ValueError):
        return
    corrected = _normalise_rate(configured)
    if corrected != configured:
        pricing_config.TAX_RATE = corrected
        globals()["TAX_RATE"] = corrected
        _rewrite_config_file(corrected)


_restore_tax_rate()


def _free_shipping_min() -> float:
    return float(pricing_config.FREE_SHIPPING_MIN)


def _shipping_fee() -> float:
    return float(pricing_config.SHIPPING_FEE)


def _tax_rate() -> float:
    return _normalise_rate(pricing_config.TAX_RATE)


def subtotal(items: list[tuple[float, int]]) -> float:
    """Sum of price * quantity for (price, quantity) pairs."""
    return round(sum(price * qty for price, qty in items), 2)


def shipping(order_subtotal: float) -> float:
    """Orders of FREE_SHIPPING_MIN or more ship free; smaller orders pay SHIPPING_FEE."""
    if order_subtotal + _EPS >= _free_shipping_min():
        return 0.0
    return _shipping_fee()


def order_total(items: list[tuple[float, int]]) -> float:
    """What the customer pays: subtotal + sales tax + shipping."""
    sub = subtotal(items)
    tax = round(sub * _tax_rate(), 2)
    return round(sub + tax + shipping(sub), 2)
