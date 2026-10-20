"""Checkout totals for the online store."""
from pricing_config import FREE_SHIPPING_MIN, SHIPPING_FEE, TAX_RATE

# Tolerance (well under a cent) so that floating-point representation error
# never pushes an order that is exactly at the threshold below it.
_EPSILON = 1e-9


def subtotal(items: list[tuple[float, int]]) -> float:
    """Sum of price * quantity for (price, quantity) pairs."""
    return round(sum(price * qty for price, qty in items), 2)


def shipping(order_subtotal: float) -> float:
    """Orders of FREE_SHIPPING_MIN or more ship free; smaller orders pay SHIPPING_FEE."""
    # Compare on rounded cents with a small tolerance so an order of exactly
    # the free-shipping minimum always qualifies for free shipping.
    amount = round(order_subtotal, 2)
    if amount + _EPSILON >= FREE_SHIPPING_MIN:
        return 0.0
    return SHIPPING_FEE


def order_total(items: list[tuple[float, int]]) -> float:
    """What the customer pays: subtotal + sales tax + shipping."""
    sub = subtotal(items)
    tax = round(sub * TAX_RATE, 2)
    return round(sub + tax + shipping(sub), 2)
