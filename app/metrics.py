"""Pure readers. Callers pass sample text; nothing here opens a user-supplied path."""

import os
import socket

LOCAL_FS = {
    "ext2",
    "ext3",
    "ext4",
    "xfs",
    "btrfs",
    "vfat",
    "ntfs",
    "ntfs3",
    "zfs",
    "fuseblk",
    "exfat",
    "f2fs",
    "bcachefs",
    "tmpfs",
    "overlay",
}

TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
    "0C": "NEW_SYN_RECV",
}

PORT_LIMIT = 100
PROCESS_LIMIT = 10
UNABLE_UPTIME = "Unable to read uptime"
UNABLE_LOAD = "Unable to read load average"
UNABLE_HOSTNAME = "Unable to read hostname"
UNABLE_CPU = "Unable to read CPU"
UNABLE_MEMORY = "Unable to read memory"
UNABLE_NETWORK = "Unable to read network counters"
UNABLE_DISK = "Unable to read disks"
UNABLE_PORTS = "Unable to read ports"
PORTS_DENIED = "Port details are hidden without extra privileges."
UNABLE_PROCESSES = "Unable to read processes"


def percent_label(value):
    if value is None:
        return "—"
    return f"{float(value):.1f}%"


def format_bytes(num):
    value = float(num)
    if value < 0:
        value = 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_rate(num):
    return format_bytes(num) + "/s"


def format_uptime(seconds):
    total = int(float(seconds))
    if total < 0:
        raise ValueError("negative uptime")
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def parse_uptime(text):
    return float(str(text).split()[0])


def parse_loadavg(text):
    parts = str(text).split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def present_host(hostname, uptime_text, load_text):
    """Build the host card from fixed sample strings. Errors never echo the input."""
    errors = []
    name = hostname.strip() if isinstance(hostname, str) else ""
    if not name:
        name = None
        errors.append(UNABLE_HOSTNAME)
    uptime = None
    if uptime_text is None:
        errors.append(UNABLE_UPTIME)
    else:
        try:
            uptime = format_uptime(parse_uptime(uptime_text))
        except (TypeError, ValueError, IndexError):
            errors.append(UNABLE_UPTIME)
    load = None
    if load_text is None:
        errors.append(UNABLE_LOAD)
    else:
        try:
            parts = parse_loadavg(load_text)
            load = " ".join(f"{part:.2f}" for part in parts)
        except (TypeError, ValueError, IndexError):
            errors.append(UNABLE_LOAD)
    return {
        "hostname": name,
        "uptime": uptime,
        "load": load,
        "error": " ".join(errors) or None,
    }


def parse_cpu_times(text):
    for line in str(text).splitlines():
        if not line.startswith("cpu "):
            continue
        numbers = [int(part) for part in line.split()[1:]]
        if len(numbers) < 4:
            break
        core = numbers[:8]
        idle = core[3] + (core[4] if len(core) > 4 else 0)
        return {"idle": idle, "total": sum(core)}
    raise ValueError("cpu sample missing")


def cpu_percent(previous, current):
    total_delta = current["total"] - previous["total"]
    idle_delta = current["idle"] - previous["idle"]
    if total_delta <= 0 or idle_delta < 0:
        return None
    busy = 1 - (idle_delta / total_delta)
    if busy < 0:
        busy = 0.0
    if busy > 1:
        busy = 1.0
    return round(busy * 100, 1)


def present_cpu(previous, current_text):
    try:
        current = parse_cpu_times(current_text)
    except (TypeError, ValueError, IndexError):
        return _cpu_error(), None
    percent = None if previous is None else cpu_percent(previous, current)
    return {
        "percent": percent,
        "percent_label": percent_label(percent),
        "error": None,
    }, current


def _cpu_error():
    return {"percent": None, "percent_label": "—", "error": UNABLE_CPU}


def parse_meminfo(text):
    values = {}
    for line in str(text).splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        parts = rest.split()
        if not parts:
            continue
        values[key] = int(parts[0])
    if "MemTotal" not in values or values["MemTotal"] <= 0:
        raise ValueError("memory sample missing")
    total = values["MemTotal"] * 1024
    if "MemAvailable" in values:
        available = values["MemAvailable"] * 1024
    else:
        available = values.get("MemFree", 0) * 1024
    used = max(0, total - available)
    percent = round(used / total * 100, 1)
    return {"total": total, "used": used, "percent": percent}


def present_memory(text):
    try:
        parsed = parse_meminfo(text)
    except (TypeError, ValueError, IndexError):
        return _memory_error(), None
    return {
        "used": parsed["used"],
        "total": parsed["total"],
        "percent": parsed["percent"],
        "used_label": format_bytes(parsed["used"]),
        "total_label": format_bytes(parsed["total"]),
        "percent_label": percent_label(parsed["percent"]),
        "error": None,
    }, parsed["total"]


def _memory_error():
    return {
        "used": None,
        "total": None,
        "percent": None,
        "used_label": "—",
        "total_label": "—",
        "percent_label": "—",
        "error": UNABLE_MEMORY,
    }


def parse_net_dev(text):
    received = 0
    sent = 0
    found = False
    for line in str(text).splitlines():
        if ":" not in line:
            continue
        _name, rest = line.split(":", 1)
        columns = rest.split()
        if len(columns) < 9:
            continue
        try:
            received += int(columns[0])
            sent += int(columns[8])
        except ValueError:
            continue
        found = True
    if not found:
        raise ValueError("network sample missing")
    return {"rx_bytes": received, "tx_bytes": sent}


def counter_rate(previous, current, elapsed):
    if elapsed <= 0:
        return None
    delta = current - previous
    if delta < 0:
        return None
    return delta / elapsed


def rates_from_counters(previous, current, elapsed):
    return {
        "rx_bps": counter_rate(previous["rx_bytes"], current["rx_bytes"], elapsed),
        "tx_bps": counter_rate(previous["tx_bytes"], current["tx_bytes"], elapsed),
    }


def present_network(counters, rx_bps, tx_bps):
    return {
        "rx_bytes": counters["rx_bytes"],
        "tx_bytes": counters["tx_bytes"],
        "rx_bps": None if rx_bps is None else round(rx_bps, 1),
        "tx_bps": None if tx_bps is None else round(tx_bps, 1),
        "rx_total_label": format_bytes(counters["rx_bytes"]),
        "tx_total_label": format_bytes(counters["tx_bytes"]),
        "rx_rate_label": "—" if rx_bps is None else format_rate(rx_bps),
        "tx_rate_label": "—" if tx_bps is None else format_rate(tx_bps),
        "error": None,
    }


def network_error():
    return {
        "rx_bytes": None,
        "tx_bytes": None,
        "rx_bps": None,
        "tx_bps": None,
        "rx_total_label": "—",
        "tx_total_label": "—",
        "rx_rate_label": "—",
        "tx_rate_label": "—",
        "error": UNABLE_NETWORK,
    }


def unescape_mount(value):
    output = []
    index = 0
    while index < len(value):
        if (
            value[index] == "\\"
            and index + 3 < len(value)
            and value[index + 1 : index + 4].isdigit()
        ):
            output.append(chr(int(value[index + 1 : index + 4], 8)))
            index += 4
        else:
            output.append(value[index])
            index += 1
    return "".join(output)


def safe_mount_path(path):
    if not isinstance(path, str) or not path.startswith("/"):
        return False
    if "\x00" in path:
        return False
    return all(part != ".." for part in path.split("/"))


def parse_mounts(text):
    rows = []
    for line in str(text).splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        rows.append(
            {
                "device": unescape_mount(parts[0]),
                "mount": unescape_mount(parts[1]),
                "fstype": parts[2],
            }
        )
    return rows


def read_disks(mounts_text, stat_fn, is_dir=None):
    """One row per local mount. A mount that cannot be read is skipped.

    ``stat_fn`` is called only with mount paths taken from ``mounts_text``.
    """
    is_dir = os.path.isdir if is_dir is None else is_dir
    rows = []
    seen = set()
    for mount in parse_mounts(mounts_text):
        path = mount["mount"]
        fstype = mount["fstype"]
        if fstype not in LOCAL_FS or path in seen or not safe_mount_path(path):
            continue
        try:
            if not is_dir(path):
                continue
            stat = stat_fn(path)
        except OSError:
            continue
        total = int(stat.f_blocks) * int(stat.f_frsize)
        used = (int(stat.f_blocks) - int(stat.f_bfree)) * int(stat.f_frsize)
        if total < 0 or used < 0:
            continue
        percent = round(used / total * 100, 1) if total else 0.0
        seen.add(path)
        rows.append(
            {
                "mount": path,
                "used": used,
                "total": total,
                "percent": percent,
            }
        )
    return rows


def present_disk_row(row):
    return {
        "mount": row["mount"],
        "used_label": format_bytes(row["used"]),
        "total_label": format_bytes(row["total"]),
        "percent_label": percent_label(row["percent"]),
    }


def parse_proc_addr(raw, ipv6):
    ip_hex, port_hex = raw.split(":")
    port = int(port_hex, 16)
    if not ipv6:
        ip = socket.inet_ntoa(bytes.fromhex(ip_hex)[::-1])
    else:
        words = [ip_hex[index : index + 8] for index in range(0, 32, 8)]
        packed = b"".join(bytes.fromhex(word)[::-1] for word in words)
        ip = socket.inet_ntop(socket.AF_INET6, packed)
        return f"[{ip}]:{port}"
    return f"{ip}:{port}"


def parse_proc_net(text, ipv6=False):
    rows = []
    for line in str(text or "").splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] == "sl":
            continue
        try:
            local = parse_proc_addr(parts[1], ipv6)
            remote = parse_proc_addr(parts[2], ipv6)
            state = TCP_STATES.get(parts[3].upper(), parts[3].upper())
        except (ValueError, IndexError, OSError):
            continue
        rows.append({"local": local, "remote": remote, "state": state})
    return rows


def format_connections(rows, permission_denied=False, limit=PORT_LIMIT):
    """Keep local address, remote address, and state. Drop every other field."""
    if permission_denied:
        return {
            "listening": [],
            "active": [],
            "listening_count": 0,
            "active_count": 0,
            "error": PORTS_DENIED,
        }
    listening = []
    active = []
    for row in rows:
        item = {
            "local": str(row["local"]),
            "remote": str(row["remote"]),
            "state": str(row["state"]),
        }
        if item["state"] == "LISTEN":
            listening.append(item)
        else:
            active.append(item)
    listening.sort(key=lambda item: (item["local"], item["remote"]))
    active.sort(key=lambda item: (item["state"], item["local"], item["remote"]))
    return {
        "listening": listening[:limit],
        "active": active[:limit],
        "listening_count": len(listening),
        "active_count": len(active),
        "error": None,
    }


def ports_error():
    return {
        "listening": [],
        "active": [],
        "listening_count": 0,
        "active_count": 0,
        "error": UNABLE_PORTS,
    }


def parse_stat(text):
    start = text.find("(")
    end = text.rfind(")")
    if start < 1 or end < start:
        raise ValueError("stat sample missing")
    pid = int(text[:start].strip())
    name = text[start + 1 : end]
    rest = text[end + 1 :].split()
    if len(rest) < 13:
        raise ValueError("stat sample short")
    ticks = int(rest[11]) + int(rest[12])
    return {"pid": pid, "name": name, "ticks": ticks}


def parse_vm_rss(status_text):
    for line in str(status_text).splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return 0


def clean_process_name(name):
    cleaned = str(name).replace("\x00", "").replace("\n", " ").replace("\r", " ").strip()
    if not cleaned:
        return "?"
    return cleaned[:64]


def top_processes(rows, limit=PROCESS_LIMIT):
    """Sort sample processes and keep pid, name, cpu, and memory only."""
    public = []
    for row in rows:
        cpu = row["cpu"]
        memory = row["memory"]
        public.append(
            {
                "pid": int(row["pid"]),
                "name": clean_process_name(row["name"]),
                "cpu": None if cpu is None else float(cpu),
                "memory": None if memory is None else float(memory),
            }
        )
    by_cpu = sorted(
        public,
        key=lambda row: (-1 if row["cpu"] is None else -row["cpu"], row["pid"]),
    )[:limit]
    by_memory = sorted(
        public,
        key=lambda row: (-1 if row["memory"] is None else -row["memory"], row["pid"]),
    )[:limit]
    return {"by_cpu": by_cpu, "by_memory": by_memory}


def decorate_process(row):
    return {
        "pid": row["pid"],
        "name": row["name"],
        "cpu": row["cpu"],
        "memory": row["memory"],
        "cpu_label": percent_label(row["cpu"]),
        "memory_label": percent_label(row["memory"]),
    }


def collect_processes(
    proc_root, mem_total_bytes, cpu_total, prev_ticks, prev_total, limit=PROCESS_LIMIT
):
    """Read pid, comm, and RSS. Command lines and environ files are not opened."""
    rows = []
    new_ticks = {}
    for name in os.listdir(proc_root):
        if not name.isdigit():
            continue
        stat_path = os.path.join(proc_root, name, "stat")
        try:
            with open(stat_path, "r", encoding="utf-8", errors="replace") as handle:
                parsed = parse_stat(handle.read())
        except (OSError, ValueError):
            continue
        if str(parsed["pid"]) != name:
            continue
        rss = 0
        status_path = os.path.join(proc_root, name, "status")
        try:
            with open(status_path, "r", encoding="utf-8", errors="replace") as handle:
                rss = parse_vm_rss(handle.read())
        except OSError:
            rss = 0
        ticks = parsed["ticks"]
        new_ticks[parsed["pid"]] = ticks
        cpu = None
        if prev_total is not None and parsed["pid"] in prev_ticks:
            total_delta = cpu_total - prev_total
            proc_delta = ticks - prev_ticks[parsed["pid"]]
            if total_delta > 0 and proc_delta >= 0:
                cpu = round(proc_delta / total_delta * 100, 1)
        if mem_total_bytes:
            memory = round(rss / mem_total_bytes * 100, 1)
        else:
            memory = None
        rows.append(
            {
                "pid": parsed["pid"],
                "name": parsed["name"],
                "cpu": cpu,
                "memory": memory,
            }
        )
    ranked = top_processes(rows, limit=limit)
    return {
        "by_cpu": [decorate_process(row) for row in ranked["by_cpu"]],
        "by_memory": [decorate_process(row) for row in ranked["by_memory"]],
        "error": None,
    }, new_ticks, cpu_total


def processes_error():
    return {"by_cpu": [], "by_memory": [], "error": UNABLE_PROCESSES}


def disk_error():
    return {"rows": [], "error": UNABLE_DISK}
