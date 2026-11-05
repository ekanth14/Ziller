"""Exact-input recorded debate replay; missing or invalid entries reject.

Heuristic mode is an explicitly named diagnostic, never a recorded model vote.
Cache creation/model generation is deliberately outside this module.
"""
import hashlib
import json
import math
from collections import Counter


def debate_key(symbol, direction, entry, stop, target, indicators):
    payload = dict(schema=1, symbol=symbol, direction=direction, entry=entry,
                   stop=stop, target=target, indicators=indicators)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                                     separators=(',', ':')).encode()).hexdigest()


class RecordedDebateEngine:
    def __init__(self, records=None, mode='recorded'):
        if mode not in {'recorded', 'heuristic_diagnostic'}:
            raise ValueError('Unknown offline debate mode')
        self.records = records or {}
        self.mode = mode
        self.counts = Counter()
        self.keys = []

    def deliberate_combined(self, *, symbol, direction, entry, stop, target,
                           indicators, timeout_sec):
        key = debate_key(symbol, direction, entry, stop, target, indicators)
        self.keys.append(key)
        record = self.records.get(key)
        if record is not None:
            if not isinstance(record,dict):
                self.counts['invalid_cache'] += 1
                return self._reject('Invalid recorded debate')
            score = record.get('conviction_score')
            valid = (
                record.get('source') == 'recorded_model'
                and isinstance(record.get('model'),str) and bool(record['model'].strip())
                and not record.get('fallback_used',False)
                and record.get('verdict') in {'APPROVE', 'REJECT'}
                and isinstance(score, (int, float)) and not isinstance(score, bool)
                and math.isfinite(score) and 0 <= score <= 10
                and isinstance(record.get('latency_ms'), (int, float))
                and not isinstance(record['latency_ms'],bool)
                and math.isfinite(record['latency_ms']) and 0 <= record['latency_ms'] <= timeout_sec * 1000
            )
            self.counts['cached' if valid else 'invalid_cache'] += 1
            if valid:
                return dict(record, fallback_used=False)
            return self._reject('Invalid recorded debate')
        if self.mode == 'heuristic_diagnostic':
            self.counts['heuristic'] += 1
            reward_risk = abs(target-entry) / abs(entry-stop) if entry != stop else 0
            return dict(verdict='APPROVE' if reward_risk >= 1 else 'REJECT',
                        conviction_score=6.0, fallback_used=True,
                        reason='Heuristic reward/risk diagnostic; not a model decision')
        self.counts['cache_miss'] += 1
        return self._reject('No exact recorded debate; STAND_ASIDE')

    @staticmethod
    def _reject(reason):
        return dict(verdict='REJECT', conviction_score=0.0,
                    fallback_used=True, reason=reason)
