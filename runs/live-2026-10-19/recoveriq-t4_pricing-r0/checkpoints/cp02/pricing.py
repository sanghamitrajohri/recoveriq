"""Invoice pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def _to_decimal(value):
    """Convert a numeric value to Decimal without binary float artifacts."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    # Using str() keeps the decimal literal the user wrote (e.g. 1.005)
    return Decimal(str(value))


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents.

    The discount is applied to the gross amount (unit_price * quantity) and the
    result is rounded to two decimal places using "round half up" (the
    conventional money rounding policy), not Python's banker's rounding.

    Returns a :class:`decimal.Decimal` quantized to cents.
    """
    price = _to_decimal(unit_price)
    qty = _to_decimal(quantity)
    discount = _to_decimal(discount_pct)

    if qty < 0:
        raise ValueError("quantity must be non-negative")
    if price < 0:
        raise ValueError("unit_price must be non-negative")
    if not Decimal(0) <= discount <= Decimal(100):
        raise ValueError("discount_pct must be between 0 and 100")

    gross = price * qty
    net = gross * (Decimal(1) - discount / Decimal(100))

    return net.quantize(CENT, rounding=ROUND_HALF_UP)
