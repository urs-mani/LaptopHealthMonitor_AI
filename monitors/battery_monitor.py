import os
import platform
import subprocess
from typing import Any

import psutil


class BatteryMonitor:
    def collect(self) -> dict[str, Any]:
        battery = psutil.sensors_battery()
        if battery is None:
            return {"health": 100.0, "percent": 100.0, "plugged": False}
        return {
            "health": round(min(100.0, max(0.0, battery.percent)), 1),
            "percent": round(battery.percent, 1),
            "plugged": battery.power_plugged,
        }
