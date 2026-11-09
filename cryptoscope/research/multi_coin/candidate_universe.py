"""Point-in-time Candidate Universe of Binance Spot Symbols (Phase 4.1).

Builds candidate list of Binance Spot USDT pairs, tracking active and delisted
instruments to support survivorship-bias-free multi-coin backtesting.
"""

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger("cryptoscope.research.multi_coin.candidate_universe")

BINANCE_SPOT_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"

# Historically prominent delisted spot USDT pairs on Binance
HISTORICAL_DELISTED_SPOT_USDT = [
    "LUNAUSDT",   # Terra Classic collapse
    "FTTUSDT",    # FTX collapse
    "BUSDUSDT",   # Paxos BUSD deprecation
    "SRMUSDT",    # Serum delisting
    "HNTUSDT",    # Helium delisting
    "ANCUSDT",    # Anchor protocol delisting
    "MIRUSDT",    # Mirror protocol delisting
    "BEAMUSDT",   # Beam delisting
    "TOMOUSDT",   # TomoChain delisting
    "WTCUSDT",    # Waltonchain delisting
]

# Stablecoins to flag for universe exclusions in strategy design
STABLECOIN_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "GBP", "AEUR", "EURI"
}


def fetch_binance_exchange_info(timeout: float = 15.0) -> Dict[str, Any]:
    """Fetch official Binance Spot exchange info."""
    req = urllib.request.Request(
        BINANCE_SPOT_EXCHANGE_INFO,
        headers={"User-Agent": "ZILLERS-Research/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_candidate_universe(
    exchange_info: Dict[str, Any] = None,
    include_delisted: bool = True
) -> Dict[str, Any]:
    """Parse exchange info and construct point-in-time candidate universes."""
    if exchange_info is None:
        exchange_info = fetch_binance_exchange_info()

    all_symbols = exchange_info.get("symbols", [])
    
    active_spot_usdt: List[str] = []
    inactive_spot_usdt: List[str] = []
    leveraged_tokens: List[str] = []
    stablecoin_pairs: List[str] = []
    symbol_metadata: Dict[str, Dict[str, Any]] = {}

    for s in all_symbols:
        symbol = s.get("symbol", "")
        quote = s.get("quoteAsset", "")
        base = s.get("baseAsset", "")
        status = s.get("status", "")
        is_spot = "SPOT" in s.get("permissions", []) or s.get("isSpotTradingAllowed", False)

        if quote != "USDT" or not is_spot:
            continue

        meta = {
            "symbol": symbol,
            "base_asset": base,
            "quote_asset": quote,
            "status": status,
            "filters": s.get("filters", []),
        }
        symbol_metadata[symbol] = meta

        # Detect leveraged tokens (e.g. BTCUP, BTCDOWN, ETHBEAR, BULL)
        if any(base.endswith(suffix) for suffix in ("UP", "DOWN", "BULL", "BEAR")):
            leveraged_tokens.append(symbol)
            continue

        # Detect stablecoin to stablecoin pairs
        if base in STABLECOIN_BASES:
            stablecoin_pairs.append(symbol)

        if status == "TRADING":
            active_spot_usdt.append(symbol)
        else:
            inactive_spot_usdt.append(symbol)

    # Merge historical delisted tracking
    historical_delisted_set: Set[str] = set(inactive_spot_usdt)
    if include_delisted:
        for ds in HISTORICAL_DELISTED_SPOT_USDT:
            if ds not in symbol_metadata:
                symbol_metadata[ds] = {
                    "symbol": ds,
                    "base_asset": ds[:-4],
                    "quote_asset": "USDT",
                    "status": "DELISTED",
                    "historical": True
                }
            historical_delisted_set.add(ds)

    # Core high-liquidity benchmark candidates
    core_benchmark_symbols = [
        s for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT"]
        if s in symbol_metadata
    ]

    return {
        "timestamp_server": exchange_info.get("serverTime"),
        "total_spot_usdt_symbols": len(symbol_metadata),
        "active_trading_symbols_count": len(active_spot_usdt),
        "inactive_or_delisted_count": len(historical_delisted_set),
        "leveraged_tokens_count": len(leveraged_tokens),
        "stablecoin_pairs_count": len(stablecoin_pairs),
        "active_trading_symbols": sorted(active_spot_usdt),
        "inactive_or_delisted_symbols": sorted(list(historical_delisted_set)),
        "core_benchmark_symbols": core_benchmark_symbols,
        "leveraged_excluded": sorted(leveraged_tokens),
        "stablecoins_flagged": sorted(stablecoin_pairs),
        "symbols_metadata": symbol_metadata,
    }


def save_candidate_universe(dest_path: Path = None) -> Path:
    """Fetch, build and persist the candidate universe to JSON."""
    if dest_path is None:
        dest_path = Path("data/universe/candidate_spot_usdt.json")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    universe = build_candidate_universe()
    dest_path.write_text(json.dumps(universe, indent=2), encoding="utf-8")
    logger.info(
        "Candidate universe saved: %d total, %d active, %d inactive/delisted",
        universe["total_spot_usdt_symbols"],
        universe["active_trading_symbols_count"],
        universe["inactive_or_delisted_count"]
    )
    return dest_path


if __name__ == "__main__":
    path = save_candidate_universe()
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"Saved candidate universe to {path}")
    print(f"Total Spot USDT symbols: {data['total_spot_usdt_symbols']}")
    print(f"Active Trading: {data['active_trading_symbols_count']}")
    print(f"Inactive / Delisted: {data['inactive_or_delisted_count']}")
    print(f"Core Benchmark Candidates: {data['core_benchmark_symbols']}")
