"""Local accounts besides the built-in admin. Passwords are stored as hashes."""

import json
import os
import re
import threading
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}")
_LOCK = threading.Lock()


class UserStoreError(Exception):
    """The user file could not be read. The message has no path."""


def load_users(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UserStoreError("User list unavailable.") from exc
    if not isinstance(data, list):
        raise UserStoreError("User list unavailable.")
    users = []
    for row in data:
        clean = _clean_row(row)
        if clean is not None:
            users.append(clean)
    return users


def public_usernames(path):
    return [user["username"] for user in load_users(path)]


def add_user(path, username, password):
    """Save a username and a password hash. The password is not written."""
    cleaned = clean_username(username)
    if cleaned is None:
        return {
            "ok": False,
            "message": "Use a username of letters, numbers, dots, hyphens, or underscores.",
        }
    if cleaned.lower() == "admin":
        return {"ok": False, "message": "The admin account already exists."}
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        return {"ok": False, "message": "Use a password of at least 8 characters."}
    with _LOCK:
        try:
            current = load_users(path)
        except UserStoreError:
            return {"ok": False, "message": "User list unavailable."}
        if any(user["username"].lower() == cleaned.lower() for user in current):
            return {"ok": False, "message": "That username is already in the list."}
        current.append(
            {
                "username": cleaned,
                "password_hash": generate_password_hash(password),
            }
        )
        _write(path, current)
        return {"ok": True, "message": ""}


def remove_user(path, username):
    """Drop one account from the JSON file. Admin cannot be removed here."""
    if not isinstance(username, str) or username.lower() == "admin":
        return False
    with _LOCK:
        current = load_users(path)
        remaining = [user for user in current if user["username"] != username]
        if len(remaining) == len(current):
            return False
        _write(path, remaining)
        return True


def password_matches(path, username, password):
    candidate = password if isinstance(password, str) else ""
    if not isinstance(username, str) or not username:
        return False
    try:
        users = load_users(path)
    except UserStoreError:
        return False
    match = next((user for user in users if user["username"] == username), None)
    if match is None:
        return False
    try:
        return check_password_hash(match["password_hash"], candidate)
    except Exception:
        return False


def clean_username(username):
    if not isinstance(username, str):
        return None
    cleaned = username.strip()
    if _NAME.fullmatch(cleaned) is None:
        return None
    return cleaned


def _clean_row(row):
    if not isinstance(row, dict):
        return None
    username = row.get("username")
    password_hash = row.get("password_hash")
    if not isinstance(username, str) or clean_username(username) != username:
        return None
    if username.lower() == "admin":
        return None
    if not isinstance(password_hash, str) or not password_hash or any(
        char.isspace() for char in password_hash
    ):
        return None
    return {"username": username, "password_hash": password_hash}


def _write(path, users):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(users, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
