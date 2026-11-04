"""Server list. This machine is stored as loopback. Other hosts keep SSH details."""

import ipaddress
import json
import os
import re
import threading
import uuid
from pathlib import Path

LOCAL_ADDRESSES = {"127.0.0.1", "localhost", "::1"}
LOCAL_STORED_ADDRESS = "127.0.0.1"
_ID = re.compile(r"[0-9a-f]{32}")
_HOSTNAME = re.compile(
    r"(?=.{1,253}$)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
_USERNAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}")
_LOCK = threading.Lock()


class ServerStoreError(Exception):
    """The server list file could not be read. The message has no path."""


def load_servers(path):
    """Return saved servers without SSH passwords."""
    return [_public(row) for row in _load_rows(path)]


def server_record(path, server_id):
    """Return one full record, including the SSH password, or None."""
    for row in _load_rows(path):
        if row["id"] == server_id:
            return row
    return None


def add_server(path, name, address, hostname, port=None, username=None, password=None):
    """Store a display name and a host. A command is not accepted or stored.

    This machine is saved as 127.0.0.1 with no SSH password. Any other hostname
    or IP is saved with its port, username, and password.
    """
    with _LOCK:
        try:
            current = _load_rows(path)
        except ServerStoreError:
            return {"ok": False, "message": "Server list unavailable.", "server": None}
        cleaned = clean_display_name(name)
        if cleaned is None:
            return {"ok": False, "message": "Enter a server name.", "server": None}
        stored_address = normalize_address(address, hostname)
        if stored_address is None:
            return {
                "ok": False,
                "message": "Enter a hostname or IP address.",
                "server": None,
            }
        local = stored_address == LOCAL_STORED_ADDRESS
        if local:
            server = {
                "id": uuid.uuid4().hex,
                "name": cleaned,
                "address": stored_address,
                "port": 22,
                "username": "",
            }
        else:
            stored_port = normalize_port(port)
            if stored_port is None:
                return {
                    "ok": False,
                    "message": "Enter a port from 1 to 65535.",
                    "server": None,
                }
            stored_username = normalize_username(username)
            if stored_username is None:
                return {
                    "ok": False,
                    "message": "Enter the SSH username.",
                    "server": None,
                }
            stored_password = normalize_password(password)
            if stored_password is None:
                return {
                    "ok": False,
                    "message": "Enter the SSH password.",
                    "server": None,
                }
            server = {
                "id": uuid.uuid4().hex,
                "name": cleaned,
                "address": stored_address,
                "port": stored_port,
                "username": stored_username,
                "password": stored_password,
            }
        _write(path, current + [server])
        return {"ok": True, "message": "", "server": _public(server)}


def remove_server(path, server_id):
    """Drop one entry from the JSON file. This does not change the host."""
    with _LOCK:
        current = _load_rows(path)
        remaining = [server for server in current if server["id"] != server_id]
        if len(remaining) == len(current):
            return False
        _write(path, remaining)
        return True


def is_local_address(address, hostname):
    if address is None:
        return True
    text = str(address).strip()
    if text == "":
        return True
    if any(char.isspace() for char in text):
        return False
    lowered = text.lower()
    if lowered in LOCAL_ADDRESSES:
        return True
    host = str(hostname or "").strip().lower()
    return bool(host) and lowered == host


def normalize_address(address, hostname):
    """Return a stored host, or None when the value is not a hostname or IP."""
    if address is None or str(address).strip() == "":
        return LOCAL_STORED_ADDRESS
    text = str(address).strip()
    if text.startswith("-") or any(char.isspace() for char in text):
        return None
    if any(char in text for char in "/\\@,;%"):
        return None
    if is_local_address(text, hostname):
        return LOCAL_STORED_ADDRESS
    try:
        parsed = ipaddress.ip_address(text)
    except ValueError:
        parsed = None
    if parsed is not None:
        return str(parsed)
    if _HOSTNAME.fullmatch(text):
        return text
    return None


def normalize_port(port):
    if port is None or str(port).strip() == "":
        return 22
    try:
        value = int(str(port).strip())
    except (TypeError, ValueError):
        return None
    if value < 1 or value > 65535:
        return None
    return value


def normalize_username(username):
    if username is None:
        return None
    text = str(username).strip()
    if _USERNAME.fullmatch(text) is None:
        return None
    return text


def normalize_password(password):
    if not isinstance(password, str) or password == "":
        return None
    if len(password) > 128:
        return None
    if any(char in password for char in "\x00\r\n"):
        return None
    return password


def clean_display_name(name):
    if not isinstance(name, str):
        return None
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 80:
        return None
    if any(ord(char) < 32 for char in cleaned):
        return None
    return cleaned


def _load_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServerStoreError("Server list unavailable.") from exc
    if not isinstance(data, list):
        raise ServerStoreError("Server list unavailable.")
    servers = []
    for row in data:
        clean = _clean_row(row)
        if clean is not None:
            servers.append(clean)
    return servers


def _public(server):
    return {
        "id": server["id"],
        "name": server["name"],
        "address": server["address"],
        "port": server["port"],
        "username": server["username"],
    }


def _clean_row(row):
    if not isinstance(row, dict):
        return None
    server_id = row.get("id")
    name = row.get("name")
    if not isinstance(server_id, str) or not _ID.fullmatch(server_id):
        return None
    if not isinstance(name, str):
        return None
    cleaned = clean_display_name(name)
    if cleaned is None:
        return None
    raw_address = row.get("address")
    if not isinstance(raw_address, str) or not raw_address.strip():
        return None
    address = normalize_address(raw_address, "")
    if address is None:
        return None
    port = normalize_port(row.get("port", 22))
    if port is None:
        return None
    if address == LOCAL_STORED_ADDRESS:
        return {
            "id": server_id,
            "name": cleaned,
            "address": address,
            "port": 22,
            "username": "",
        }
    username = normalize_username(row.get("username", ""))
    if username is None:
        return None
    cleaned_row = {
        "id": server_id,
        "name": cleaned,
        "address": address,
        "port": port,
        "username": username,
    }
    password = row.get("password", "")
    if isinstance(password, str) and password and normalize_password(password):
        cleaned_row["password"] = password
    return cleaned_row


def _write(path, servers):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(servers, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
