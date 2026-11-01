"""Read the existing research ledgers without creating or migrating databases."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
from cryptoscope.providers.laya import LayaProvider


class DashboardData:
    def __init__(self, root, config):
        self.root, self.config = Path(root), config
        self.health = {"status": "unchecked", "model": LayaProvider(config).model}
        self.checked_at = 0
        self.health_lock = threading.Lock()

    def directories(self, workspace):
        if workspace not in {"research", "demo"}:
            raise ValueError("Unknown workspace")
        base = self.root / "work" / ("research-agent" if workspace == "research" else "research-demo")
        paths = [base] if (base / "research.sqlite3").exists() else []
        if workspace == "demo" and base.exists():
            paths += [p.parent for p in base.glob("*/research.sqlite3")]
        return sorted(paths, key=lambda p: (p / "research.sqlite3").stat().st_mtime, reverse=True)

    @staticmethod
    def query(path, sql, params=()):
        if not path.exists():
            return []
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            return db.execute(sql, params).fetchall()

    def runs(self, workspace):
        bodies, errors = {}, []
        for directory in self.directories(workspace):
            try:
                for row in self.query(directory / "research.sqlite3", "SELECT body FROM runs ORDER BY created DESC LIMIT 100"):
                    body = json.loads(row[0])
                    bodies[body["run_id"]] = body
            except (sqlite3.Error, ValueError, KeyError):
                errors.append("A research ledger could not be read.")
        return sorted(bodies.values(), key=lambda r: r["created_at"], reverse=True)[:100], errors

    def run(self, workspace, run_id):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid run ID")
        for directory in self.directories(workspace):
            rows = self.query(directory / "research.sqlite3", "SELECT body FROM runs WHERE id=?", (run_id,))
            if rows:
                return json.loads(rows[0][0])
        return None

    @staticmethod
    def summary(body):
        decision = body.get("decision") or {}
        proposal = decision.get("proposal", {})
        return {"run_id": body["run_id"], "created_at": body["created_at"],
                "finished_at": body.get("finished_at"), "status": body["status"],
                "symbol": body.get("snapshot", {}).get("symbol", "—"), "model": body.get("model"),
                "mode": body.get("mode"), "action": proposal.get("action"),
                "confidence": proposal.get("confidence"), "error": body.get("error"),
                "execution": body.get("execution", {}),
                "stages": [s["name"] for s in body.get("stages", [])]}

    def model_health(self):
        if time.time() - self.checked_at < 30:
            return self.health
        with self.health_lock:
            if time.time() - self.checked_at < 30:
                return self.health
            provider = LayaProvider(self.config)
            try:
                available = provider.model in provider.models()
                self.health = {"status": "ready" if available else "model_missing", "model": provider.model}
            except Exception as error:
                delayed=isinstance(error,TimeoutError) or isinstance(getattr(error,'reason',None),TimeoutError)
                self.health = {"status": "check_delayed" if delayed else "unreachable", "model": provider.model}
            self.checked_at = time.time()
            return self.health

    def overview(self, workspace):
        bodies, errors = self.runs(workspace)
        directories = self.directories(workspace)
        portfolio, fills = {"cash": None, "positions": {}}, []
        controls = {'halted': False, 'reason': '', 'changed_at': None}
        if directories:
            path = directories[0] / "paper.sqlite3"
            try:
                rows = self.query(path, "SELECT cash FROM account WHERE id=1")
                if rows:
                    portfolio["cash"] = rows[0][0]
                    portfolio["positions"] = {r[0]: {"quantity": r[1], "entry": r[2], "stop": r[3], "target": r[4]}
                                              for r in self.query(path, "SELECT * FROM positions")}
                    fills = [json.loads(r[0]) for r in self.query(path, "SELECT body FROM fills ORDER BY rowid DESC LIMIT 20")]
                    if self.query(path, "SELECT name FROM sqlite_master WHERE type='table' AND name='controls'"):
                        row = self.query(path, 'SELECT halted,reason,changed FROM controls WHERE id=1')
                        if row:
                            controls = {'halted': bool(row[0][0]), 'reason': row[0][1], 'changed_at': row[0][2]}
            except (sqlite3.Error, ValueError):
                errors.append("The paper ledger could not be read.")
        snapshots = {}
        for body in bodies:
            snapshot = body.get("snapshot", {})
            if snapshot.get("symbol") not in snapshots and snapshot.get("candles"):
                snapshots[snapshot["symbol"]] = snapshot
        return {"workspace": workspace, "server_time": time.time(), "model": self.model_health(),
                'autotrader':self.autotrader() if workspace=='research' else None,
                'forecast': self.latest_forecast(workspace, bodies), 'strategy': self.latest_strategy(workspace),
                "backtests": self.backtests(workspace), "risk_reports": self.risk_reports(workspace),
                "portfolio": portfolio, "controls": controls, "fills": fills, "runs": [self.summary(b) for b in bodies],
                "snapshots": snapshots, "errors": errors,
                "settings": {key: self.config[key] for key in ("symbols", "interval", "risk_fraction", "max_position_fraction", "minimum_reward_risk")},
                "ledger_label": "Latest demo session" if workspace == "demo" else "Paper research account"}

    def backtest(self, run_id):
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise ValueError('Invalid backtest ID')
        path = self.root/'reports/backtests'/run_id/'report.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

    def backtests(self, workspace):
        result = []
        paths = sorted((self.root/'reports/backtests').glob('*/report.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:100]:
            try:
                body = json.loads(path.read_text(encoding='utf-8'))
                is_demo = body.get('source') == 'synthetic_demo'
                if is_demo != (workspace == 'demo'):
                    continue
                result.append({key: body.get(key) for key in ('run_id','created_at','strategy','symbol','source','metrics','fingerprint')})
            except (ValueError, OSError):
                continue
        return result

    def risk_reports(self, workspace):
        for summary in self.backtests(workspace):
            body = self.backtest(summary['run_id'])
            risk = body.get('risk') or {}
            if risk.get('status') == 'completed':
                return {'status': 'available', 'source': 'backtest', 'run_id': summary['run_id'],
                        'symbol': summary['symbol'], 'created_at': summary['created_at'], 'report': risk}
        return {'status': 'unavailable', 'reason': 'Run a baseline backtest to calculate risk from its equity series.'}

    def feature_catalog(self):
        path = self.root/'config/features.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'features': [], 'repositories': []}

    def autotrader(self):
        path=self.root/'work/autotrader/autotrader.sqlite3'
        if not path.is_file():
            return {'available':False,'runtime':{'state':'not_started'},'decisions':[],'fills':[]}
        rows=self.query(path,'SELECT body FROM runtime WHERE id=1')
        runtime=json.loads(rows[0][0]) if rows else {'state':'stopped'}
        if runtime.get('state') in {'running','stopping'} and time.time()-runtime.get('heartbeat_at',0)>90:
            runtime={**runtime,'state':'heartbeat_overdue'}
        decisions=[]
        for row in self.query(path,'SELECT body FROM decisions ORDER BY created DESC LIMIT 12'):
            body=json.loads(row[0])
            decisions.append({k:body.get(k) for k in ('run_id','created_at','finished_at','symbol','status',
                'decision','decision_source','execution','latency_seconds','error')})
        fills=[json.loads(row[0]) for row in self.query(self.root/'work/autotrader/paper.sqlite3',
               'SELECT body FROM fills ORDER BY rowid DESC LIMIT 12')]
        return {'available':True,'runtime':runtime,'decisions':decisions,'fills':fills}

    def autotrader_run(self,run_id):
        if not re.fullmatch(r'[a-f0-9]{32}',run_id):
            raise ValueError('Invalid autonomous decision ID')
        rows=self.query(self.root/'work/autotrader/autotrader.sqlite3','SELECT body FROM decisions WHERE id=?',(run_id,))
        return json.loads(rows[0][0]) if rows else None

    def artifact(self, kind, run_id):
        if kind not in {'forecasts','strategies'} or not re.fullmatch(r'[a-f0-9]{32}',run_id):
            raise ValueError('Invalid research artifact')
        path=self.root/'reports'/kind/run_id/'report.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

    def artifacts(self, kind):
        if kind not in {'forecasts','strategies'}:
            raise ValueError('Unknown artifact kind')
        paths=sorted((self.root/'reports'/kind).glob('*/report.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        for path in paths[:100]:
            if not re.fullmatch(r'[a-f0-9]{32}',path.parent.name):
                continue
            try:
                body=json.loads(path.read_text(encoding='utf-8'))
                if isinstance(body,dict):
                    yield {**body,'run_id':path.parent.name}
            except (ValueError,OSError):
                continue

    def forecast_report(self, workspace, run_id):
        report=self.artifact('forecasts',run_id)
        if report is None:
            body=self.run(workspace,run_id)
            report=body.get('forecast') if body else None
        return report

    def latest_forecast(self, workspace, bodies):
        reports=[{**b['forecast'],'run_id':b['run_id']} for b in bodies if b.get('forecast')]
        reports.extend(r for r in self.artifacts('forecasts') if (r.get('source')=='synthetic_demo')==(workspace=='demo'))
        if not reports:
            return None
        report=max(reports,key=lambda r:r.get('available_at',0))
        return {k:report.get(k) for k in ('run_id','symbol','model','input_cutoff','available_at','parameters','forecast')}

    def latest_strategy(self, workspace):
        if workspace!='research':
            return None
        body=next(self.artifacts('strategies'),None)
        if body is None:
            return None
        result={k:body.get(k) for k in ('run_id','created_at','model','spec','status')}
        for summary in self.backtests('research'):
            report=self.backtest(summary['run_id'])
            if report.get('strategy_spec')==body.get('spec'):
                result['backtest']=summary
                break
        return result
