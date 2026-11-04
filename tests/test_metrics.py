import json
import os
import tempfile
import unittest
from pathlib import Path

from app.charts import render_chart
from app.metrics import (
    collect_processes,
    cpu_percent,
    format_connections,
    parse_cpu_times,
    parse_meminfo,
    parse_net_dev,
    parse_proc_net,
    present_cpu,
    present_host,
    present_memory,
    rates_from_counters,
    read_disks,
    top_processes,
)


class HostTests(unittest.TestCase):
    def test_reader_uses_fixed_samples(self):
        view = present_host("box", "3661.2 999\n", "0.50 0.40 0.30 1/100 10\n")
        self.assertEqual(view["hostname"], "box")
        self.assertEqual(view["uptime"], "1h 1m")
        self.assertEqual(view["load"], "0.50 0.40 0.30")
        self.assertIsNone(view["error"])
        longer = present_host("box", "90061 1\n", "1 1 1 1/1 1\n")
        self.assertEqual(longer["uptime"], "1d 1h 1m")

    def test_bad_samples_do_not_leak_into_the_error(self):
        view = present_host("box", "/var/secret/uptime", "nope-and-/etc/passwd")
        self.assertEqual(view["hostname"], "box")
        self.assertIn("Unable to read uptime", view["error"])
        self.assertIn("Unable to read load average", view["error"])
        self.assertNotIn("/var/secret", view["error"])
        self.assertNotIn("passwd", view["error"])
        self.assertNotIn("nope", view["error"])


class CpuMemoryTests(unittest.TestCase):
    def test_cpu_percent_from_fixed_stat_samples(self):
        previous = parse_cpu_times("cpu  100 0 0 100 0 0 0 0 9 9\ncpu0 1 0 0 1 0 0 0 0\n")
        current = parse_cpu_times("cpu  150 0 50 200 0 0 0 0 0 0\n")
        self.assertEqual(previous["total"], 200)
        self.assertEqual(cpu_percent(previous, current), 50.0)

    def test_bad_cpu_sample_hides_the_input(self):
        view, current = present_cpu(None, "/tmp/secret-cpu")
        self.assertIsNone(current)
        self.assertEqual(view["error"], "Unable to read CPU")
        self.assertNotIn("secret", view["error"])

    def test_memory_from_fixed_meminfo(self):
        parsed = parse_meminfo(
            "MemTotal: 1000000 kB\nMemFree: 100 kB\nMemAvailable: 250000 kB\n"
        )
        self.assertEqual(parsed["total"], 1000000 * 1024)
        self.assertEqual(parsed["used"], 750000 * 1024)
        self.assertEqual(parsed["percent"], 75.0)
        view, _total = present_memory("MemTotal: nope\n")
        self.assertEqual(view["error"], "Unable to read memory")
        self.assertNotIn("nope", view["error"])


class NetworkTests(unittest.TestCase):
    SAMPLE = """
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 1 0 0 0 0 0 0 2000 1 0 0 0 0 0 0
  eth0: 3000 1 0 0 0 0 0 0 4000 1 0 0 0 0 0 0
"""

    def test_parser_sums_interface_counters(self):
        counters = parse_net_dev(self.SAMPLE)
        self.assertEqual(counters, {"rx_bytes": 4000, "tx_bytes": 6000})

    def test_rate_math_with_fixed_counters(self):
        previous = {"rx_bytes": 1000, "tx_bytes": 2000}
        current = {"rx_bytes": 5000, "tx_bytes": 2600}
        rates = rates_from_counters(previous, current, 4)
        self.assertEqual(rates["rx_bps"], 1000)
        self.assertEqual(rates["tx_bps"], 150)
        self.assertIsNone(rates_from_counters(previous, current, 0)["rx_bps"])
        wrapped = {"rx_bytes": 10, "tx_bytes": 2000}
        self.assertIsNone(rates_from_counters(previous, wrapped, 4)["rx_bps"])


class DiskTests(unittest.TestCase):
    def test_reader_skips_unreadable_and_non_local_mounts(self):
        mounts = "\n".join(
            [
                "/dev/sda1 / ext4 rw 0 0",
                "/dev/sdb1 /blocked ext4 rw 0 0",
                "proc /proc proc rw 0 0",
                "server:/share /mnt/nas nfs rw 0 0",
                "/dev/sdc1 /media/My\\040Disk xfs rw 0 0",
            ]
        )

        class Stat:
            def __init__(self, blocks, bfree, frsize):
                self.f_blocks = blocks
                self.f_bfree = bfree
                self.f_frsize = frsize

        def stat_fn(path):
            if path == "/blocked":
                raise OSError("denied")
            return Stat(1000, 250, 4096)

        rows = read_disks(mounts, stat_fn, is_dir=lambda _path: True)
        self.assertEqual([row["mount"] for row in rows], ["/", "/media/My Disk"])
        self.assertEqual(rows[0]["total"], 1000 * 4096)
        self.assertEqual(rows[0]["used"], 750 * 4096)
        self.assertEqual(rows[0]["percent"], 75.0)


class PortTests(unittest.TestCase):
    def test_formats_fixed_rows_and_drops_extra_fields(self):
        text = (
            "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 "
            "00000000 0 0 0 1 0000000000000000 100 0 0 10 0\n"
            "   1: 0100007F:0CEA 0100007F:0050 01 00000000:00000000 00:00000000 "
            "00000000 0 0 0 1 0000000000000000 100 0 0 10 0\n"
        )
        parsed = parse_proc_net(text, ipv6=False)
        view = format_connections(parsed)
        self.assertIsNone(view["error"])
        self.assertEqual(
            view["listening"],
            [{"local": "127.0.0.1:8080", "remote": "0.0.0.0:0", "state": "LISTEN"}],
        )
        self.assertEqual(view["active"][0]["state"], "ESTABLISHED")
        self.assertEqual(view["active"][0]["local"], "127.0.0.1:3306")
        extra = format_connections(
            [
                {
                    "local": "127.0.0.1:80",
                    "remote": "0.0.0.0:0",
                    "state": "LISTEN",
                    "cmdline": "nginx -c /secret",
                    "environ": "TOKEN=hidden",
                }
            ]
        )
        self.assertEqual(
            extra["listening"][0],
            {"local": "127.0.0.1:80", "remote": "0.0.0.0:0", "state": "LISTEN"},
        )
        self.assertNotIn("secret", json.dumps(extra))

    def test_ipv6_listen_address(self):
        text = (
            "   0: 00000000000000000000000000000000:0050 "
            "00000000000000000000000000000000:0000 0A\n"
        )
        rows = parse_proc_net(text, ipv6=True)
        self.assertEqual(rows[0]["local"], "[::]:80")
        self.assertEqual(rows[0]["state"], "LISTEN")

    def test_permission_denied_is_a_short_message(self):
        view = format_connections(
            [{"local": "10.0.0.1:1", "remote": "10.0.0.2:2", "state": "ESTABLISHED"}],
            permission_denied=True,
        )
        self.assertEqual(view["listening"], [])
        self.assertEqual(view["active"], [])
        self.assertEqual(
            view["error"], "Port details are hidden without extra privileges."
        )
        self.assertNotIn("Traceback", json.dumps(view))


class ProcessTests(unittest.TestCase):
    def test_sort_and_limit_keep_public_fields_only(self):
        rows = []
        for index in range(12):
            rows.append(
                {
                    "pid": index + 1,
                    "name": f"proc{index}",
                    "cpu": index,
                    "memory": 12 - index,
                    "cmdline": "curl --password hunter2",
                    "environ": "ADMIN_PASSWORD_HASH=supersecret",
                }
            )
        ranked = top_processes(rows, limit=10)
        self.assertEqual(len(ranked["by_cpu"]), 10)
        self.assertEqual(len(ranked["by_memory"]), 10)
        self.assertEqual(ranked["by_cpu"][0]["pid"], 12)
        self.assertEqual(ranked["by_cpu"][0]["cpu"], 11.0)
        self.assertEqual(ranked["by_memory"][0]["pid"], 1)
        self.assertEqual(ranked["by_memory"][0]["memory"], 12.0)
        self.assertEqual(
            set(ranked["by_cpu"][0]), {"pid", "name", "cpu", "memory"}
        )
        blob = json.dumps(ranked)
        self.assertNotIn("hunter2", blob)
        self.assertNotIn("supersecret", blob)

    def test_reader_ignores_cmdline_and_environ(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp)
            pid = proc / "55"
            pid.mkdir()
            rest = ["S"] + ["0"] * 10 + ["5", "7"]
            (pid / "stat").write_text(f"55 (worker) {' '.join(rest)}\n", encoding="utf-8")
            (pid / "status").write_text("Name:\tworker\nVmRSS:\t2048 kB\n", encoding="utf-8")
            (pid / "cmdline").write_text("curl http://secret.example --password hunter2")
            (pid / "environ").write_text("ADMIN_PASSWORD_HASH=supersecret\0PATH=/bin")
            view, ticks, _total = collect_processes(
                str(proc), 8 * 1024 * 1024, 100, {}, None
            )
            self.assertEqual(view["by_memory"][0]["name"], "worker")
            self.assertEqual(view["by_memory"][0]["memory"], 25.0)
            self.assertIsNone(view["by_memory"][0]["cpu"])
            self.assertEqual(ticks[55], 12)
            blob = json.dumps(view)
            self.assertNotIn("hunter2", blob)
            self.assertNotIn("supersecret", blob)
            self.assertNotIn("secret.example", blob)
            again, _ticks, _total = collect_processes(
                str(proc), 8 * 1024 * 1024, 100, {55: 0}, 0
            )
            self.assertEqual(again["by_cpu"][0]["cpu"], 12.0)


class ChartTests(unittest.TestCase):
    def test_chart_escapes_the_label(self):
        svg = str(render_chart([1, 2, 3], "<script>"))
        self.assertIn("<svg", svg)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)


class LiveReadTests(unittest.TestCase):
    @unittest.skipUnless(os.path.isdir("/proc"), "linux proc")
    def test_live_snapshot_errors_do_not_include_paths(self):
        from app.collect import Monitor

        monitor = Monitor(interval=5)
        first = monitor.snapshot(now=1000)
        second = monitor.snapshot(now=1004)
        third = monitor.snapshot(now=1005)
        self.assertIs(first, second)
        self.assertIsNot(third, first)
        for section in ("host", "cpu", "memory", "network", "disk", "ports", "processes"):
            error = third[section].get("error")
            if error:
                self.assertNotIn("/proc", error)
                self.assertNotIn("SECRET", error)
                self.assertNotIn("Traceback", error)
        for row in third["processes"]["by_cpu"]:
            self.assertEqual(
                set(row),
                {"pid", "name", "cpu", "memory", "cpu_label", "memory_label"},
            )
        for row in third["ports"]["listening"] + third["ports"]["active"]:
            self.assertEqual(set(row), {"local", "remote", "state"})


if __name__ == "__main__":
    unittest.main()
