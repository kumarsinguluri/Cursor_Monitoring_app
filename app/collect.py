"""Read local /proc data. No shell command is taken from a request."""

import os
import socket
import threading
import time

from app.history import SAMPLE_INTERVAL_SECONDS, SampleBuffer
from app.metrics import (
    collect_processes,
    disk_error,
    format_connections,
    network_error,
    parse_cpu_times,
    parse_net_dev,
    parse_proc_net,
    present_cpu,
    present_disk_row,
    present_host,
    present_memory,
    present_network,
    ports_error,
    processes_error,
    rates_from_counters,
    read_disks,
)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def empty_snapshot():
    return {
        "host": {"hostname": None, "uptime": None, "load": None, "error": None},
        "cpu": {"percent": None, "percent_label": "—", "error": None},
        "memory": {
            "used": None,
            "total": None,
            "percent": None,
            "used_label": "—",
            "total_label": "—",
            "percent_label": "—",
            "error": None,
        },
        "network": network_error(),
        "disk": disk_error(),
        "ports": ports_error(),
        "processes": processes_error(),
        "history": {"cpu": [], "memory": [], "net_rx": [], "net_tx": []},
    }


class Monitor:
    """Sample this machine about every five seconds and keep the series in memory."""

    def __init__(self, interval=SAMPLE_INTERVAL_SECONDS):
        self.interval = interval
        self.history = SampleBuffer()
        self._lock = threading.Lock()
        self._cpu_prev = None
        self._net_prev = None
        self._net_prev_at = None
        self._proc_prev = {}
        self._proc_total_prev = None
        self.latest = empty_snapshot()
        self._last_at = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="monitor-sampler", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.snapshot()
            except Exception:
                pass
            if self._stop.wait(self.interval):
                return

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            if self._last_at is not None and (now - self._last_at) < self.interval:
                return self.latest
            try:
                self.latest = self._sample(now)
            except Exception:
                pass
            self._last_at = now
            return self.latest

    def _sample(self, now):
        host = self._host()
        cpu_view, cpu_value = self._cpu()
        memory_view, mem_total = self._memory()
        network_view, rx_bps, tx_bps = self._network(now)
        if cpu_value is not None:
            self.history.append("cpu", cpu_value, now)
        if memory_view.get("error") is None and memory_view.get("percent") is not None:
            self.history.append("memory", memory_view["percent"], now)
        if rx_bps is not None and tx_bps is not None:
            self.history.append("net_rx", rx_bps, now)
            self.history.append("net_tx", tx_bps, now)
        return {
            "host": host,
            "cpu": cpu_view,
            "memory": memory_view,
            "network": network_view,
            "disk": self._disk(),
            "ports": self._ports(),
            "processes": self._processes(mem_total),
            "history": {
                "cpu": self.history.values("cpu"),
                "memory": self.history.values("memory"),
                "net_rx": self.history.values("net_rx"),
                "net_tx": self.history.values("net_tx"),
            },
        }

    def _host(self):
        try:
            hostname = socket.gethostname()
        except OSError:
            hostname = ""
        return present_host(
            hostname,
            _maybe_read("/proc/uptime"),
            _maybe_read("/proc/loadavg"),
        )

    def _cpu(self):
        text = _maybe_read("/proc/stat")
        if text is None:
            return _failed_cpu(), None
        view, current = present_cpu(self._cpu_prev, text)
        if view["error"]:
            return view, None
        self._cpu_prev = current
        return view, view["percent"]

    def _memory(self):
        text = _maybe_read("/proc/meminfo")
        if text is None:
            failed = present_memory("")
            return failed[0], None
        return present_memory(text)

    def _network(self, now):
        text = _maybe_read("/proc/net/dev")
        if text is None:
            return network_error(), None, None
        try:
            current = parse_net_dev(text)
        except (TypeError, ValueError, IndexError):
            return network_error(), None, None
        rx_bps = None
        tx_bps = None
        if self._net_prev is not None and self._net_prev_at is not None:
            rates = rates_from_counters(self._net_prev, current, now - self._net_prev_at)
            rx_bps = rates["rx_bps"]
            tx_bps = rates["tx_bps"]
        self._net_prev = current
        self._net_prev_at = now
        return present_network(current, rx_bps, tx_bps), rx_bps, tx_bps

    def _disk(self):
        text = _maybe_read("/proc/mounts")
        if text is None:
            return disk_error()
        try:
            rows = read_disks(text, os.statvfs, os.path.isdir)
        except Exception:
            return disk_error()
        return {"rows": [present_disk_row(row) for row in rows], "error": None}

    def _ports(self):
        try:
            v4 = read_text("/proc/net/tcp")
        except PermissionError:
            return format_connections([], permission_denied=True)
        except OSError:
            return ports_error()
        try:
            v6 = read_text("/proc/net/tcp6")
        except PermissionError:
            return format_connections([], permission_denied=True)
        except FileNotFoundError:
            v6 = ""
        except OSError:
            v6 = ""
        rows = parse_proc_net(v4, ipv6=False) + parse_proc_net(v6, ipv6=True)
        return format_connections(rows)

    def _processes(self, mem_total):
        text = _maybe_read("/proc/stat")
        if text is None:
            return processes_error()
        try:
            cpu_total = parse_cpu_times(text)["total"]
            view, ticks, total = collect_processes(
                "/proc",
                mem_total or 0,
                cpu_total,
                self._proc_prev,
                self._proc_total_prev,
            )
        except (OSError, ValueError):
            return processes_error()
        self._proc_prev = ticks
        self._proc_total_prev = total
        return view


def _maybe_read(path):
    try:
        return read_text(path)
    except OSError:
        return None


def _failed_cpu():
    return {"percent": None, "percent_label": "—", "error": "Unable to read CPU"}
