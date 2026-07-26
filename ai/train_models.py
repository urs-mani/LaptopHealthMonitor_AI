from __future__ import annotations

import json
import math
from datetime import datetime
import numpy as np
import pandas as pd
from joblib import dump
from sklearn.ensemble import (
    ExtraTreesRegressor, GradientBoostingRegressor, RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.metrics import (
    accuracy_score, confusion_matrix, mean_absolute_error,
    mean_absolute_percentage_error, mean_squared_error,
    precision_recall_fscore_support, r2_score,
)
from sklearn.model_selection import GroupShuffleSplit

from .config import FEATURES, MODELS_DIR, REPORTS_DIR
from .dataset_loader import build_cycle_dataset


def train() -> dict:
    df = build_cycle_dataset()
    processed_path = REPORTS_DIR / "processed_cycle_dataset.csv"
    df.to_csv(processed_path, index=False)

    X = df[FEATURES]
    y = df["rul_cycles"]
    groups = df["battery_id"].astype(str)
    if groups.nunique() < 3:
        raise ValueError("At least three distinct batteries are required for battery-level holdout validation.")

    splitter = GroupShuffleSplit(n_splits=1, test_size=.22, random_state=42)
    train_idx, test_idx = next(splitter.split(X, y, groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    candidates = {
        "Random Forest": RandomForestRegressor(n_estimators=350, min_samples_leaf=2, random_state=42, n_jobs=-1),
        "Extra Trees": ExtraTreesRegressor(n_estimators=350, min_samples_leaf=2, random_state=42, n_jobs=-1),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=250, learning_rate=.035, max_depth=3, loss="huber", random_state=42),
    }
    comparison = []
    fitted = {}
    predictions = {}
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        pred = np.clip(model.predict(X_test), 0, None)
        fitted[name] = model
        predictions[name] = pred
        comparison.append({
            "model": name,
            "MAE_cycles": float(mean_absolute_error(y_test, pred)),
            "RMSE_cycles": float(math.sqrt(mean_squared_error(y_test, pred))),
            "R2": float(r2_score(y_test, pred)),
            "MAPE_pct": float(mean_absolute_percentage_error(y_test.clip(lower=1), pred.clip(min=1)) * 100),
        })
    comparison_df = pd.DataFrame(comparison).sort_values("RMSE_cycles").reset_index(drop=True)
    best_name = str(comparison_df.iloc[0]["model"])
    best_model = fitted[best_name]

    classifier = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=42, n_jobs=-1)
    y_class_train = df.iloc[train_idx]["health_class"].astype(str)
    y_class_test = df.iloc[test_idx]["health_class"].astype(str)
    classifier.fit(X_train, y_class_train)
    class_pred = classifier.predict(X_test)
    accuracy = accuracy_score(y_class_test, class_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_class_test, class_pred, average="weighted", zero_division=0)

    dump({
        "model": best_model, "features": FEATURES, "model_name": best_name,
        "dataset_rows": len(df), "trained_at": datetime.now().isoformat(),
    }, MODELS_DIR / "battery_rul_model.joblib")
    dump({
        "model": classifier, "features": FEATURES,
        "classes": classifier.classes_.tolist(), "trained_at": datetime.now().isoformat(),
    }, MODELS_DIR / "battery_health_classifier.joblib")

    importance = pd.DataFrame({
        "feature": FEATURES,
        "importance": getattr(best_model, "feature_importances_", np.zeros(len(FEATURES))),
    }).sort_values("importance", ascending=False)
    comparison_df.to_csv(REPORTS_DIR / "regression_metrics.csv", index=False)
    importance.to_csv(REPORTS_DIR / "feature_importance.csv", index=False)
    pd.DataFrame({"actual_rul": y_test.to_numpy(), "predicted_rul": predictions[best_name]}).to_csv(
        REPORTS_DIR / "test_predictions.csv", index=False
    )

    labels = classifier.classes_.tolist()
    result = {
        "dataset_rows": int(len(df)),
        "batteries": int(groups.nunique()),
        "train_batteries": sorted(df.iloc[train_idx]["battery_id"].astype(str).unique().tolist()),
        "test_batteries": sorted(df.iloc[test_idx]["battery_id"].astype(str).unique().tolist()),
        "best_model": best_name,
        "regression": comparison_df.to_dict("records"),
        "classification": {
            "accuracy": float(accuracy),
            "precision_weighted": float(precision),
            "recall_weighted": float(recall),
            "f1_weighted": float(f1),
            "labels": labels,
            "confusion_matrix": confusion_matrix(y_class_test, class_pred, labels=labels).tolist(),
        },
        "features": FEATURES,
        "validation": "Battery-group holdout; test batteries are not used during training.",
    }
    (MODELS_DIR / "model_metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (REPORTS_DIR / "training_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    metrics = train()
    print(json.dumps(metrics, indent=2))
