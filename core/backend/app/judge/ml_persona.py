# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""ML-based persona training (logistic regression saf Python).

Outcome (accept=1, reject=0) → 3-feature logistic regression:
  - ast_score (0-10)
  - llm_score (0-10)
  - persona_drift (0-2)

Sklearn opsiyonel; default saf Python (math.exp + manual gradient descent).
Model: cache_dir/persona_ml_model.json
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.judge.log import read_recent

logger = logging.getLogger(__name__)


def _model_path() -> Path:
    p = Path(settings.cache_dir) / "persona_ml_model.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def _extract_features(entry: dict) -> Optional[List[float]]:
    ast = entry.get("ast_score")
    llm = entry.get("llm_score")
    drift = entry.get("persona_drift")
    if ast is None or llm is None or drift is None:
        return None
    try:
        return [float(ast), float(llm), float(drift)]
    except (TypeError, ValueError):
        return None


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _train_logistic(
    X: List[List[float]], y: List[int], epochs: int = 200, lr: float = 0.05
) -> Dict[str, Any]:
    """Saf Python gradient descent logistic regression."""
    n_features = len(X[0])
    w = [0.0] * n_features
    b = 0.0
    n = len(X)
    for _ in range(epochs):
        dw = [0.0] * n_features
        db = 0.0
        for xi, yi in zip(X, y):
            z = sum(wj * xij for wj, xij in zip(w, xi)) + b
            p = _sigmoid(z)
            err = p - yi
            for j in range(n_features):
                dw[j] += err * xi[j]
            db += err
        for j in range(n_features):
            w[j] -= lr * dw[j] / n
        b -= lr * db / n
    return {"weights": w, "bias": b, "n_samples": n}


def train_ml(min_samples: int = 20) -> Dict[str, Any]:
    """judge_log entry'lerini logistic regression ile fit et, modeli persist et."""
    entries = read_recent(limit=2000)
    rows: List[tuple] = []
    for e in entries:
        feats = _extract_features(e)
        outcome = e.get("outcome")
        if feats and outcome in ("accept", "reject"):
            rows.append((feats, 1 if outcome == "accept" else 0))
    if len(rows) < min_samples:
        return {
            "action": "insufficient_data",
            "samples": len(rows),
            "min_required": min_samples,
        }
    X = [r[0] for r in rows]
    y = [r[1] for r in rows]
    model = _train_logistic(X, y)
    payload = {
        "trained_at": time.time(),
        "weights": model["weights"],
        "bias": model["bias"],
        "n_samples": model["n_samples"],
        "feature_names": ["ast_score", "llm_score", "persona_drift"],
    }
    _model_path().write_text(json.dumps(payload), encoding="utf-8")
    return {"action": "trained", **payload}


def predict_accept(
    ast_score: float, llm_score: float, persona_drift: float
) -> Dict[str, Any]:
    """Probability that this patch is accepted, from the trained model."""
    p = _model_path()
    if not p.is_file():
        return {"error": "model not trained yet — call train_ml first"}
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": f"model parse fail: {exc}"}
    feats = [float(ast_score), float(llm_score), float(persona_drift)]
    weights = m.get("weights") or []
    bias = float(m.get("bias", 0.0))
    z = sum(float(w) * x for w, x in zip(weights, feats)) + bias
    prob = _sigmoid(z)
    return {
        "p_accept": round(prob, 4),
        "decision": "accept" if prob >= 0.5 else "reject",
        "model_n_samples": m.get("n_samples"),
        "feature_names": m.get("feature_names", []),
    }


def model_status() -> Dict[str, Any]:
    p = _model_path()
    if not p.is_file():
        return {"trained": False}
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"trained": False, "error": "model corrupt"}
    return {
        "trained": True,
        "trained_at": m.get("trained_at"),
        "n_samples": m.get("n_samples"),
        "feature_names": m.get("feature_names", []),
    }
