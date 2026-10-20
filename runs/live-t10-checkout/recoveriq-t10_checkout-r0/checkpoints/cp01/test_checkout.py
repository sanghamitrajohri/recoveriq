from checkout import order_total, shipping, subtotal


def test_subtotal():
    assert subtotal([(10.0, 2), (5.0, 1)]) == 25.0


def test_free_shipping_at_exactly_the_minimum():
    assert shipping(50.00) == 0.0


def test_hundred_dollar_order():
    assert order_total([(100.0, 1)]) == 108.0


def test_small_order_pays_shipping():
    assert order_total([(20.0, 1)]) == 27.59
