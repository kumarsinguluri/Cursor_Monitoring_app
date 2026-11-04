import json
import unittest

from app.remote import REMOTE_SCRIPT, RemoteMonitor, ssh_argv, ssh_collect


class SshCommandTests(unittest.TestCase):
    def test_argv_is_fixed_and_has_no_password_or_user_command(self):
        argv = ssh_argv("203.0.113.5", 2222, "monitor")
        self.assertEqual(argv[0], "ssh")
        self.assertEqual(argv[-2], "203.0.113.5")
        self.assertTrue(argv[-1].startswith("python3 -c "))
        self.assertIn("base64.b64decode", argv[-1])
        self.assertNotIn(REMOTE_SCRIPT, argv[-1])
        joined = " ".join(argv)
        self.assertNotIn("secret-pass", joined)
        self.assertNotIn("rm -rf", joined)
        self.assertNotIn("shell=True", joined)

    def test_failed_ssh_returns_none_without_stderr(self):
        def runner(argv, **kwargs):
            self.assertNotIn("secret-pass", argv)
            self.assertNotIn("secret-pass", kwargs["env"]["SSH_ASKPASS"])
            with open(kwargs["env"]["SSH_ASKPASS"], encoding="utf-8") as handle:
                self.assertNotIn("secret-pass", handle.read())
            self.assertEqual(kwargs["env"]["MONITOR_SSH_PASSWORD"], "secret-pass")
            return _Result(1, b"", b"SECRET_PATH=/tmp/keys")

        result = ssh_collect("203.0.113.5", 22, "monitor", "secret-pass", runner=runner)
        self.assertIsNone(result)

    def test_stdout_json_is_the_reading(self):
        body = json.dumps({"hostname": "remote-host"}).encode()

        def runner(argv, **kwargs):
            self.assertNotIn("secret-pass", " ".join(argv))
            return _Result(0, b"noise\n" + body + b"\n", b"")

        result = ssh_collect("203.0.113.5", 22, "monitor", "secret-pass", runner=runner)
        self.assertEqual(result, {"hostname": "remote-host"})


class RemoteSnapshotTests(unittest.TestCase):
    def test_two_samples_fill_cpu_and_a_failure_stays_generic(self):
        calls = {"n": 0}

        def collect(address, port, username, password):
            self.assertEqual((address, port, username, password), ("203.0.113.5", 22, "monitor", "secret-pass"))
            calls["n"] += 1
            idle = 100 if calls["n"] == 1 else 150
            busy = 0 if calls["n"] == 1 else 50
            cpu = f"cpu  {busy} 0 0 {idle} 0 0 0 0\n"
            net_rx = 1000 if calls["n"] == 1 else 1100
            return {
                "hostname": "remote-host",
                "uptime": "90 0\n",
                "load": "0.10 0.20 0.30 1/1 1\n",
                "cpu": cpu,
                "mem": "MemTotal: 2048 kB\nMemAvailable: 1024 kB\n",
                "net": f"  lo: {net_rx} 0 0 0 0 0 0 0 400 0 0 0 0 0 0 0\n",
                "disks": [{"mount": "/", "used": 10, "total": 20, "percent": 50.0}],
                "tcp": "",
                "tcp6": "",
                "tcp_denied": False,
                "processes": [{"pid": 1, "name": "init", "ticks": 5, "rss": 1024}],
            }

        monitor = RemoteMonitor(collect=collect, interval=0)
        server = {
            "id": "a" * 32,
            "address": "203.0.113.5",
            "port": 22,
            "username": "monitor",
            "password": "secret-pass",
        }
        first = monitor.snapshot(server, now=100)
        second = monitor.snapshot(server, now=105)
        self.assertEqual(first["host"]["hostname"], "remote-host")
        self.assertIsNone(first["cpu"]["percent"])
        self.assertEqual(second["cpu"]["percent"], 50.0)
        self.assertEqual(second["network"]["rx_bps"], 20.0)
        self.assertIsNone(second["error"])
        self.assertEqual(second["disk"]["rows"][0]["mount"], "/")

        down = RemoteMonitor(collect=lambda *args: None, interval=0)
        failed = down.snapshot(server, now=1)
        self.assertEqual(failed["error"], "Unable to reach this server.")
        self.assertNotIn("SECRET_PATH", json.dumps(failed))


class _Result:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


if __name__ == "__main__":
    unittest.main()
