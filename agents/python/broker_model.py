from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrokerModel:
    slippage_pct: float = 0.0005
    commission_per_share: float = 0.005
    commission_min: float = 1.0
    commission_max: float = 10.0

    def apply_slippage(self, price: float, side: str) -> float:
        if side == "buy":
            return round(price * (1 + self.slippage_pct), 2)
        return round(price * (1 - self.slippage_pct), 2)

    def commission(self, qty: int, price: float) -> float:
        raw = qty * self.commission_per_share
        return round(max(self.commission_min, min(self.commission_max, raw)), 2)

    def total_buy_cost(self, qty: int, price: float) -> tuple[float, float, float]:
        exec_price = self.apply_slippage(price, "buy")
        comm = self.commission(qty, exec_price)
        total = qty * exec_price + comm
        return exec_price, comm, total

    def total_sell_proceeds(self, qty: int, price: float) -> tuple[float, float, float]:
        exec_price = self.apply_slippage(price, "sell")
        comm = self.commission(qty, exec_price)
        proceeds = qty * exec_price - comm
        return exec_price, comm, proceeds


DEFAULT_BROKER = BrokerModel()


def get_broker() -> BrokerModel:
    return DEFAULT_BROKER
