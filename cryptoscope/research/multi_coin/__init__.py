"""Multi-Coin Research, Universe Management, Cost Modeling, and Portfolio Risk."""

from cryptoscope.research.multi_coin.candidate_universe import (
    build_candidate_universe,
    fetch_binance_exchange_info,
)
from cryptoscope.research.multi_coin.data_integrity import (
    verify_symbol_integrity,
    audit_all_parquet_klines,
)
from cryptoscope.research.multi_coin.kline_downloader import (
    download_universe_4y,
)
from cryptoscope.research.multi_coin.universe_manager import (
    PointInTimeUniverseManager,
    UniverseConfig,
    UniverseSnapshot,
)
from cryptoscope.research.multi_coin.cost_model import (
    DynamicCostModel,
    CostModelCalibration,
    ExecutionResult,
)
from cryptoscope.research.multi_coin.portfolio_risk import (
    MultiCoinPortfolioRiskManager,
    PortfolioRiskConfig,
    RiskCheckResult,
)

__all__ = [
    "build_candidate_universe",
    "fetch_binance_exchange_info",
    "verify_symbol_integrity",
    "audit_all_parquet_klines",
    "download_universe_4y",
    "PointInTimeUniverseManager",
    "UniverseConfig",
    "UniverseSnapshot",
    "DynamicCostModel",
    "CostModelCalibration",
    "ExecutionResult",
    "MultiCoinPortfolioRiskManager",
    "PortfolioRiskConfig",
    "RiskCheckResult",
]
