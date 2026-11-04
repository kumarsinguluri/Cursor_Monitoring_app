import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.users import add_user, load_users, password_matches, public_usernames, remove_user
from tests.support import login, make_app


class UserStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "users.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_stores_a_hash_and_lists_the_username(self):
        result = add_user(self.path, "ada", "long-password")
        self.assertTrue(result["ok"])
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("long-password", text)
        saved = json.loads(text)
        self.assertEqual(saved[0]["username"], "ada")
        self.assertEqual(set(saved[0]), {"username", "password_hash"})
        self.assertEqual(public_usernames(self.path), ["ada"])
        self.assertTrue(password_matches(self.path, "ada", "long-password"))
        self.assertFalse(password_matches(self.path, "ada", "wrong-password"))

    def test_reject_duplicate_admin_and_short_password(self):
        self.assertEqual(
            add_user(self.path, "admin", "long-password")["message"],
            "The admin account already exists.",
        )
        self.assertFalse(self.path.exists())
        short = add_user(self.path, "ada", "short")
        self.assertFalse(short["ok"])
        self.assertIn("8 characters", short["message"])
        add_user(self.path, "ada", "long-password")
        again = add_user(self.path, "Ada", "another-password")
        self.assertFalse(again["ok"])
        self.assertEqual(len(load_users(self.path)), 1)

    def test_remove_edits_only_the_user_file(self):
        add_user(self.path, "ada", "long-password")
        notes = self.path.parent / "notes.txt"
        notes.write_text("keep", encoding="utf-8")
        self.assertFalse(remove_user(self.path, "admin"))
        self.assertTrue(remove_user(self.path, "ada"))
        self.assertEqual(load_users(self.path), [])
        self.assertEqual(notes.read_text(encoding="utf-8"), "keep")


class UserPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.servers = os.path.join(self.tmp.name, "servers.json")
        self.users = os.path.join(self.tmp.name, "users.json")
        self.app = make_app(self.servers, users_path=self.users)
        self.client = self.app.test_client()
        login(self.client)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_server_form_asks_for_ssh_and_hides_the_user_list(self):
        page = self.client.get("/servers/new")
        self.assertIn(b"SSH host", page.data)
        self.assertIn(b"SSH username", page.data)
        self.assertIn(b"SSH password", page.data)
        self.assertNotIn(b"All users", page.data)
        self.assertNotIn(b"Add user", page.data)

    def test_added_account_can_sign_in(self):
        add_user(self.users, "ada", "long-password")
        saved = json.loads(Path(self.users).read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["username"], "ada")
        self.assertNotIn("long-password", saved[0]["password_hash"])
        self.client.post("/logout")
        signed_in = login(self.client, password="long-password", username="ada")
        self.assertEqual(signed_in.status_code, 302)
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)

    def test_anonymous_cannot_add_a_user(self):
        self.client.post("/logout")
        response = self.client.post(
            "/users",
            data={"username": "ada", "password": "long-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        self.assertFalse(os.path.exists(self.users))


if __name__ == "__main__":
    unittest.main()
