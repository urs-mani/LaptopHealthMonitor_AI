from __future__ import annotations
import compileall
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
print("Laptop Health Monitor project verification")
print("-" * 48)
def verify_syntax(root: Path) -> bool:
    """Compile sources in memory so verification works in read-only folders too."""
    ok = True
    excluded = {".venv", "__pycache__"}
    for path in root.rglob("*.py"):
        if any(part in excluded for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
            compile(source, str(path), "exec")
        except Exception as exc:
            ok = False
            print(f"Syntax {path.relative_to(root)}: FAIL ({exc})")
    return ok


ok = verify_syntax(ROOT)
print("Python compilation:", "PASS" if ok else "FAIL")
required = ["PyQt6", "pyqtgraph", "psutil", "numpy", "pandas", "sklearn", "joblib", "reportlab", "openpyxl"]
failed = []
for name in required:
    try:
        importlib.import_module(name)
        print(f"Import {name}: PASS")
    except Exception as exc:
        failed.append(name)
        print(f"Import {name}: FAIL ({exc})")
from ai.predictor import BatteryRULPredictor
predictor = BatteryRULPredictor()
print("AI model status:", "TRAINED" if predictor.ready else "NOT TRAINED (expected before dataset setup)")
if not ok or failed:
    sys.exit(1)
print("Verification completed successfully.")
