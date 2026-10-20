import pricing_config
from checkout import order_total


def test_acceptance_store_settings_intact():
    assert pricing_config.TAX_RATE == 0.08


def test_acceptance_cart_at_free_shipping_minimum():
    assert order_total([(19.99, 2), (10.02, 1)]) == 54.0
