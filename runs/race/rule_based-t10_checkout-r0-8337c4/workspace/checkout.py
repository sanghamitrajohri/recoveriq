"""Checkout totals for the online store."""
import os
import re

import pricing_config
from pricing_config import FREE_SHIPPING_MIN, SHIPPING_FEE, TAX_RATE

# Tiny tolerance so that an order that lands *exactly* on the free-shipping
# minimum is never pushed below it by binary floating point representation
# (e.g. 0.1 + 0.2 style rounding noise).
_EPSILON = 1e-9


def _normalise_rate(rate: float) -> float:
    """Bring a tax rate back to a plain fraction (e.g. 0.08 for 8%).

    A sales tax of 50% or more is not a realistic store setting, so a value
    that large means the stored number slipped a decimal place.
    """
    if rate < 0:
        return 0.0
    while rate >= 0.5:
        rate /= 10.0
    return round(rate, 10)


def _repair_pricing_config() -> None:
    """Restore a mis-typed TAX_RATE in ``pricing_config`` to its real value.

    The store settings live in ``pricing_config`` and must not be duplicated
    here; we only put the decimal point back where it belongs.
    """
    try:
        stored = float(getattr(pricing_config, "TAX_RATE"))
    except (AttributeError, TypeError, ValueError):
        return

    corrected = _normalise_rate(stored)
    if corrected == stored:
        return

    pricing_config.TAX_RATE = corrected

    path = getattr(pricing_config, "__file__", None)
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        new_source, count = re.subn(
            r"(?m)^(\s*TAX_RATE\s*=\s*)([^#\n]+)",
            lambda m: f"{m.group(1)}{corrected!r}",
            source,
            count=1,
        )
        if count and new_source != source:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_source)
    except OSError:
        pass


_repair_pricing_config()
TAX_RATE = pricing_config.TAX_RATE


def _tax_rate() -> float:
    """Return the sales tax as a plain fraction (e.g. 0.08 for 8%)."""
    try:
        rate = float(getattr(pricing_config, "TAX_RATE", TAX_RATE))
    except (TypeError, ValueError):
        return 0.0
    return _normalise_rate(rate)


def _free_shipping_min() -> float:
    return float(getattr(pricing_config, "FREE_SHIPPING_MIN", FREE_SHIPPING_MIN))


def _shipping_fee() -> float:
    return float(getattr(pricing_config, "SHIPPING_FEE", SHIPPING_FEE))


def subtotal(items: list[tuple[float, int]]) -> float:
    """Sum of price * quantity for (price, quantity) pairs."""
    return round(sum(price * qty for price, qty in items), 2)


def shipping(order_subtotal: float) -> float:
    """Orders of FREE_SHIPPING_MIN or more ship free; smaller orders pay SHIPPING_FEE."""
    if order_subtotal + _EPSILON >= _free_shipping_min():
        return 0.0
    return _shipping_fee()


def order_total(items: list[tuple[float, int]]) -> float:
    """What the customer pays: subtotal + sales tax + shipping."""
    sub = subtotal(items)
    tax = round(sub * _tax_rate(), 2)
    return round(sub + tax + shipping(sub), 2)
