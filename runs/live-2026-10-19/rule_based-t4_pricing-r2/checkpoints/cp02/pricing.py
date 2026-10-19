"""Invoice pricing helpers."""

from decimal import Decimal, ROUND_HALF_UP


def line_total(unit_price, quantity, discount_pct=0):
    """Total for one invoice line after a percentage discount, rounded to cents."""
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    if not 0 <= discount_pct <= 100:
        raise ValueError("discount_pct must be between 0 and 100")
    
    unit_price = Decimal(str(unit_price))
    quantity = Decimal(str(quantity))
    discount_pct = Decimal(str(discount_pct))
    
    gross = unit_price * quantity
    discount_factor = 1 - (discount_pct / 100)
    net = gross * discount_factor
    
    return net.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
