"""Which symbols the autotrader may trade.

The operator excluded BTC, ETH and SOL from autotrading. Override with the environment variable
ZILLERS_EXCLUDE_SYMBOLS (comma or space separated, e.g. "BTCUSDT,ETHUSDT"); set it to "none" to
exclude nothing. The desk, charts, markets page and Strategy Lab still show every coin; this list
only controls what the scanner may pick and what the fleet may start on.
"""
from __future__ import annotations

import os
import re
from typing import FrozenSet, Iterable, List, Tuple

DEFAULT_EXCLUDED: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def excluded_symbols() -> FrozenSet[str]:
    raw = os.environ.get("ZILLERS_EXCLUDE_SYMBOLS")
    if raw is None:
        return frozenset(DEFAULT_EXCLUDED)
    if raw.strip().lower() in {"", "none"}:
        return frozenset()
    return frozenset(s.upper() for s in re.split(r"[\s,]+", raw.strip()) if s)


def filter_symbols(symbols: Iterable[str]) -> Tuple[List[str], List[str]]:
    """Split symbols into (allowed, excluded), keeping order and dropping duplicates."""
    blocked = excluded_symbols()
    kept, dropped, seen = [], [], set()
    for s in symbols:
        s = str(s).upper()
        if s in seen:
            continue
        seen.add(s)
        (dropped if s in blocked else kept).append(s)
    return kept, dropped
