from __future__ import annotations

import zipfile
from pathlib import Path
import numpy as np
import pandas as pd

from .config import CACHE_DIR, DATASET_DIR, FEATURES


def _find_cycle_csv() -> Path | None:
    preferred = [
        DATASET_DIR / "nasa_cycle_level.csv",
        DATASET_DIR / "battery_cycle_level.csv",
        DATASET_DIR / "dataset.csv",
    ]
    for path in preferred:
        if path.exists():
            return path
    csvs = [p for p in DATASET_DIR.rglob("*.csv") if p.name.lower() != "metadata.csv"]
    for path in csvs:
        try:
            columns = set(pd.read_csv(path, nrows=2).columns)
            if {"battery_id", "cycle_index", "rul_cycles"}.issubset(columns):
                return path
        except Exception:
            continue
    return None


def _find_cleaned_root() -> Path | None:
    candidates = [DATASET_DIR / "cleaned_dataset", DATASET_DIR]
    for base in candidates:
        if (base / "metadata.csv").exists() and (base / "data").is_dir():
            return base
    for meta in DATASET_DIR.rglob("metadata.csv"):
        if (meta.parent / "data").is_dir():
            return meta.parent
    return None


def _extract_archive() -> Path | None:
    archives = sorted(DATASET_DIR.glob("*.zip"))
    if not archives:
        return None
    archive = archives[0]
    target = CACHE_DIR / f"extracted_{archive.stem}"
    marker = target / ".complete"
    if not marker.exists():
        if target.exists():
            import shutil
            shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target)
        marker.write_text("ok", encoding="utf-8")
    for meta in target.rglob("metadata.csv"):
        if (meta.parent / "data").is_dir():
            return meta.parent
    return None


def build_cycle_dataset() -> pd.DataFrame:
    """Load a prepared cycle CSV or convert the cleaned NASA archive/folder."""
    cycle_csv = _find_cycle_csv()
    if cycle_csv:
        df = pd.read_csv(cycle_csv)
        missing = [c for c in ["battery_id", "rul_cycles", *FEATURES] if c not in df.columns]
        if missing:
            raise ValueError(f"Cycle CSV is missing columns: {', '.join(missing)}")
        if "total_cycles" not in df.columns:
            df["total_cycles"] = df.groupby("battery_id")["cycle_index"].transform("max")
        if "health_class" not in df.columns:
            fraction = df["rul_cycles"] / df["total_cycles"].clip(lower=1)
            df["health_class"] = pd.cut(fraction, [-1, .2, .5, 1.1], labels=["Critical", "Warning", "Healthy"]).astype(str)
        return _clean(df)

    root = _find_cleaned_root() or _extract_archive()
    if root is None:
        raise FileNotFoundError(
            "No supported dataset found. Put one of these in ai/dataset/:\n"
            "1) NASA cleaned archive .zip,\n"
            "2) extracted cleaned_dataset folder containing metadata.csv and data/, or\n"
            "3) a prepared nasa_cycle_level.csv."
        )

    meta = pd.read_csv(root / "metadata.csv")
    required_meta = {"type", "battery_id", "filename", "Capacity", "ambient_temperature"}
    missing_meta = sorted(required_meta - set(meta.columns))
    if missing_meta:
        raise ValueError(f"metadata.csv is missing: {', '.join(missing_meta)}")
    meta = meta[meta["type"].astype(str).str.lower().eq("discharge")].copy()
    meta["Capacity"] = pd.to_numeric(meta["Capacity"], errors="coerce")
    sort_col = "test_id" if "test_id" in meta.columns else "filename"
    rows: list[dict] = []
    for battery_id, group in meta.groupby("battery_id", sort=True):
        group = group.sort_values(sort_col).reset_index(drop=True)
        initial = float(group["Capacity"].dropna().head(5).median())
        total = len(group)
        for index, row in group.iterrows():
            file_path = root / "data" / str(row["filename"])
            if not file_path.exists():
                continue
            try:
                cycle = pd.read_csv(file_path)
                voltage = pd.to_numeric(cycle.get("Voltage_measured"), errors="coerce")
                current = pd.to_numeric(cycle.get("Current_measured"), errors="coerce")
                temperature = pd.to_numeric(cycle.get("Temperature_measured"), errors="coerce")
                elapsed = pd.to_numeric(cycle.get("Time"), errors="coerce")
                capacity = float(row["Capacity"])
                rows.append({
                    "battery_id": str(battery_id),
                    "cycle_index": index + 1,
                    "total_cycles": total,
                    "rul_cycles": total - (index + 1),
                    "capacity_ah": capacity,
                    "capacity_ratio": capacity / initial if initial > 0 else np.nan,
                    "ambient_temperature": float(row["ambient_temperature"]),
                    "voltage_mean": voltage.mean(),
                    "voltage_min": voltage.min(),
                    "voltage_max": voltage.max(),
                    "current_mean": current.mean(),
                    "current_std": current.std(),
                    "temperature_mean": temperature.mean(),
                    "temperature_max": temperature.max(),
                    "duration_s": elapsed.max() - elapsed.min(),
                })
            except Exception:
                continue
    if not rows:
        raise ValueError("The dataset was found, but no valid discharge-cycle rows could be created.")
    df = pd.DataFrame(rows)
    fraction = df["rul_cycles"] / df["total_cycles"].clip(lower=1)
    df["health_class"] = pd.cut(fraction, [-1, .2, .5, 1.1], labels=["Critical", "Warning", "Healthy"]).astype(str)
    return _clean(df)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.replace([np.inf, -np.inf], np.nan).copy()
    for column in FEATURES:
        df[column] = pd.to_numeric(df[column], errors="coerce")
        df[column] = df.groupby("battery_id")[column].transform(
            lambda series: series.interpolate(limit_direction="both")
        )
        median = df[column].median()
        df[column] = df[column].fillna(0.0 if pd.isna(median) else median)
    df["rul_cycles"] = pd.to_numeric(df["rul_cycles"], errors="coerce")
    df = df.dropna(subset=["battery_id", "rul_cycles"]).reset_index(drop=True)
    if len(df) < 100:
        raise ValueError(f"Only {len(df)} valid records were found; at least 100 are required.")
    return df
