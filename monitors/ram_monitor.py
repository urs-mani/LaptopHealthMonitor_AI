import psutil


class RAMMonitor:
    def collect(self) -> dict:
        memory = psutil.virtual_memory()
        return {
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "usage": round(memory.percent, 1),
        }
