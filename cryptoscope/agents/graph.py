"""Bounded research workflow; persist stage outputs and stop on model failure."""
from concurrent.futures import ThreadPoolExecutor
import time
from cryptoscope.agents.analysts.market import technical, derivatives, news
from cryptoscope.agents.researchers.debate import debate
from cryptoscope.agents.schemas import Proposal
from cryptoscope.agents.risk.policy import validate
from cryptoscope.research.reports import write_report


class ResearchGraph:
    def __init__(self, provider, store, broker, config, reports_dir, on_stage=None, forecast_supplier=None):
        self.provider, self.store, self.broker = provider, store, broker
        self.config, self.reports_dir = config, reports_dir
        self.on_stage = on_stage
        self.forecast_supplier = forecast_supplier

    def run(self, snapshot, quote_supplier=None, paper=False):
        first_call = len(self.provider.calls)
        body = self.store.create({"model": self.provider.model, "mode": "paper" if paper else "research",
                                  "snapshot": snapshot.to_dict(), "settings": self.config})

        def stage(name, output):
            body["stages"].append({"name": name, "output": output})
            self.store.save(body)
            if self.on_stage:
                self.on_stage(name)

        try:
            now = time.time()
            if snapshot.symbol not in self.config["symbols"]:
                raise ValueError("symbol is not in configured universe")
            if not 0 <= now - snapshot.as_of <= self.config["max_snapshot_age_seconds"]:
                raise ValueError("snapshot is stale or in the future")
            with ThreadPoolExecutor(max_workers=3) as pool:
                analysts = list(pool.map(lambda fn: fn(snapshot), (technical, derivatives, news)))
            if self.forecast_supplier:
                from cryptoscope.forecasting import evidence
                report = self.forecast_supplier(snapshot)
                analysts.append(evidence(report, snapshot))
                body['forecast'] = report
            stage("analysts", analysts)
            context = {"instrument": {"symbol": snapshot.symbol, "as_of": snapshot.as_of,
                                      "interval_seconds": snapshot.interval_seconds,
                                      "last_closed_candle": snapshot.candles[-1]}, "analysts": analysts,
                       "portfolio": self.broker.portfolio(), "settings": self.config}
            history = debate(self.provider, context)
            stage("research_debate", history)
            context["debate"] = history
            context["output_contract"] = {
                "action": "LONG|SHORT|REDUCE|CLOSE|HOLD|NO_TRADE", "symbol": snapshot.symbol,
                "entry": "positive number or null", "stop": "positive number or null",
                "target": "positive number or null", "confidence": "number 0..1",
                "thesis": "string", "evidence": [a['id'] for a in analysts if a['status'] == 'available'],
                "expires_at": f"Unix seconds > now and <= {snapshot.as_of + 86400}",
                "reduce_fraction": "number > 0 and <= 1"}
            proposal = Proposal.parse(self.provider.complete("trader", context), snapshot.symbol)
            if not set(proposal.evidence) <= {a["id"] for a in analysts if a["status"] == "available"}:
                raise ValueError("proposal cites missing evidence")
            stage("trader", proposal.to_dict())
            risk = []
            for role in ("aggressive_risk", "neutral_risk", "conservative_risk"):
                review = self.provider.complete(role, {"proposal": proposal.to_dict(), "analysts": analysts,
                    "portfolio": self.broker.portfolio(), "output_contract": {"concerns": ["string"], "assessment": "string"}})
                if not isinstance(review.get("assessment"), str) or not isinstance(review.get("concerns"), list):
                    raise ValueError("invalid risk review")
                risk.append({"role": role, "review": review})
                stage(role, review)
            decision = self.provider.complete("portfolio_manager", {"proposal": proposal.to_dict(), "risk": risk,
                "portfolio": self.broker.portfolio(), "analysts": analysts,
                "output_contract": {"approved": "boolean", "reason": "string"}})
            if type(decision.get("approved")) is not bool or not isinstance(decision.get("reason"), str):
                raise ValueError("invalid portfolio manager decision")
            body["decision"] = {**decision, "proposal": proposal.to_dict()}
            stage("portfolio_manager", decision)
            body["execution"] = {"status": "not_requested"}
            if decision["approved"] and proposal.action not in {"HOLD", "NO_TRADE"}:
                if quote_supplier is None:
                    body["execution"] = {"status": "blocked", "reasons": ["FRESH_QUOTE_REQUIRED"]}
                else:
                    quote = quote_supplier(snapshot.symbol)
                    stage("execution_quote", quote)
                    gate = validate(proposal, snapshot, self.broker.portfolio(), quote, self.config)
                    stage("execution_gate", gate)
                    body["execution"] = self.broker.execute(body["run_id"], proposal, snapshot, quote) if paper else {"status": "research_only", **gate}
            elif not decision["approved"]:
                body["execution"] = {"status": "rejected_by_laya"}
            body["status"] = "completed"
        except Exception as error:
            body["status"] = "failed"
            body["error"] = f"{type(error).__name__}: {error}"
        finally:
            body["model_calls"] = self.provider.calls[first_call:]
            body["finished_at"] = time.time()
            self.store.save(body)
            body["report_directory"] = write_report(body, self.reports_dir)
        return body
