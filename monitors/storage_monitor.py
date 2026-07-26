import os
import hashlib
from pathlib import Path
from typing import List, Dict, Any

import psutil


class StorageMonitor:
    def collect(self) -> dict[str, Any]:
        disk = psutil.disk_usage("C:/")
        return {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "usage": round(disk.percent, 1),
        }

    def analyze_storage(self, root: str = "C:/") -> dict[str, Any]:
        files = []
        for path in Path(root).rglob("*"):
            if path.is_file():
                try:
                    files.append((path, path.stat().st_size))
                except OSError:
                    continue
        large_files = sorted(files, key=lambda item: item[1], reverse=True)[:10]
        large_file_info = [{"path": str(path), "size_mb": round(size / (1024**2), 2)} for path, size in large_files]
        duplicates = self._find_duplicates(files)
        junk_candidates = self._find_junk_candidates(root)
        return {
            "large_files": large_file_info,
            "duplicates": duplicates,
            "junk_files": junk_candidates,
            "cleanup_suggestions": self._suggest_cleanup(duplicates, junk_candidates),
        }

    def _find_duplicates(self, files: List[tuple[Path, int]]) -> List[Dict[str, Any]]:
        hashes = {}
        duplicates = []
        for path, size in files:
            try:
                if size > 5 * 1024 * 1024:
                    with path.open("rb") as handle:
                        digest = hashlib.md5(handle.read()).hexdigest()
                    hashes.setdefault(digest, []).append((path, size))
            except Exception:
                continue
        for entries in hashes.values():
            if len(entries) > 1:
                duplicates.append({"files": [str(path) for path, _ in entries], "size_mb": round(sum(size for _, size in entries) / (1024**2), 2)})
        return duplicates[:10]

    def _find_junk_candidates(self, root: str) -> List[Dict[str, Any]]:
        junk = []
        for folder in ["Downloads", "Temp", "AppData\\Local\\Temp"]:
            path = Path(root) / folder
            if path.exists():
                for file_path in path.rglob("*"):
                    if file_path.is_file() and file_path.stat().st_size > 1024 * 1024:
                        junk.append({"path": str(file_path), "size_mb": round(file_path.stat().st_size / (1024**2), 2)})
        return junk[:10]

    def _suggest_cleanup(self, duplicates: List[Dict[str, Any]], junk: List[Dict[str, Any]]) -> List[str]:
        suggestions = []
        if duplicates:
            suggestions.append("Remove duplicate files to free up storage space.")
        if junk:
            suggestions.append("Clean temporary and large downloaded files.")
        if not suggestions:
            suggestions.append("No immediate cleanup required.")
        return suggestions
