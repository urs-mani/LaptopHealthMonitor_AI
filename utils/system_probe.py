from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil


class SystemProbe:
    """Best-effort, read-only system telemetry collector.

    Fast counters are sampled every refresh. Slower hardware/OS inventory is cached.
    Unsupported fields are returned as None instead of fabricated values.
    """

    def __init__(self) -> None:
        self._last_net = psutil.net_io_counters()
        self._last_disk = psutil.disk_io_counters()
        self._last_time = time.monotonic()
        self._static_cache: dict[str, Any] = {}
        self._static_at = 0.0

    @staticmethod
    def _gb(value: float) -> float:
        return round(value / (1024 ** 3), 2)

    def fast_snapshot(self, temperature: float, battery_health: float | None = None) -> dict[str, Any]:
        now = time.monotonic()
        elapsed = max(0.25, now - self._last_time)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        cpu = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        root = str(Path.home().anchor or "/")
        du = psutil.disk_usage(root)
        net = psutil.net_io_counters()
        disk_io = psutil.disk_io_counters()
        freq = psutil.cpu_freq()
        battery = psutil.sensors_battery()

        down = max(0.0, (net.bytes_recv - self._last_net.bytes_recv) / elapsed) if net and self._last_net else 0.0
        up = max(0.0, (net.bytes_sent - self._last_net.bytes_sent) / elapsed) if net and self._last_net else 0.0
        read = 0.0
        write = 0.0
        if disk_io and self._last_disk:
            read = max(0.0, (disk_io.read_bytes - self._last_disk.read_bytes) / elapsed)
            write = max(0.0, (disk_io.write_bytes - self._last_disk.write_bytes) / elapsed)
        self._last_net, self._last_disk, self._last_time = net or self._last_net, disk_io or self._last_disk, now

        process_count = len(psutil.pids())
        thread_count = 0
        try:
            for p in psutil.process_iter(["num_threads"]):
                thread_count += int(p.info.get("num_threads") or 0)
        except Exception:
            pass

        return {
            "cpu_usage": round(cpu, 1),
            "cpu_per_core": [round(x, 1) for x in cpu_per_core],
            "cpu_frequency_ghz": round((freq.current / 1000.0), 2) if freq else None,
            "cpu_frequency_max_ghz": round((freq.max / 1000.0), 2) if freq and freq.max else None,
            "logical_cores": psutil.cpu_count(logical=True),
            "physical_cores": psutil.cpu_count(logical=False),
            "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "ram_usage": round(vm.percent, 1),
            "ram_total_gb": self._gb(vm.total),
            "ram_available_gb": self._gb(vm.available),
            "ram_used_gb": self._gb(vm.used),
            "swap_usage": round(swap.percent, 1),
            "swap_total_gb": self._gb(swap.total),
            "disk_usage": round(du.percent, 1),
            "disk_total_gb": self._gb(du.total),
            "disk_free_gb": self._gb(du.free),
            "disk_read_mbps": round(read / (1024 ** 2), 3),
            "disk_write_mbps": round(write / (1024 ** 2), 3),
            "network_download_mbps": round(down * 8 / 1_000_000, 3),
            "network_upload_mbps": round(up * 8 / 1_000_000, 3),
            "network_total_received_gb": self._gb(net.bytes_recv) if net else 0.0,
            "network_total_sent_gb": self._gb(net.bytes_sent) if net else 0.0,
            "battery_percent": round(battery.percent, 1) if battery else None,
            "battery_plugged": bool(battery.power_plugged) if battery else None,
            "battery_seconds_left": battery.secsleft if battery and battery.secsleft >= 0 else None,
            "battery_health": battery_health,
            "temperature": round(float(temperature), 1),
            "uptime_seconds": max(0.0, time.time() - psutil.boot_time()),
            "process_count": process_count,
            "thread_count": thread_count,
            "boot_time": psutil.boot_time(),
        }

    def static_snapshot(self, max_age: float = 600.0) -> dict[str, Any]:
        now = time.monotonic()
        if self._static_cache and now - self._static_at < max_age:
            return dict(self._static_cache)
        data: dict[str, Any] = {
            "os": platform.platform(),
            "os_name": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor() or "Unavailable",
            "hostname": socket.gethostname(),
            "python_version": platform.python_version(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "Unavailable",
        }
        try:
            data["drives"] = []
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    data["drives"].append({
                        "device": part.device, "mount": part.mountpoint, "filesystem": part.fstype,
                        "total_gb": self._gb(usage.total), "free_gb": self._gb(usage.free), "usage": usage.percent,
                    })
                except Exception:
                    continue
            data["network_interfaces"] = {
                name: [a.address for a in addrs if a.address]
                for name, addrs in psutil.net_if_addrs().items()
            }
        except Exception:
            pass

        if platform.system() == "Windows":
            ps = r'''$cs=Get-CimInstance Win32_ComputerSystem; $bios=Get-CimInstance Win32_BIOS; $cpu=Get-CimInstance Win32_Processor|Select-Object -First 1; $gpu=Get-CimInstance Win32_VideoController|Select-Object Name,AdapterRAM,DriverVersion; $os=Get-CimInstance Win32_OperatingSystem; [PSCustomObject]@{Manufacturer=$cs.Manufacturer;Model=$cs.Model;TotalPhysicalMemory=$cs.TotalPhysicalMemory;BIOSManufacturer=$bios.Manufacturer;BIOSVersion=($bios.SMBIOSBIOSVersion -join ', ');BIOSDate=$bios.ReleaseDate;CPUName=$cpu.Name;CPUMaxClockMHz=$cpu.MaxClockSpeed;GPU=$gpu;OSCaption=$os.Caption;OSBuild=$os.BuildNumber}|ConvertTo-Json -Depth 5 -Compress'''
            try:
                out = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps], text=True,
                                              stderr=subprocess.DEVNULL, timeout=12,
                                              encoding="utf-8", errors="ignore").strip()
                if out:
                    data["windows_hardware"] = json.loads(out)
            except Exception:
                data["windows_hardware"] = None
        self._static_cache, self._static_at = data, now
        return dict(data)

    def rows(self, live: dict[str, Any], hardware: dict[str, Any] | None = None):
        hardware = hardware or self.static_snapshot()
        rows: list[tuple[str, str, str]] = []
        def add(category: str, name: str, value: Any):
            if value is None or value == "":
                value = "Unavailable on this device"
            elif isinstance(value, float):
                value = f"{value:.2f}"
            elif isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            rows.append((category, name, str(value)))
        for name in ["os", "architecture", "processor", "hostname", "python_version", "user"]:
            add("System", name.replace("_", " ").title(), hardware.get(name))
        for name in ["physical_cores", "logical_cores", "cpu_frequency_ghz", "cpu_frequency_max_ghz", "cpu_usage", "cpu_per_core"]:
            add("Processor", name.replace("_", " ").title(), live.get(name))
        for name in ["ram_total_gb", "ram_used_gb", "ram_available_gb", "ram_usage", "swap_total_gb", "swap_usage"]:
            add("Memory", name.replace("_", " ").title(), live.get(name))
        for name in ["disk_total_gb", "disk_free_gb", "disk_usage", "disk_read_mbps", "disk_write_mbps"]:
            add("Storage", name.replace("_", " ").title(), live.get(name))
        for name in ["network_download_mbps", "network_upload_mbps", "network_total_received_gb", "network_total_sent_gb"]:
            add("Network", name.replace("_", " ").title(), live.get(name))
        for name in ["battery_percent", "battery_health", "battery_plugged", "battery_seconds_left"]:
            add("Battery", name.replace("_", " ").title(), live.get(name))
        for name in ["temperature", "uptime_seconds", "process_count", "thread_count", "boot_time"]:
            add("Runtime", name.replace("_", " ").title(), live.get(name))
        wh = hardware.get("windows_hardware") or {}
        if isinstance(wh, dict):
            for key, value in wh.items():
                add("Hardware", key, value)
        return rows
