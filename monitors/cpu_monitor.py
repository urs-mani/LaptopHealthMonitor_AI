import psutil


class CPUMonitor:
    def collect(self) -> dict:
        return {
            "usage": round(psutil.cpu_percent(interval=None), 1),
            "cores": psutil.cpu_count(),
        }
