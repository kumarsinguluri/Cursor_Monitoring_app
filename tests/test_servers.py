import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.remote import RemoteMonitor
from app.servers import add_server, load_servers, remove_server
from tests.support import login, make_app


class ServerStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "servers.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_stores_name_and_loopback(self):
        result = add_server(self.path, "  Local box  ", "localhost", "other")
        self.assertTrue(result["ok"])
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["name"], "Local box")
        self.assertEqual(saved[0]["address"], "127.0.0.1")
        self.assertEqual(saved[0]["port"], 22)
        self.assertEqual(saved[0]["username"], "")
        self.assertNotIn("password", saved[0])

    def test_hostname_is_accepted_and_not_stored(self):
        result = add_server(self.path, "local", "MyHost", "myhost")
        self.assertTrue(result["ok"])
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        self.assertNotIn("MyHost", text)
        self.assertNotIn("myhost", text)

    def test_remote_server_stores_ssh_details_not_a_command(self):
        missing = add_server(self.path, "remote", "8.8.8.8", "myhost")
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["message"], "Enter the SSH username.")
        self.assertFalse(self.path.exists())
        result = add_server(
            self.path,
            "remote",
            "8.8.8.8",
            "myhost",
            port="2222",
            username="monitor",
            password="secret-pass",
        )
        self.assertTrue(result["ok"])
        self.assertNotIn("password", result["server"])
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["address"], "8.8.8.8")
        self.assertEqual(saved[0]["port"], 2222)
        self.assertEqual(saved[0]["username"], "monitor")
        self.assertEqual(saved[0]["password"], "secret-pass")
        self.assertNotIn("command", saved[0])

    def test_remove_only_edits_the_json_file(self):
        added = add_server(self.path, "local", "", "myhost")
        notes = self.path.parent / "notes.txt"
        notes.write_text("keep", encoding="utf-8")
        self.assertTrue(remove_server(self.path, added["server"]["id"]))
        self.assertEqual(load_servers(self.path), [])
        self.assertEqual(notes.read_text(encoding="utf-8"), "keep")
        self.assertFalse(remove_server(self.path, added["server"]["id"]))

    def test_loaded_remote_row_drops_a_command(self):
        self.path.write_text(
            json.dumps(
                [
                    {
                        "id": "a" * 32,
                        "name": "elsewhere",
                        "address": "8.8.8.8",
                        "port": 22,
                        "username": "monitor",
                        "password": "secret-pass",
                        "command": "id",
                    }
                ]
            ),
            encoding="utf-8",
        )
        loaded = load_servers(self.path)
        self.assertEqual(loaded[0]["address"], "8.8.8.8")
        self.assertNotIn("password", loaded[0])
        self.assertNotIn("command", loaded[0])


class ServerPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "servers.json")
        self.password = "correct-horse"
        self.app = make_app(self.path, self.password)
        self.client = self.app.test_client()
        login(self.client, self.password)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_reject_and_remove_from_the_page(self):
        rejected = self.client.post(
            "/servers/new",
            data={"name": "nope", "address": "bad host"},
        )
        self.assertIn(b"Enter a hostname or IP address.", rejected.data)
        self.assertFalse(os.path.exists(self.path))

        ignored = self.client.post(
            "/servers/new",
            data={
                "name": "this machine",
                "address": "127.0.0.1",
                "host": "evil.example",
                "port": "22",
                "username": "root",
                "password": "secret-pass",
                "command": "rm -rf /",
            },
            follow_redirects=True,
        )
        self.assertEqual(ignored.status_code, 200)
        saved = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["address"], "127.0.0.1")
        self.assertEqual(saved[0]["username"], "")
        self.assertNotIn("password", saved[0])
        text = Path(self.path).read_text(encoding="utf-8")
        self.assertNotIn("evil.example", text)
        self.assertNotIn("root", text)
        self.assertNotIn("secret-pass", text)
        self.assertNotIn("rm -rf", text)
        self.assertIn(b"this machine", ignored.data)

        self.app.remote = RemoteMonitor(collect=_sample_payload, interval=0)
        remote = self.client.post(
            "/servers/new",
            data={
                "name": "dns",
                "address": "203.0.113.5",
                "port": "2222",
                "username": "monitor",
                "password": "secret-pass",
                "command": "rm -rf /",
            },
            follow_redirects=True,
        )
        self.assertEqual(remote.status_code, 200)
        saved = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(saved[1]["address"], "203.0.113.5")
        self.assertEqual(saved[1]["port"], 2222)
        self.assertEqual(saved[1]["username"], "monitor")
        self.assertEqual(saved[1]["password"], "secret-pass")
        text = Path(self.path).read_text(encoding="utf-8")
        self.assertNotIn("rm -rf", text)
        self.assertNotIn(b"secret-pass", remote.data)
        self.assertIn(b"monitor@203.0.113.5:2222", remote.data)
        self.assertIn(b"This machine", remote.data)
        self.assertIn(b"remote-host", remote.data)

        remote_detail = self.client.get(f"/servers/{saved[1]['id']}")
        self.assertEqual(remote_detail.status_code, 200)
        self.assertIn(b"remote-host", remote_detail.data)
        self.assertNotIn(b"secret-pass", remote_detail.data)

        detail = self.client.get(f"/servers/{saved[0]['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"read only", detail.data)

        duplicate = self.client.post(
            "/servers/new",
            data={"name": "second", "address": "127.0.0.1"},
            follow_redirects=True,
        )
        saved = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual([row["name"] for row in saved], ["this machine", "dns", "second"])
        self.assertEqual(saved[1]["address"], "203.0.113.5")
        self.assertIn(b"second", duplicate.data)

        self.client.post(f"/servers/{saved[0]['id']}/remove")
        self.client.post(f"/servers/{saved[1]['id']}/remove")
        removed = self.client.post(
            f"/servers/{saved[2]['id']}/remove",
            follow_redirects=True,
        )
        self.assertEqual(json.loads(Path(self.path).read_text(encoding="utf-8")), [])
        self.assertIn(b"No servers yet", removed.data)


def _sample_payload(*_args):
    return {
        "hostname": "remote-host",
        "uptime": "90 0\n",
        "load": "0.10 0.20 0.30 1/1 1\n",
        "cpu": "cpu  0 0 0 100 0 0 0 0\n",
        "mem": "MemTotal: 2048 kB\nMemAvailable: 1024 kB\n",
        "net": "  lo: 1000 0 0 0 0 0 0 0 400 0 0 0 0 0 0 0\n",
        "disks": [],
        "tcp": "",
        "tcp6": "",
        "tcp_denied": False,
        "processes": [],
    }


if __name__ == "__main__":
    unittest.main()
