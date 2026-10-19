"""Invoice pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def _to_decimal(value):
    """Convert a numeric value to Decimal without binary float artifacts."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_cents(value):
    """Round a Decimal amount to cents using ROUND_HALF_UP."""
    return _to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents.

    The discount is applied to the gross amount (unit_price * quantity) and the
    result is rounded half-up to two decimal places, as is conventional for
    monetary amounts.

    Returns a :class:`decimal.Decimal` quantized to cents.
    """
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if not 0 <= discount_pct <= 100:
        raise ValueError("discount_pct must be between 0 and 100")

    price = _to_decimal(unit_price)
    qty = _to_decimal(quantity)
    discount = _to_decimal(discount_pct)

    gross = price * qty
    net = gross * (Decimal(1) - discount / Decimal(100))

    return _round_cents(net)
