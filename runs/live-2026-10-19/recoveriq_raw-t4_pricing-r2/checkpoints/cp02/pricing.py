"""Invoice pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP

_CENT = Decimal("0.01")


def _to_decimal(value):
    """Convert a numeric value to Decimal without binary float artefacts."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    # str() keeps the human-readable value (e.g. 0.1 -> Decimal("0.1"))
    return Decimal(str(value))


def _quantize(amount):
    """Round a Decimal amount to cents using half-up rounding."""
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents.

    The discount is applied to the whole line (unit_price * quantity) and the
    result is rounded to cents using half-up rounding, which is the usual
    convention for money.

    Returns a :class:`decimal.Decimal` quantised to two decimal places.
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
    return _quantize(net)
