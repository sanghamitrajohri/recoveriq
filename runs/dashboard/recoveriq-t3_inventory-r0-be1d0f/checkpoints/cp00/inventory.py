"""Inventory domain model and reporting utilities for a small warehouse.

The module intentionally contains a fair amount of surrounding code: the agent has to
return the whole file, so its size matters for output-token budgets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class Supplier:
    """A vendor that can restock items."""

    supplier_id: str
    name: str
    lead_time_days: int
    min_order_value: float = 0.0

    def expected_delivery(self, ordered_on: date) -> date:
        """Return the date an order placed on ``ordered_on`` should arrive."""
        return ordered_on + timedelta(days=self.lead_time_days)


@dataclass
class Item:
    """A stock-keeping unit tracked in the warehouse."""

    sku: str
    description: str
    on_hand: int
    reorder_point: int
    reorder_quantity: int
    unit_cost: float
    supplier_id: str
    tags: set[str] = field(default_factory=set)

    def stock_value(self) -> float:
        """Total cost value of the units currently on hand."""
        return round(self.on_hand * self.unit_cost, 2)

    def is_discontinued(self) -> bool:
        return "discontinued" in self.tags


@dataclass
class Movement:
    """A single stock movement; positive quantities are receipts, negative are issues."""

    sku: str
    quantity: int
    on: date
    reason: str = ""


class Inventory:
    """In-memory inventory with suppliers, items and a movement ledger."""

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}
        self._suppliers: dict[str, Supplier] = {}
        self._ledger: list[Movement] = []

    # ------------------------------------------------------------------ setup
    def add_supplier(self, supplier: Supplier) -> None:
        if supplier.supplier_id in self._suppliers:
            raise ValueError(f"duplicate supplier {supplier.supplier_id}")
        self._suppliers[supplier.supplier_id] = supplier

    def add_item(self, item: Item) -> None:
        if item.sku in self._items:
            raise ValueError(f"duplicate sku {item.sku}")
        if item.supplier_id not in self._suppliers:
            raise KeyError(f"unknown supplier {item.supplier_id}")
        if item.on_hand < 0 or item.reorder_point < 0 or item.reorder_quantity <= 0:
            raise ValueError(f"invalid stock levels for {item.sku}")
        self._items[item.sku] = item

    def item(self, sku: str) -> Item:
        try:
            return self._items[sku]
        except KeyError:
            raise KeyError(f"unknown sku {sku}") from None

    def items(self) -> list[Item]:
        return sorted(self._items.values(), key=lambda i: i.sku)

    # -------------------------------------------------------------- movements
    def receive(self, sku: str, quantity: int, on: date, reason: str = "receipt") -> None:
        if quantity <= 0:
            raise ValueError("receipt quantity must be positive")
        self.item(sku).on_hand += quantity
        self._ledger.append(Movement(sku, quantity, on, reason))

    def issue(self, sku: str, quantity: int, on: date, reason: str = "issue") -> None:
        if quantity <= 0:
            raise ValueError("issue quantity must be positive")
        item = self.item(sku)
        if quantity > item.on_hand:
            raise ValueError(f"insufficient stock for {sku}: {item.on_hand} < {quantity}")
        item.on_hand -= quantity
        self._ledger.append(Movement(sku, -quantity, on, reason))

    def movements(self, sku: str | None = None) -> list[Movement]:
        return [m for m in self._ledger if sku is None or m.sku == sku]

    def average_daily_usage(self, sku: str, days: int, today: date) -> float:
        """Average units issued per day over the trailing ``days`` window."""
        if days <= 0:
            raise ValueError("days must be positive")
        start = today - timedelta(days=days)
        issued = sum(-m.quantity for m in self.movements(sku) if m.quantity < 0 and start < m.on <= today)
        return issued / days

    # -------------------------------------------------------------- reporting
    def total_value(self) -> float:
        return round(sum(i.stock_value() for i in self._items.values()), 2)

    def items_to_reorder(self) -> list[Item]:
        """Items whose on-hand stock is at or below the reorder point (excluding discontinued)."""
        return [
            item
            for item in self.items()
            if not item.is_discontinued() and item.on_hand > item.reorder_point
        ]

    def purchase_orders(self, today: date) -> dict[str, dict]:
        """Group reorder lines by supplier, respecting each supplier's minimum order value."""
        orders: dict[str, dict] = {}
        for item in self.items_to_reorder():
            supplier = self._suppliers[item.supplier_id]
            order = orders.setdefault(
                supplier.supplier_id,
                {"supplier": supplier.name, "lines": [], "value": 0.0,
                 "expected": supplier.expected_delivery(today)},
            )
            line_value = round(item.reorder_quantity * item.unit_cost, 2)
            order["lines"].append({"sku": item.sku, "quantity": item.reorder_quantity, "value": line_value})
            order["value"] = round(order["value"] + line_value, 2)
        return {
            sid: order
            for sid, order in orders.items()
            if order["value"] >= self._suppliers[sid].min_order_value
        }

    def days_of_cover(self, sku: str, today: date, window_days: int = 30) -> float | None:
        """How many days current stock lasts at recent usage; ``None`` if there is no usage."""
        usage = self.average_daily_usage(sku, window_days, today)
        if usage == 0:
            return None
        return round(self.item(sku).on_hand / usage, 1)

    def report_lines(self, today: date) -> list[str]:
        """Human-readable report, one line per item."""
        lines = []
        reorder = {i.sku for i in self.items_to_reorder()}
        for item in self.items():
            cover = self.days_of_cover(item.sku, today)
            cover_text = "n/a" if cover is None else f"{cover:.1f}d"
            flag = "REORDER" if item.sku in reorder else "ok"
            lines.append(f"{item.sku:<8} {item.on_hand:>5} {cover_text:>7} {flag}")
        return lines


def load_items(inventory: Inventory, rows: Iterable[dict]) -> int:
    """Bulk-load items from dictionaries; returns the number of items added."""
    count = 0
    for row in rows:
        inventory.add_item(
            Item(
                sku=row["sku"],
                description=row.get("description", ""),
                on_hand=int(row["on_hand"]),
                reorder_point=int(row["reorder_point"]),
                reorder_quantity=int(row["reorder_quantity"]),
                unit_cost=float(row["unit_cost"]),
                supplier_id=row["supplier_id"],
                tags=set(row.get("tags", ())),
            )
        )
        count += 1
    return count
