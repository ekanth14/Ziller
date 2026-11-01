"""Sizing and order validation remain independent of model confidence."""
import time
from cryptoscope.agents.schemas import number


def validate(proposal, snapshot, portfolio, quote, config, now=None):
    now = time.time() if now is None else now
    reasons = []
    quantity = 0.0
    if proposal.symbol not in config["symbols"]:
        reasons.append("SYMBOL_NOT_ALLOWED")
    if not 0 <= now - snapshot.as_of <= config["max_snapshot_age_seconds"]:
        reasons.append("STALE_OR_FUTURE_SNAPSHOT")
    if not now < proposal.expires_at <= snapshot.as_of + 86400:
        reasons.append("EXPIRED_OR_EXCESSIVE_TTL")
    if proposal.action in {"HOLD", "NO_TRADE"}:
        return {"approved": False, "reasons": reasons + ["NO_ORDER"], "quantity": 0}
    if proposal.action == "SHORT":
        reasons.append("SPOT_SHORT_NOT_SUPPORTED")
    try:
        bid = number(quote.get("bid"), "bid", 0.00000001)
        ask = number(quote.get("ask"), "ask", 0.00000001)
        stamp = number(quote.get("available_at"), "quote time", 1)
        if ask < bid or quote.get("symbol") != proposal.symbol:
            raise ValueError("quote mismatch")
        if not 0 <= now - stamp <= config["max_quote_age_seconds"]:
            reasons.append("STALE_OR_FUTURE_QUOTE")
    except (ValueError, TypeError, AttributeError):
        return {"approved": False, "reasons": reasons + ["INVALID_QUOTE"], "quantity": 0}
    cash = number(portfolio["cash"], "cash")
    positions = portfolio["positions"]
    position = positions.get(proposal.symbol)
    if proposal.action == "LONG":
        if position:
            reasons.append("POSITION_ALREADY_OPEN")
        if positions:
            reasons.append("SINGLE_POSITION_MVP_LIMIT")
        fill = ask * (1 + config["slippage_fraction"])
        if abs(fill / proposal.entry - 1) > 0.002:
            reasons.append("ENTRY_DRIFT_EXCEEDED")
        if not proposal.stop < fill < proposal.target:
            reasons.append("INVALID_LONG_LEVELS")
        else:
            fees = config["fee_fraction"]
            exit_stop = proposal.stop * (1 - config["slippage_fraction"])
            loss = fill - exit_stop + fees * (fill + exit_stop)
            exit_target = proposal.target * (1 - config["slippage_fraction"])
            reward = exit_target - fill - fees * (fill + exit_target)
            if reward / loss < config["minimum_reward_risk"]:
                reasons.append("INSUFFICIENT_NET_REWARD_RISK")
            # With a flat book cash equals equity; one open position is allowed.
            quantity = min(cash * config["risk_fraction"] / loss,
                           cash * config["max_position_fraction"] / fill,
                           cash / (fill * (1 + fees)))
            if quantity <= 0:
                reasons.append("INSUFFICIENT_CASH")
    elif proposal.action in {"CLOSE", "REDUCE"}:
        if not position:
            reasons.append("NO_POSITION_TO_CLOSE")
        else:
            quantity = position["quantity"] * (proposal.reduce_fraction if proposal.action == "REDUCE" else 1)
    return {"approved": not reasons, "reasons": reasons, "quantity": 0 if reasons else quantity}
