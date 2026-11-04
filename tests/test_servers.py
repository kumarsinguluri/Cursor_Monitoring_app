import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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
        self.assertEqual(set(saved[0]), {"id", "name", "address"})

    def test_hostname_is_accepted_and_not_stored(self):
        result = add_server(self.path, "local", "MyHost", "myhost")
        self.assertTrue(result["ok"])
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        self.assertNotIn("MyHost", text)
        self.assertNotIn("myhost", text)

    def test_reject_non_local_address(self):
        result = add_server(self.path, "remote", "8.8.8.8", "myhost")
        self.assertFalse(result["ok"])
        self.assertEqual(result["message"], "Only this machine is accepted.")
        self.assertFalse(self.path.exists())

    def test_remove_only_edits_the_json_file(self):
        added = add_server(self.path, "local", "", "myhost")
        notes = self.path.parent / "notes.txt"
        notes.write_text("keep", encoding="utf-8")
        self.assertTrue(remove_server(self.path, added["server"]["id"]))
        self.assertEqual(load_servers(self.path), [])
        self.assertEqual(notes.read_text(encoding="utf-8"), "keep")
        self.assertFalse(remove_server(self.path, added["server"]["id"]))

    def test_remote_row_in_the_file_is_ignored(self):
        self.path.write_text(
            json.dumps(
                [
                    {
                        "id": "a" * 32,
                        "name": "elsewhere",
                        "address": "8.8.8.8",
                        "command": "id",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual(load_servers(self.path), [])


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
            data={"name": "nope", "address": "203.0.113.5"},
        )
        self.assertIn(b"Only this machine is accepted.", rejected.data)
        self.assertFalse(os.path.exists(self.path))

        ignored = self.client.post(
            "/servers/new",
            data={
                "name": "this machine",
                "address": "127.0.0.1",
                "host": "evil.example",
                "port": "22",
                "username": "root",
                "command": "rm -rf /",
            },
            follow_redirects=True,
        )
        self.assertEqual(ignored.status_code, 200)
        saved = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["address"], "127.0.0.1")
        self.assertEqual(set(saved[0]), {"id", "name", "address"})
        text = Path(self.path).read_text(encoding="utf-8")
        self.assertNotIn("evil.example", text)
        self.assertNotIn("root", text)
        self.assertNotIn("rm -rf", text)
        self.assertIn(b"this machine", ignored.data)

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
        self.assertEqual([row["name"] for row in saved], ["this machine", "second"])
        self.assertEqual({row["address"] for row in saved}, {"127.0.0.1"})
        self.assertIn(b"second", duplicate.data)

        self.client.post(f"/servers/{saved[0]['id']}/remove")
        removed = self.client.post(
            f"/servers/{saved[1]['id']}/remove",
            follow_redirects=True,
        )
        self.assertEqual(json.loads(Path(self.path).read_text(encoding="utf-8")), [])
        self.assertIn(b"No servers yet", removed.data)


if __name__ == "__main__":
    unittest.main()
