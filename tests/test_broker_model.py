from agents.python.broker_model import BrokerModel


def test_slippage_buy_increases_price():
    broker = BrokerModel(slippage_pct=0.001)
    assert broker.apply_slippage(100.0, "buy") == 100.10


def test_slippage_sell_decreases_price():
    broker = BrokerModel(slippage_pct=0.001)
    assert broker.apply_slippage(100.0, "sell") == 99.90


def test_commission_respects_minimum():
    broker = BrokerModel(commission_per_share=0.005, commission_min=1.0)
    assert broker.commission(10, 100.0) == 1.0


def test_commission_respects_maximum():
    broker = BrokerModel(commission_per_share=0.005, commission_max=10.0)
    assert broker.commission(10000, 100.0) == 10.0


def test_commission_scales_with_shares():
    broker = BrokerModel(commission_per_share=0.01, commission_min=0, commission_max=100)
    assert broker.commission(1000, 100.0) == 10.0


def test_total_buy_cost_includes_slippage_and_commission():
    broker = BrokerModel(slippage_pct=0.001, commission_per_share=0.005, commission_min=1.0)
    exec_price, commission, total = broker.total_buy_cost(10, 100.0)

    assert exec_price == 100.10
    assert commission == 1.0
    assert total == 10 * 100.10 + 1.0


def test_total_sell_proceeds():
    broker = BrokerModel(slippage_pct=0.001, commission_per_share=0.005, commission_min=1.0)
    exec_price, commission, proceeds = broker.total_sell_proceeds(10, 100.0)

    assert exec_price == 99.90
    assert commission == 1.0
    assert proceeds == 10 * 99.90 - 1.0
