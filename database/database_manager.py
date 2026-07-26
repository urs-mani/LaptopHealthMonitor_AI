import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class DatabaseManager:
    """Thread-safe SQLite database manager.

    Key design points:
    - No global/shared sqlite3.Connection caching.
    - Each operation opens its own connection via context manager.
    - WAL mode + busy_timeout reduce locking contention.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = Path(db_path or os.path.join(os.path.dirname(__file__), "laptop_health.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False is an extra safety net; we still avoid sharing
        # connection objects across threads by creating a new connection per call.
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
        )
        conn.row_factory = sqlite3.Row

        # Concurrency/performance pragmas.
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        return conn

    def initialize_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")

        with self._connect() as conn:
            if schema_path.exists():
                conn.executescript(schema_path.read_text(encoding="utf-8"))
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS system_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        cpu_usage REAL,
                        ram_usage REAL,
                        battery_health REAL,
                        temperature REAL,
                        disk_usage REAL,
                        network_usage REAL,
                        health_score REAL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        priority TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        report_type TEXT NOT NULL,
                        file_path TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL,
                        value TEXT NOT NULL
                    )
                    """
                )

            # default settings + sample data are created once.
            self._create_default_settings_and_sample_metrics(conn)

    def _create_default_settings_and_sample_metrics(self, conn: sqlite3.Connection) -> None:
        defaults: Dict[str, str] = {
            "monitor_interval": "1",
            "cpu_threshold": "80",
            "temperature_warning": "80",
            "temperature_critical": "90",
            "theme": "Light",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

        # If the DB is empty, seed it from sample_metrics.csv.
        cur = conn.execute("SELECT COUNT(*) FROM system_metrics")
        count = int(cur.fetchone()[0])
        if count == 0:
            sample_path = Path(__file__).resolve().parent.parent / "data" / "sample_metrics.csv"
            if sample_path.exists():
                import csv

                with sample_path.open(encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        conn.execute(
                            """
                            INSERT INTO system_metrics (
                                timestamp, cpu_usage, ram_usage, battery_health, temperature,
                                disk_usage, network_usage, health_score
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                row["timestamp"],
                                float(row["cpu_usage"]),
                                float(row["ram_usage"]),
                                float(row["battery_health"]),
                                float(row["temperature"]),
                                float(row["disk_usage"]),
                                float(row["network_usage"]),
                                float(row["health_score"]),
                            ),
                        )

    def save_system_metric(self, data: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO system_metrics (
                    timestamp, cpu_usage, ram_usage, battery_health, temperature,
                    disk_usage, network_usage, health_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    data.get("cpu_usage"),
                    data.get("ram_usage"),
                    data.get("battery_health"),
                    data.get("temperature"),
                    data.get("disk_usage"),
                    data.get("network_usage"),
                    data.get("health_score"),
                ),
            )

    def get_recent_metrics(self, limit: int = 60) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM system_metrics ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            # Return in ascending time order.
            return [dict(row) for row in reversed(rows)]

    def add_alert(self, severity: str, title: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (timestamp, severity, title, message)
                VALUES (?, ?, ?, ?)
                """,
                (datetime.now().isoformat(), severity, title, message),
            )

    def get_alerts(self, limit: int = 20) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_recommendation(self, title: str, description: str, priority: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO recommendations (timestamp, title, description, priority)
                VALUES (?, ?, ?, ?)
                """,
                (datetime.now().isoformat(), title, description, priority),
            )

    def get_recommendations(self, limit: int = 20) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM recommendations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_report(self, report_type: str, file_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (timestamp, report_type, file_path)
                VALUES (?, ?, ?)
                """,
                (datetime.now().isoformat(), report_type, file_path),
            )

    def get_reports(self) -> List[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()
            return [dict(row) for row in rows]

    def save_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
            return row[0] if row else default

    def get_settings(self) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {row[0]: row[1] for row in rows}

