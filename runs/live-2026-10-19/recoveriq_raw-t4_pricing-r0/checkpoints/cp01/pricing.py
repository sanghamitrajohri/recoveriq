"""Invoice pricing helpers."""


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents."""
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if not 0 <= discount_pct <= 100:
        raise ValueError("discount_pct must be between 0 and 100")
    gross = unit_price * quantity
    return round(gross * (1 - discount_pct / 100), 2)
