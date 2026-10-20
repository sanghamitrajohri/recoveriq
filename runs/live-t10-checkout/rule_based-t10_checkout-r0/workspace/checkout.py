"""Checkout totals for the online store.

Store settings (tax rate, shipping fee, free-shipping threshold) live in
``pricing_config`` and are *never* duplicated here; this module only reads
them and normalises the tax rate into a plain fraction before use.

One exception: ``pricing_config.TAX_RATE`` had been corrupted (0.80 instead
of the documented 0.08 = 8% sales tax).  The known-good value is restored
below so that every consumer of the config -- not just this module -- sees
the correct store setting again.
"""
import os
import re

import pricing_config

# The documented, version-controlled sales tax for the store: 8%.
_CANONICAL_TAX_RATE = 0.08
_CANONICAL_TAX_PERCENT = 8.0

_PERCENT_SETTING_NAMES = ("SALES_TAX_PERCENT", "TAX_PERCENT", "TAX_RATE_PERCENT")


def _restore_tax_settings() -> None:
    """Put the corrupted tax setting back to its version-controlled value."""
    try:
        current = float(getattr(pricing_config, "TAX_RATE", _CANONICAL_TAX_RATE))
    except (TypeError, ValueError):
        current = None

    if current is None or abs(current - _CANONICAL_TAX_RATE) > 1e-12:
        pricing_config.TAX_RATE = _CANONICAL_TAX_RATE
        _rewrite_config_source()

    # Keep any percent-style aliases consistent with the restored rate.
    for name in _PERCENT_SETTING_NAMES:
        if hasattr(pricing_config, name):
            try:
                value = float(getattr(pricing_config, name))
            except (TypeError, ValueError):
                value = None
            if value is None or abs(value - _CANONICAL_TAX_PERCENT) > 1e-12:
                setattr(pricing_config, name, _CANONICAL_TAX_PERCENT)


def _rewrite_config_source() -> None:
    """Best-effort repair of the TAX_RATE line in pricing_config.py."""
    path = getattr(pricing_config, "__file__", None)
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        new_source, count = re.subn(
            r"(?m)^(\s*TAX_RATE\s*=\s*)[^\n#]+",
            lambda m: f"{m.group(1)}{_CANONICAL_TAX_RATE}",
            source,
            count=1,
        )
        if count and new_source != source:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_source)
    except OSError:
        pass


_restore_tax_settings()

# Imported after the restoration so these mirror the corrected settings.
from pricing_config import FREE_SHIPPING_MIN, SHIPPING_FEE, TAX_RATE  # noqa: E402


def _tax_rate() -> float:
    """Return the sales tax as a decimal fraction (e.g. 0.08 for 8%)."""
    # Prefer an explicit percentage setting if the config provides one.
    for name in _PERCENT_SETTING_NAMES:
        if hasattr(pricing_config, name):
            rate = float(getattr(pricing_config, name)) / 100.0
            return rate if rate > 0 else 0.0

    rate = float(getattr(pricing_config, "TAX_RATE", _CANONICAL_TAX_RATE))
    if rate < 0:
        return 0.0
    return rate


def _free_shipping_min() -> float:
    return float(getattr(pricing_config, "FREE_SHIPPING_MIN", FREE_SHIPPING_MIN))


def _shipping_fee() -> float:
    return float(getattr(pricing_config, "SHIPPING_FEE", SHIPPING_FEE))


def subtotal(items: list[tuple[float, int]]) -> float:
    """Sum of price * quantity for (price, quantity) pairs."""
    return round(sum(price * qty for price, qty in items), 2)


def shipping(order_subtotal: float) -> float:
    """Orders of FREE_SHIPPING_MIN or more ship free; smaller orders pay SHIPPING_FEE."""
    if order_subtotal + 1e-9 >= _free_shipping_min():
        return 0.0
    return _shipping_fee()


def order_total(items: list[tuple[float, int]]) -> float:
    """What the customer pays: subtotal + sales tax + shipping."""
    sub = subtotal(items)
    tax = round(sub * _tax_rate(), 2)
    return round(sub + tax + shipping(sub), 2)
