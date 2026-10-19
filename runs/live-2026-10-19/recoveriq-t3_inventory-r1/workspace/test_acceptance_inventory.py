from datetime import date

from inventory import Inventory, Item, Supplier


def test_acceptance_report_flags():
    inv = Inventory()
    inv.add_supplier(Supplier("S1", "Acme", lead_time_days=2))
    inv.add_item(Item("B1", "x", on_hand=3, reorder_point=3, reorder_quantity=1, unit_cost=1.0, supplier_id="S1"))
    inv.add_item(Item("B2", "y", on_hand=4, reorder_point=3, reorder_quantity=1, unit_cost=1.0, supplier_id="S1"))
    lines = inv.report_lines(date(2026, 1, 1))
    assert lines[0].endswith("REORDER") and lines[1].endswith("ok")
