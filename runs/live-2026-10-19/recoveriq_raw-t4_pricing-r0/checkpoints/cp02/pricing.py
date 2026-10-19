"""Invoice pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP

_CENTS = Decimal("0.01")


def _to_decimal(value):
    """Convert a numeric value to Decimal without binary float artifacts."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents.

    The discount is applied to the line subtotal (unit_price * quantity), and
    the result is rounded half-up to two decimal places.

    Returns a ``decimal.Decimal`` quantized to cents (finance policy: never
    use binary floats or the built-in ``round()`` for monetary amounts).
    """
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if not 0 <= discount_pct <= 100:
        raise ValueError("discount_pct must be between 0 and 100")

    price = _to_decimal(unit_price)
    qty = _to_decimal(quantity)
    discount = _to_decimal(discount_pct)

    subtotal = price * qty
    discounted = subtotal * (Decimal(1) - discount / Decimal(100))
    return discounted.quantize(_CENTS, rounding=ROUND_HALF_UP)
