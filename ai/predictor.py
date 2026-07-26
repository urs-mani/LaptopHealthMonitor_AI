from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from joblib import load

from .config import FEATURES, MODELS_DIR


class BatteryRULPredictor:
    """Loads trained research models when available; never trains fake data."""

    def __init__(self) -> None:
        self.rul_bundle: dict[str, Any] | None = None
        self.classifier_bundle: dict[str, Any] | None = None
        self.metrics: dict[str, Any] = {}
        self.reload()

    @property
    def ready(self) -> bool:
        return self.rul_bundle is not None and self.classifier_bundle is not None

    def reload(self) -> None:
        self.rul_bundle = None
        self.classifier_bundle = None
        try:
            self.rul_bundle = load(MODELS_DIR / "battery_rul_model.joblib")
            self.classifier_bundle = load(MODELS_DIR / "battery_health_classifier.joblib")
            metrics_path = MODELS_DIR / "model_metrics.json"
            self.metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
        except Exception:
            self.rul_bundle = None
            self.classifier_bundle = None
            self.metrics = {}

    def predict(self, features: dict[str, float]) -> dict[str, Any]:
        if not self.ready:
            raise RuntimeError("AI model is not trained. Add the dataset and run TRAIN_AI_MODEL.bat.")
        vector = pd.DataFrame([[float(features.get(name, 0.0)) for name in FEATURES]], columns=FEATURES)
        rul_model = self.rul_bundle["model"]
        classifier = self.classifier_bundle["model"]
        rul = max(0.0, float(rul_model.predict(vector)[0]))
        health_class = str(classifier.predict(vector)[0])
        confidence = None
        if hasattr(classifier, "predict_proba"):
            confidence = float(np.max(classifier.predict_proba(vector)[0]))
        return {
            "rul_cycles": rul,
            "health_class": health_class,
            "confidence": confidence,
            "model_name": self.rul_bundle.get("model_name", "Unknown"),
        }
