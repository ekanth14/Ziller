"""The fleet's LLM debate must get its full configured deadline (CPU Gemma 12B needs ~60-100 s)."""
import asyncio
from unittest.mock import patch

import pytest

from cryptoscope.agents.consensus import DeliberationConsensusEngine
from cryptoscope.orchestrator.bots.debate_bot import DebateBot
from cryptoscope.orchestrator.event_bus import EventBus
from cryptoscope.orchestrator.events import DebateResult, RiskPreApproved
from cryptoscope.providers import deadline_http
from cryptoscope.providers.deadline_http import post_json_deadline

APPROVE = {"done": True, "done_reason": "stop",
           "response": '{"bull_thesis":"trend up","bear_thesis":"tight stop","risk_verdict":"APPROVE",'
                       '"conviction":8,"consensus_action":"BUY","reason":"aligned"}'}


def test_consensus_passes_the_callers_full_deadline():
    with patch("cryptoscope.agents.consensus.post_json_deadline", return_value=APPROVE) as call:
        r = DeliberationConsensusEngine().deliberate_combined("ADAUSDT", "BUY", 1.0, 0.98, 1.04, model="m", timeout_sec=180)
    assert call.call_args.args[2] == 180          # no hidden 35 s cap
    assert r["verdict"] == "APPROVE" and r["conviction_score"] == 8 and not r["fallback_used"]


def test_deadline_bounds():
    assert deadline_http.MAX_DEADLINE_SEC >= 180
    for bad in (0, -1, float("nan"), deadline_http.MAX_DEADLINE_SEC + 1):
        with pytest.raises(ValueError):
            post_json_deadline("http://127.0.0.1:11434/api/generate", {}, bad)


def _pre(i, sym="ADAUSDT"):
    return RiskPreApproved(intent_id=f"i{i}", symbol=sym, direction="BUY", entry_price=1.0, stop_loss=0.98,
                           take_profit=1.04, strategy_id="t")


def test_debate_skips_instead_of_queueing_while_busy():
    async def run():
        bot = DebateBot(EventBus(), timeout_seconds=5)
        out = []

        async def emit(ev):
            out.append(ev)
        bot.emit = emit
        started = asyncio.Event()

        def slow(**_):
            started.set()
            import time
            time.sleep(0.3)
            return {"verdict": "APPROVE", "conviction_score": 7, "bull_thesis": "", "bear_thesis": "", "reason": "", "fallback_used": False}
        bot.deliberation_engine.deliberate_combined = slow
        first = asyncio.create_task(bot._deliberate_pre_approved(_pre(1)))
        while not bot._busy.locked():
            await asyncio.sleep(0.01)
        await bot._deliberate_pre_approved(_pre(2, "XRPUSDT"))
        await first
        return bot, out

    bot, out = asyncio.run(run())
    by_id = {e.intent_id: e for e in out if isinstance(e, DebateResult)}
    assert by_id["i2"].verdict == "REJECT" and "DEBATE_BUSY" in by_id["i2"].risk_summary
    assert by_id["i1"].verdict == "APPROVE"
    assert bot.skipped_busy_count == 1 and bot.get_health_details()["skipped_busy"] == 1
