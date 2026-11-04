"""Read a remote Linux host over SSH. The remote command is fixed."""

import base64
import json
import os
import subprocess
import tempfile
import threading
import time

from app.history import SAMPLE_INTERVAL_SECONDS, SampleBuffer
from app.metrics import (
    LOCAL_FS,
    decorate_process,
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
    safe_mount_path,
    top_processes,
)
from app.collect import empty_snapshot

UNREACHABLE = "Unable to reach this server."
_ASKPASS = "#!/bin/sh\nprintf '%s\\n' \"$MONITOR_SSH_PASSWORD\"\n"
_STDOUT_LIMIT = 1_000_000

REMOTE_SCRIPT = r"""
import json, os, socket
FS = set(__FS__)
def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(), False
    except PermissionError:
        return None, True
    except OSError:
        return None, False
def disks():
    text, _denied = read("/proc/mounts")
    rows, seen = [], set()
    if not text:
        return rows
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount, fstype = parts[1], parts[2]
        if fstype not in FS or mount in seen or not mount.startswith("/") or ".." in mount.split("/"):
            continue
        try:
            if not os.path.isdir(mount):
                continue
            st = os.statvfs(mount)
        except OSError:
            continue
        total = int(st.f_blocks) * int(st.f_frsize)
        used = (int(st.f_blocks) - int(st.f_bfree)) * int(st.f_frsize)
        if total < 0 or used < 0:
            continue
        seen.add(mount)
        percent = round(used / total * 100, 1) if total else 0.0
        rows.append({"mount": mount, "used": max(0, used), "total": total, "percent": percent})
        if len(rows) >= 64:
            break
    return rows
def procs():
    out = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return out
    for name in names:
        if not name.isdigit():
            continue
        try:
            stat = open("/proc/" + name + "/stat", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        start, end = stat.find("("), stat.rfind(")")
        if start < 1 or end < start:
            continue
        try:
            pid = int(stat[:start].strip())
        except ValueError:
            continue
        if str(pid) != name:
            continue
        rest = stat[end + 1:].split()
        if len(rest) < 13:
            continue
        rss = 0
        try:
            status = open("/proc/" + name + "/status", encoding="utf-8", errors="replace").read()
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) * 1024
                    break
        except (OSError, ValueError, IndexError):
            rss = 0
        try:
            ticks = int(rest[11]) + int(rest[12])
        except ValueError:
            continue
        out.append({"pid": pid, "name": stat[start + 1:end][:64], "ticks": ticks, "rss": rss})
        if len(out) >= 400:
            break
    return out
tcp, denied = read("/proc/net/tcp")
tcp6, denied6 = read("/proc/net/tcp6")
print(json.dumps({
    "hostname": socket.gethostname(),
    "uptime": read("/proc/uptime")[0],
    "load": read("/proc/loadavg")[0],
    "cpu": read("/proc/stat")[0],
    "mem": read("/proc/meminfo")[0],
    "net": read("/proc/net/dev")[0],
    "disks": disks(),
    "tcp": tcp or "",
    "tcp6": tcp6 or "",
    "tcp_denied": denied or denied6,
    "processes": procs(),
}))
""".replace("__FS__", json.dumps(sorted(LOCAL_FS)))


def ssh_argv(address, port, username):
    """Build the SSH argument list. The password is not an argument.

    The script is one remote-shell argument. A raw ``python3 -c`` script is
    split on newlines by the remote shell, so the script is sent as base64.
    """
    encoded = base64.b64encode(REMOTE_SCRIPT.encode()).decode()
    command = (
        "python3 -c 'import base64,sys; exec(base64.b64decode(sys.argv[1]))' "
        + encoded
    )
    return [
        "ssh",
        "-o",
        "PreferredAuthentications=password,keyboard-interactive",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ConnectTimeout=5",
        "-p",
        str(port),
        "-l",
        username,
        address,
        command,
    ]


def ssh_collect(address, port, username, password, runner=None):
    """Run the fixed read-only script. Failure returns None and keeps stderr private."""
    if not username or not password:
        return None
    runner = runner or subprocess.run
    handle = tempfile.NamedTemporaryFile("w", prefix="hm-askpass-", delete=False)
    try:
        handle.write(_ASKPASS)
        handle.close()
        os.chmod(handle.name, 0o700)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", ""),
            "LANG": "C",
            "MONITOR_SSH_PASSWORD": password,
            "SSH_ASKPASS": handle.name,
            "SSH_ASKPASS_REQUIRE": "force",
            "DISPLAY": "none",
        }
        try:
            completed = runner(
                ssh_argv(address, port, username),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=12,
                env=env,
                check=False,
                start_new_session=True,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if getattr(completed, "returncode", 1) != 0:
            return None
        return _parse_stdout(getattr(completed, "stdout", b"") or b"")
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


def _parse_stdout(stdout):
    if isinstance(stdout, bytes):
        text = stdout.decode("utf-8", "replace")
    else:
        text = str(stdout)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start or (end - start) > _STDOUT_LIMIT:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def unreachable_snapshot():
    snap = empty_snapshot()
    snap["host"] = {**snap["host"], "error": None}
    snap["cpu"] = {**snap["cpu"], "error": None}
    snap["memory"] = {**snap["memory"], "error": None}
    snap["network"] = {**snap["network"], "error": None}
    snap["disk"] = {**snap["disk"], "error": None}
    snap["ports"] = {**snap["ports"], "error": None}
    snap["processes"] = {**snap["processes"], "error": None}
    snap["error"] = UNREACHABLE
    return snap


class RemoteMonitor:
    """Keep one in-memory series per server. SSH runs inside that server's lock."""

    def __init__(self, collect=None, interval=SAMPLE_INTERVAL_SECONDS):
        self._collect = collect or ssh_collect
        self.interval = interval
        self._guard = threading.Lock()
        self._states = {}

    def snapshot(self, server, now=None):
        now = time.time() if now is None else now
        state = self._state(server["id"])
        with state.lock:
            if state.last_at is not None and (now - state.last_at) < self.interval:
                return state.latest
            try:
                payload = self._collect(
                    server["address"],
                    int(server["port"]),
                    server.get("username") or "",
                    server.get("password") or "",
                )
            except Exception:
                payload = None
            if payload is None:
                state.latest = unreachable_snapshot()
            else:
                state.latest = snapshot_from_payload(payload, state, now)
            state.last_at = now
            return state.latest

    def _state(self, server_id):
        with self._guard:
            state = self._states.get(server_id)
            if state is None:
                state = _Series()
                self._states[server_id] = state
            return state


class _Series:
    def __init__(self):
        self.lock = threading.Lock()
        self.history = SampleBuffer()
        self.cpu_prev = None
        self.net_prev = None
        self.net_prev_at = None
        self.proc_prev = {}
        self.proc_total_prev = None
        self.latest = unreachable_snapshot()
        self.last_at = None


def snapshot_from_payload(payload, state, now):
    if not isinstance(payload, dict):
        return unreachable_snapshot()
    host = present_host(
        payload.get("hostname") if isinstance(payload.get("hostname"), str) else "",
        _text(payload.get("uptime")),
        _text(payload.get("load")),
    )
    cpu_view, cpu_value = _cpu(state, _text(payload.get("cpu")) or "")
    memory_view, mem_total = _memory(_text(payload.get("mem")) or "")
    network_view, rx_bps, tx_bps = _network(state, _text(payload.get("net")), now)
    if cpu_value is not None:
        state.history.append("cpu", cpu_value, now)
    if memory_view.get("error") is None and memory_view.get("percent") is not None:
        state.history.append("memory", memory_view["percent"], now)
    if rx_bps is not None and tx_bps is not None:
        state.history.append("net_rx", rx_bps, now)
        state.history.append("net_tx", tx_bps, now)
    return {
        "host": host,
        "cpu": cpu_view,
        "memory": memory_view,
        "network": network_view,
        "disk": _disks(payload.get("disks")),
        "ports": _ports(payload),
        "processes": _processes(state, payload.get("processes"), mem_total, _text(payload.get("cpu")) or ""),
        "history": {
            "cpu": state.history.values("cpu"),
            "memory": state.history.values("memory"),
            "net_rx": state.history.values("net_rx"),
            "net_tx": state.history.values("net_tx"),
        },
        "error": None,
    }


def _text(value):
    return value if isinstance(value, str) else None


def _cpu(state, text):
    if not text:
        return {"percent": None, "percent_label": "—", "error": "Unable to read CPU"}, None
    view, current = present_cpu(state.cpu_prev, text)
    if view["error"]:
        return view, None
    state.cpu_prev = current
    return view, view["percent"]


def _memory(text):
    if not text:
        failed, _total = present_memory("")
        return failed, None
    return present_memory(text)


def _network(state, text, now):
    if not text:
        return network_error(), None, None
    try:
        current = parse_net_dev(text)
    except (TypeError, ValueError, IndexError):
        return network_error(), None, None
    rx_bps = None
    tx_bps = None
    if state.net_prev is not None and state.net_prev_at is not None:
        rates = rates_from_counters(state.net_prev, current, now - state.net_prev_at)
        rx_bps = rates["rx_bps"]
        tx_bps = rates["tx_bps"]
    state.net_prev = current
    state.net_prev_at = now
    return present_network(current, rx_bps, tx_bps), rx_bps, tx_bps


def _disks(rows):
    if not isinstance(rows, list):
        return disk_error()
    presented = []
    for item in rows:
        if not isinstance(item, dict) or not safe_mount_path(item.get("mount")):
            continue
        try:
            used = int(item["used"])
            total = int(item["total"])
            percent = float(item["percent"])
        except (KeyError, TypeError, ValueError):
            continue
        if used < 0 or total < 0:
            continue
        presented.append(
            present_disk_row(
                {"mount": item["mount"], "used": used, "total": total, "percent": percent}
            )
        )
    return {"rows": presented, "error": None}


def _ports(payload):
    if payload.get("tcp_denied") is True:
        return format_connections([], permission_denied=True)
    tcp = payload.get("tcp")
    tcp6 = payload.get("tcp6")
    if not isinstance(tcp, str) or not isinstance(tcp6, str):
        return ports_error()
    rows = parse_proc_net(tcp, ipv6=False) + parse_proc_net(tcp6, ipv6=True)
    return format_connections(rows)


def _processes(state, samples, mem_total, cpu_text):
    if not isinstance(samples, list) or not cpu_text:
        return processes_error()
    try:
        cpu_total = parse_cpu_times(cpu_text)["total"]
    except (TypeError, ValueError, IndexError):
        return processes_error()
    rows = []
    new_ticks = {}
    for item in samples:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item["pid"])
            ticks = int(item["ticks"])
            rss = int(item["rss"])
        except (KeyError, TypeError, ValueError):
            continue
        if pid <= 0 or rss < 0:
            continue
        new_ticks[pid] = ticks
        cpu = None
        if state.proc_total_prev is not None and pid in state.proc_prev:
            total_delta = cpu_total - state.proc_total_prev
            proc_delta = ticks - state.proc_prev[pid]
            if total_delta > 0 and proc_delta >= 0:
                cpu = round(proc_delta / total_delta * 100, 1)
        memory = round(rss / mem_total * 100, 1) if mem_total else None
        rows.append(
            {
                "pid": pid,
                "name": item.get("name") if isinstance(item.get("name"), str) else "?",
                "cpu": cpu,
                "memory": memory,
            }
        )
    ranked = top_processes(rows)
    state.proc_prev = new_ticks
    state.proc_total_prev = cpu_total
    return {
        "by_cpu": [decorate_process(row) for row in ranked["by_cpu"]],
        "by_memory": [decorate_process(row) for row in ranked["by_memory"]],
        "error": None,
    }
