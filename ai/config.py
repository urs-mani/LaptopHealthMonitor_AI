from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_ROOT = ROOT / "ai"
DATASET_DIR = AI_ROOT / "dataset"
MODELS_DIR = AI_ROOT / "models"
REPORTS_DIR = AI_ROOT / "reports"
CACHE_DIR = AI_ROOT / "cache"

FEATURES = [
    "cycle_index", "capacity_ah", "capacity_ratio", "ambient_temperature",
    "voltage_mean", "voltage_min", "voltage_max", "current_mean",
    "current_std", "temperature_mean", "temperature_max", "duration_s",
]

for directory in (DATASET_DIR, MODELS_DIR, REPORTS_DIR, CACHE_DIR):
    directory.mkdir(parents=True, exist_ok=True)
