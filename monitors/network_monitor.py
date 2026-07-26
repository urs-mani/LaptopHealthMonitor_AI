import psutil


class NetworkMonitor:
    def collect(self) -> dict:
        net = psutil.net_io_counters()
        return {"bytes_sent": net.bytes_sent, "bytes_recv": net.bytes_recv}
