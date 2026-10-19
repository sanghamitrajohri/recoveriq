"""Invoice pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def _to_decimal(value):
    """Convert a numeric value to Decimal without binary float noise."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents.

    The discount is applied to the full line amount (unit_price * quantity),
    and the result is rounded half-up to two decimal places.

    Returns a ``decimal.Decimal`` quantized to cents (never a float).
    """
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if not 0 <= discount_pct <= 100:
        raise ValueError("discount_pct must be between 0 and 100")

    price = _to_decimal(unit_price)
    qty = _to_decimal(quantity)
    pct = _to_decimal(discount_pct)

    gross = price * qty
    discount = gross * pct / Decimal(100)
    net = gross - discount

    return net.quantize(CENT, rounding=ROUND_HALF_UP)
