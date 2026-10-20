"""Checkout totals for the online store."""
from pricing_config import FREE_SHIPPING_MIN, SHIPPING_FEE, TAX_RATE


def subtotal(items: list[tuple[float, int]]) -> float:
    """Sum of price * quantity for (price, quantity) pairs."""
    return round(sum(price * qty for price, qty in items), 2)


def shipping(order_subtotal: float) -> float:
    """Orders of FREE_SHIPPING_MIN or more ship free; smaller orders pay SHIPPING_FEE."""
    return 0.0 if order_subtotal > FREE_SHIPPING_MIN else SHIPPING_FEE


def order_total(items: list[tuple[float, int]]) -> float:
    """What the customer pays: subtotal + sales tax + shipping."""
    sub = subtotal(items)
    tax = round(sub * TAX_RATE, 2)
    return round(sub + tax + shipping(sub), 2)
