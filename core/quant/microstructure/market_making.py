"""Avellaneda-Stoikov Pure Market Making Model.

Implements inventory-skewed quoting, reservation pricing, and dynamic order sizing,
inspired by hummingbot's pure market making engine and Avellaneda & Stoikov (2008).
"""

import math
from typing import Any, Mapping


def compute_reservation_price(
    mid_price: float,
    inventory: float,
    gamma: float,
    volatility: float,
    time_horizon: float = 1.0,
) -> float:
    """Calculate the Avellaneda-Stoikov reservation (indifference) price.

    Formula:
        r(s, q, t) = s - q * gamma * sigma^2 * (T - t)

    Parameters:
        mid_price: Current mid price (s > 0)
        inventory: Current net inventory (q, base asset units; positive=long, negative=short)
        gamma: Risk aversion parameter (gamma > 0)
        volatility: Asset price volatility (sigma >= 0)
        time_horizon: Remaining time to session horizon (T - t >= 0)
    """
    if mid_price <= 0.0:
        raise ValueError("mid_price must be positive")
    if gamma <= 0.0:
        raise ValueError("gamma must be positive")

    remaining_time = max(0.0, float(time_horizon))
    variance = float(volatility) ** 2
    skew = float(inventory) * float(gamma) * variance * remaining_time
    return float(mid_price) - skew


def compute_optimal_spread(
    gamma: float,
    volatility: float,
    kappa: float,
    time_horizon: float = 1.0,
) -> float:
    """Calculate the Avellaneda-Stoikov optimal bid-ask spread.

    Formula:
        s*(t) = delta^a + delta^b = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / kappa)

    Parameters:
        gamma: Risk aversion parameter (gamma > 0)
        volatility: Asset price volatility (sigma >= 0)
        kappa: Order book liquidity / arrival intensity parameter (kappa > 0)
        time_horizon: Remaining time to session horizon (T - t >= 0)
    """
    if gamma <= 0.0:
        raise ValueError("gamma must be positive")
    if kappa <= 0.0:
        raise ValueError("kappa must be positive")

    remaining_time = max(0.0, float(time_horizon))
    variance = float(volatility) ** 2
    spread = (
        gamma * variance * remaining_time
        + (2.0 / gamma) * math.log(1.0 + (gamma / kappa))
    )
    return max(1e-6, spread)


def compute_avellaneda_stoikov_quotes(
    mid_price: float,
    inventory: float,
    gamma: float,
    volatility: float,
    kappa: float,
    time_horizon: float = 1.0,
    min_spread: float = 0.0,
) -> dict[str, float]:
    """Compute symmetric or inventory-skewed Avellaneda-Stoikov bid and ask prices.

    r = reservation_price
    half_spread = optimal_spread / 2
    bid = r - half_spread
    ask = r + half_spread
    """
    r = compute_reservation_price(
        mid_price=mid_price,
        inventory=inventory,
        gamma=gamma,
        volatility=volatility,
        time_horizon=time_horizon,
    )
    spread = compute_optimal_spread(
        gamma=gamma,
        volatility=volatility,
        kappa=kappa,
        time_horizon=time_horizon,
    )
    if min_spread > 0.0:
        spread = max(spread, min_spread)

    half_spread = spread / 2.0
    bid_price = max(0.01, r - half_spread)
    ask_price = r + half_spread

    # Ensure ask is strictly greater than bid
    if ask_price <= bid_price:
        ask_price = bid_price + max(0.01, min_spread)

    return {
        "reservation_price": r,
        "optimal_spread": spread,
        "half_spread": half_spread,
        "bid_price": bid_price,
        "ask_price": ask_price,
        "bid_distance": mid_price - bid_price,
        "ask_distance": ask_price - mid_price,
    }


def compute_inventory_skewed_sizes(
    target_order_size: float,
    inventory: float,
    max_inventory: float,
    min_order_size: float = 0.0,
) -> tuple[float, float]:
    """Calculate inventory-skewed quoting sizes for bid and ask sides.

    When long (q > 0): reduces bid size, increases ask size.
    When short (q < 0): increases bid size, reduces ask size.
    """
    if target_order_size <= 0.0:
        return (0.0, 0.0)
    if max_inventory <= 0.0:
        return (target_order_size, target_order_size)

    inv_ratio = max(-1.0, min(1.0, float(inventory) / float(max_inventory)))

    # bid size scales down with positive inventory ratio
    bid_size = target_order_size * (1.0 - inv_ratio)
    # ask size scales up with positive inventory ratio
    ask_size = target_order_size * (1.0 + inv_ratio)

    bid_size = max(min_order_size, min(2.0 * target_order_size, bid_size))
    ask_size = max(min_order_size, min(2.0 * target_order_size, ask_size))

    return (bid_size, ask_size)


class AvellanedaStoikovMarketMaker:
    """Stateful Avellaneda-Stoikov Market Maker engine (Hummingbot PMM style)."""

    def __init__(
        self,
        gamma: float = 0.1,
        kappa: float = 1.5,
        time_horizon: float = 1.0,
        max_inventory: float = 10.0,
        target_order_size: float = 1.0,
        min_spread: float = 0.0001,
        min_order_size: float = 0.0,
    ) -> None:
        self.gamma = gamma
        self.kappa = kappa
        self.time_horizon = time_horizon
        self.max_inventory = max_inventory
        self.target_order_size = target_order_size
        self.min_spread = min_spread
        self.min_order_size = min_order_size
        self._inventory: float = 0.0

    @property
    def inventory(self) -> float:
        return self._inventory

    def set_inventory(self, q: float) -> None:
        self._inventory = float(q)

    def update_inventory(self, delta_q: float) -> float:
        self._inventory += float(delta_q)
        return self._inventory

    def compute_quotes(
        self,
        mid_price: float,
        volatility: float,
        current_time: float = 0.0,
    ) -> dict[str, Any]:
        """Compute current bid/ask prices and sizes based on current inventory."""
        remaining_time = max(0.0001, self.time_horizon - current_time)

        quote_prices = compute_avellaneda_stoikov_quotes(
            mid_price=mid_price,
            inventory=self._inventory,
            gamma=self.gamma,
            volatility=volatility,
            kappa=self.kappa,
            time_horizon=remaining_time,
            min_spread=self.min_spread,
        )

        bid_sz, ask_sz = compute_inventory_skewed_sizes(
            target_order_size=self.target_order_size,
            inventory=self._inventory,
            max_inventory=self.max_inventory,
            min_order_size=self.min_order_size,
        )

        return {
            "mid_price": mid_price,
            "inventory": self._inventory,
            "reservation_price": quote_prices["reservation_price"],
            "optimal_spread": quote_prices["optimal_spread"],
            "bid_price": quote_prices["bid_price"],
            "ask_price": quote_prices["ask_price"],
            "bid_size": bid_sz,
            "ask_size": ask_sz,
            "inventory_ratio": (self._inventory / self.max_inventory) if self.max_inventory > 0 else 0.0,
        }
