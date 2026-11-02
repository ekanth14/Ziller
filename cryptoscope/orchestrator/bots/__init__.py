"""Individual specialized trading micro-bots for the ZILLERS autonomous fleet."""

from cryptoscope.orchestrator.bots.supervisor_bot import SupervisorBot
from cryptoscope.orchestrator.bots.data_bot import DataBot
from cryptoscope.orchestrator.bots.analyst_bot import AnalystBot
from cryptoscope.orchestrator.bots.quant_bot import QuantBot
from cryptoscope.orchestrator.bots.strategy_bot import StrategyBot
from cryptoscope.orchestrator.bots.debate_bot import DebateBot
from cryptoscope.orchestrator.bots.risk_bot import RiskBot
from cryptoscope.orchestrator.bots.execution_bot import ExecutionBot

__all__ = [
    "SupervisorBot",
    "DataBot",
    "AnalystBot",
    "QuantBot",
    "StrategyBot",
    "DebateBot",
    "RiskBot",
    "ExecutionBot",
]
