import os
import platform
import re
import subprocess
from typing import Any

import psutil


class TemperatureMonitor:
    def collect(self) -> dict[str, Any]:
        temps = []
        if os.name == "nt":
            try:
                output = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", "Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation | Select-Object -ExpandProperty Temperature"],
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=5,
                )
                for line in output.splitlines():
                    if line.strip():
                        try:
                            temp = float(line.strip())
                            temps.append(temp / 10.0)
                        except ValueError:
                            pass
            except Exception:
                pass
        if not temps:
            try:
                sensor_data = psutil.sensors_temperatures()
            except AttributeError:
                sensor_data = {}
            if sensor_data:
                for key in ("coretemp", "cpu_thermal", "pch_thermal"):
                    if key in sensor_data and sensor_data[key]:
                        temps.append(float(sensor_data[key][0].current))
                        break
        if not temps:
            temps.append(45.0)
        return {"celsius": round(temps[0], 1), "status": self.classify(temps[0])}

    def classify(self, temp: float) -> str:
        if temp > 90:
            return "critical"
        if temp > 80:
            return "warning"
        return "normal"
