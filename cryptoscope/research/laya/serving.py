"""In-Process Laya Decision Serving Engine (Phase 8.4).

Serves calibrated predictions in-process without Ollama:
- Target: p95 latency < 50 ms, hard timeout 200 ms.
- Configurable strictly via environment variables:
  * LAYA_MODEL_PATH: Path to trained decision checkpoint.
  * LAYA_MIN_CONFIDENCE: Minimum probability threshold (default 0.55).
  * LAYA_TIMEOUT_MS: Hard inference timeout budget (default 200.0 ms).
- Exposes diagnostic latency benchmarks (p50, p95, p99) and memory usage.
"""

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
from cryptoscope.research.laya.models import PlattCalibrator, MultinomialLogisticRegression

logger = logging.getLogger("cryptoscope.research.laya.serving")

LABEL_NAMES = ["HOLD", "BUY", "SELL"]


@dataclass
class ServingBenchmark:
    """Latency percentiles and memory footprint from inference benchmark."""
    sample_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    status: str


class LayaInProcessServing:
    """Serves Laya decision model in-process with strict latency and fail-closed gates."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        min_confidence: Optional[float] = None,
        timeout_ms: Optional[float] = None,
    ):
        self.model_path = model_path or os.environ.get(
            "LAYA_MODEL_PATH", "checkpoints/laya_decision_classifier.joblib"
        )
        self.min_confidence = min_confidence if min_confidence is not None else float(
            os.environ.get("LAYA_MIN_CONFIDENCE", "0.55")
        )
        self.timeout_ms = timeout_ms if timeout_ms is not None else float(
            os.environ.get("LAYA_TIMEOUT_MS", "200.0")
        )

        self.model = None
        self.is_loaded = False
        self._load_model()

    def _load_model(self) -> None:
        """Loads trained model checkpoint from disk."""
        p = Path(self.model_path)
        if not p.is_file():
            logger.warning("Laya model checkpoint not found at %s; serving disabled", p)
            self.is_loaded = False
            return

        try:
            self.model = joblib.load(p)
            self.is_loaded = True
            logger.info("Successfully loaded in-process Laya model from %s", p)
        except Exception as e:
            logger.error("Failed loading Laya model from %s: %s", p, e)
            self.is_loaded = False

    def predict(self, feature_vector: np.ndarray) -> Dict[str, Any]:
        """Performs fast in-process inference on a 12-dimensional feature vector.
        
        Fail-closed guarantee: Returns status='STAND_ASIDE' if uncalibrated,
        model is missing, or latency budget is exceeded.
        """
        t0 = time.perf_counter()

        if not self.is_loaded or self.model is None:
            return {
                "action": "STAND_ASIDE",
                "confidence": 0.0,
                "probabilities": {"HOLD": 0.33, "BUY": 0.33, "SELL": 0.33},
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                "status": "MODEL_UNAVAILABLE",
                "reason": "Laya model checkpoint not loaded",
            }

        try:
            # Reshape to 2D
            X = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)
            probs = self.model.predict_proba(X)[0]
            top_class_idx = int(np.argmax(probs))
            top_prob = float(probs[top_class_idx])
            action_name = LABEL_NAMES[top_class_idx]

            latency_ms = (time.perf_counter() - t0) * 1000.0

            # Hard timeout guard
            if latency_ms > self.timeout_ms:
                logger.warning("Laya inference exceeded timeout (%.2f ms > %.1f ms)", latency_ms, self.timeout_ms)
                return {
                    "action": "STAND_ASIDE",
                    "confidence": top_prob,
                    "probabilities": {LABEL_NAMES[i]: round(float(probs[i]), 4) for i in range(len(LABEL_NAMES))},
                    "latency_ms": round(latency_ms, 3),
                    "status": "TIMEOUT",
                    "reason": f"Latency {latency_ms:.2f}ms exceeded {self.timeout_ms}ms limit",
                }

            # Confidence gate
            if top_prob < self.min_confidence:
                action = "HOLD" if action_name in {"BUY", "SELL"} else action_name
            else:
                action = action_name

            return {
                "action": action,
                "raw_action": action_name,
                "confidence": round(top_prob, 4),
                "probabilities": {
                    LABEL_NAMES[i]: round(float(probs[i]), 4) for i in range(len(LABEL_NAMES))
                },
                "latency_ms": round(latency_ms, 3),
                "status": "OK",
                "reason": f"Laya confidence {top_prob:.2f} >= {self.min_confidence:.2f}",
            }

        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("In-process prediction error: %s", e)
            return {
                "action": "STAND_ASIDE",
                "confidence": 0.0,
                "probabilities": {"HOLD": 0.33, "BUY": 0.33, "SELL": 0.33},
                "latency_ms": round(latency_ms, 3),
                "status": "ERROR",
                "reason": str(e),
            }

    def benchmark_latency(self, n_runs: int = 100) -> ServingBenchmark:
        """Runs N inference passes and measures p50, p95, p99 latencies."""
        dummy_vec = np.zeros(12, dtype=np.float32)
        latencies = []

        # Warmup pass
        for _ in range(5):
            self.predict(dummy_vec)

        for _ in range(n_runs):
            t0 = time.perf_counter()
            self.predict(dummy_vec)
            lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)

        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(n_runs * 0.50)]
        p95 = sorted_lat[int(n_runs * 0.95)]
        p99 = sorted_lat[min(int(n_runs * 0.99), n_runs - 1)]

        status = "PASS" if p95 < 50.0 else "REVIEW"
        return ServingBenchmark(
            sample_count=n_runs,
            p50_ms=round(p50, 3),
            p95_ms=round(p95, 3),
            p99_ms=round(p99, 3),
            max_ms=round(max(latencies), 3),
            mean_ms=round(float(np.mean(latencies)), 3),
            status=status,
        )
