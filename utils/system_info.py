import platform
import socket
import sys
from typing import Any

import psutil


class SystemInfo:
    @staticmethod
    def get_info() -> dict[str, Any]:
        return {
            "device_name": socket.gethostname(),
            "cpu": platform.processor() or platform.machine(),
            "ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "windows_version": platform.platform(),
            "python_version": sys.version.split()[0],
        }
