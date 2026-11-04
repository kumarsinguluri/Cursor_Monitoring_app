import logging
import os
import unittest
from tempfile import TemporaryDirectory

from tests.support import login, make_app


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.password = "correct-horse"
        self.app = make_app(os.path.join(self.tmp.name, "servers.json"), self.password)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_success_login_sets_session_and_cookie_flags(self):
        response = login(self.client, self.password)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))
        cookies = " ".join(response.headers.getlist("Set-Cookie")).lower()
        self.assertIn("httponly", cookies)
        self.assertIn("samesite=lax", cookies)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["user"], "admin")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertNotIn(self.password.encode(), home.data)
        self.assertNotIn(os.environ["ADMIN_PASSWORD_HASH"].encode(), home.data)

    def test_failed_login_keeps_the_user_signed_out(self):
        response = login(self.client, "wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid username or password.", response.data)
        self.assertNotIn(b"wrong-password", response.data)
        with self.client.session_transaction() as sess:
            self.assertNotIn("user", sess)
        home = self.client.get("/")
        self.assertEqual(home.status_code, 302)
        self.assertTrue(home.headers["Location"].endswith("/login"))

    def test_wrong_username_is_rejected(self):
        response = login(self.client, self.password, username="root")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid username or password.", response.data)
        with self.client.session_transaction() as sess:
            self.assertNotIn("user", sess)

    def test_login_ignores_an_external_next_url(self):
        response = self.client.post(
            "/login?next=https://evil.example/phish",
            data={"username": "admin", "password": self.password},
        )
        self.assertTrue(response.headers["Location"].endswith("/"))
        self.assertNotIn("evil.example", response.headers["Location"])

    def test_password_is_not_logged(self):
        secret = "super-unique-passphrase"
        grabbed = []

        class Grab(logging.Handler):
            def emit(self, record):
                grabbed.append(record.getMessage())

        handler = Grab()
        loggers = [
            logging.getLogger(),
            logging.getLogger("werkzeug"),
            self.app.logger,
        ]
        levels = []
        for logger in loggers:
            levels.append(logger.level)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
        try:
            self.client.post(
                "/login",
                data={"username": "admin", "password": secret},
            )
        finally:
            for logger, level in zip(loggers, levels):
                logger.removeHandler(handler)
                logger.setLevel(level)
        self.assertNotIn(secret, "\n".join(grabbed))

    def test_logout_ends_the_session(self):
        login(self.client, self.password)
        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_app_refuses_a_missing_secret(self):
        saved_secret = os.environ.pop("SECRET_KEY", None)
        saved_hash = os.environ.get("ADMIN_PASSWORD_HASH")
        try:
            os.environ["ADMIN_PASSWORD_HASH"] = "present"
            with self.assertRaises(RuntimeError) as raised:
                from app import create_app

                create_app(start_collector=False, load_env_file=False)
            self.assertEqual(str(raised.exception), "SECRET_KEY is not set")
            os.environ["SECRET_KEY"] = "test-secret-key"
            os.environ["ADMIN_PASSWORD_HASH"] = "  "
            with self.assertRaises(RuntimeError) as raised:
                from app import create_app

                create_app(start_collector=False, load_env_file=False)
            self.assertEqual(str(raised.exception), "ADMIN_PASSWORD_HASH is not set")
        finally:
            if saved_secret is None:
                os.environ.pop("SECRET_KEY", None)
            else:
                os.environ["SECRET_KEY"] = saved_secret
            if saved_hash is None:
                os.environ.pop("ADMIN_PASSWORD_HASH", None)
            else:
                os.environ["ADMIN_PASSWORD_HASH"] = saved_hash


if __name__ == "__main__":
    unittest.main()
