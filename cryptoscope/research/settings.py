"""Project-relative settings with environment overrides in the model adapter."""
import json
from pathlib import Path
from cryptoscope.agents.schemas import number
from cryptoscope.providers.binance import INTERVALS

ROOT = Path(__file__).resolve().parents[2]


def load_config(path=None):
    config = json.loads((ROOT / "config/research.json").read_text(encoding="utf-8"))
    if path:
        overrides = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(overrides, dict) or set(overrides) - set(config):
            raise ValueError("config contains unsupported keys")
        config.update(overrides)
    for key in ("risk_fraction", "max_position_fraction", "fee_fraction", "slippage_fraction"):
        if number(config[key], key) >= 1:
            raise ValueError(f"{key} must be less than one")
    for key in ("initial_cash", "minimum_reward_risk", "model_timeout_seconds", "max_snapshot_age_seconds", "max_quote_age_seconds"):
        number(config[key], key, 0.000001)
    tokens = number(config["model_max_output_tokens"], "model_max_output_tokens", 128)
    if tokens != int(tokens) or tokens > 4096 or type(config["model_thinking"]) is not bool:
        raise ValueError("invalid model generation limits")
    if config["interval"] not in INTERVALS or not config["symbols"] or not all(
        isinstance(s, str) and s.isalnum() and s.endswith("USDT") for s in config["symbols"]
    ):
        raise ValueError("invalid interval or USDT universe")
    if not isinstance(config["model"], str) or not config["model"].strip():
        raise ValueError("model is required")
    return config
