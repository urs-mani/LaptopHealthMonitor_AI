"""Compatibility predictor.

The original student prototype trained models on synthetic random rows. That
behaviour has been removed. The application remains usable with transparent
rule-based risk estimates until the NASA dataset is added and the research
models are trained via TRAIN_AI_MODEL.bat.
"""
from __future__ import annotations
from typing import Any


class Predictor:
    def __init__(self, model_dir: str | None = None) -> None:
        self.model_dir = model_dir
        self.model_status = "Condition-based fallback"

    def predict(self, metrics: dict[str, Any]) -> dict[str, Any]:
        cpu = max(0.0, min(1.0, float(metrics.get("cpu_usage", 0)) / 100.0))
        ram = max(0.0, min(1.0, float(metrics.get("ram_usage", 0)) / 100.0))
        temp = float(metrics.get("temperature", 0))
        battery = max(0.0, min(1.0, float(metrics.get("battery_health", 100)) / 100.0))
        disk = max(0.0, min(1.0, float(metrics.get("disk_usage", 0)) / 100.0))
        thermal = max(0.0, min(1.0, (temp - 60.0) / 35.0))
        return {
            "battery_failure": round(min(1.0, .55 * (1.0 - battery) + .25 * thermal + .20 * cpu), 3),
            "disk_failure": round(min(1.0, .60 * disk + .20 * thermal + .20 * cpu), 3),
            "overheating_risk": round(min(1.0, .65 * thermal + .20 * cpu + .15 * ram), 3),
            "performance_degradation": round(min(1.0, .40 * cpu + .35 * ram + .15 * thermal + .10 * disk), 3),
            "anomaly_score": 0.0,
            "confidence": 0.0,
            "mode": self.model_status,
        }
