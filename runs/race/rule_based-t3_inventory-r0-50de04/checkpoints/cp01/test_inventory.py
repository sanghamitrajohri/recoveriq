from datetime import date

import pytest

from inventory import Inventory, Item, Supplier


@pytest.fixture
def inv():
    inv = Inventory()
    inv.add_supplier(Supplier("S1", "Acme", lead_time_days=5, min_order_value=10))
    inv.add_item(Item("A1", "bolts", on_hand=5, reorder_point=10, reorder_quantity=50, unit_cost=0.5, supplier_id="S1"))
    inv.add_item(Item("A2", "nuts", on_hand=10, reorder_point=10, reorder_quantity=40, unit_cost=0.25, supplier_id="S1"))
    inv.add_item(Item("A3", "gears", on_hand=99, reorder_point=10, reorder_quantity=5, unit_cost=4.0, supplier_id="S1"))
    inv.add_item(Item("A4", "old", on_hand=0, reorder_point=10, reorder_quantity=5, unit_cost=1.0,
                      supplier_id="S1", tags={"discontinued"}))
    return inv


def test_reorder_includes_items_at_or_below_point(inv):
    assert [i.sku for i in inv.items_to_reorder()] == ["A1", "A2"]


def test_purchase_order_value(inv):
    orders = inv.purchase_orders(date(2026, 1, 1))
    assert orders["S1"]["value"] == 35.0
    assert orders["S1"]["expected"] == date(2026, 1, 6)


def test_issue_insufficient(inv):
    with pytest.raises(ValueError):
        inv.issue("A1", 6, date(2026, 1, 1))
