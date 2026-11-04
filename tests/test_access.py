import os
import socket
import unittest
from tempfile import TemporaryDirectory

from tests.support import login, make_app


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.password = "correct-horse"
        self.app = make_app(os.path.join(self.tmp.name, "servers.json"), self.password)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_home_is_blocked_when_logged_out(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_anonymous_data_requests_redirect_to_login(self):
        for path in ("/api/metrics", "/metrics/fragment", "/servers/new"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_data_request_after_logout_redirects(self):
        login(self.client, self.password)
        self.client.post("/logout")
        response = self.client.get("/api/metrics")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))

    def test_signed_in_data_is_read_only(self):
        login(self.client, self.password)
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(socket.gethostname().encode(), page.data)
        self.assertIn(b"Hostname", page.data)
        self.assertIn(b"CPU", page.data)
        self.assertIn(b"Memory", page.data)
        self.assertIn(b"Network", page.data)
        self.assertIn(b"Disk", page.data)
        self.assertNotIn(b'name="command"', page.data)
        self.assertEqual(self.client.post("/").status_code, 405)
        self.assertEqual(self.client.post("/api/metrics").status_code, 405)

        payload = self.client.get("/api/metrics")
        self.assertEqual(payload.status_code, 200)
        body = payload.get_json()
        for key in ("host", "cpu", "memory", "network", "disk", "ports", "processes", "history"):
            self.assertIn(key, body)
        fragment = self.client.get("/metrics/fragment")
        self.assertEqual(fragment.status_code, 200)
        self.assertIn(b"Load average", fragment.data)
        self.assertNotIn(b"<form", fragment.data.lower())


if __name__ == "__main__":
    unittest.main()
