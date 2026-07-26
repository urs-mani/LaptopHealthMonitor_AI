from __future__ import annotations
import sys
from .dataset_loader import build_cycle_dataset

try:
    df = build_cycle_dataset()
    print("DATASET CHECK: PASS")
    print(f"Records: {len(df):,}")
    print(f"Batteries: {df['battery_id'].nunique()}")
    print(f"Columns: {len(df.columns)}")
except Exception as exc:
    print("DATASET CHECK: FAILED")
    print(exc)
    sys.exit(1)
