"""Local server list. Entries are display names for this machine only."""

import json
import os
import re
import threading
import uuid
from pathlib import Path

LOCAL_ADDRESSES = {"127.0.0.1", "localhost", "::1"}
STORED_ADDRESS = "127.0.0.1"
_ID = re.compile(r"[0-9a-f]{32}")
_LOCK = threading.Lock()


class ServerStoreError(Exception):
    """The server list file could not be read. The message has no path."""


def load_servers(path):
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


def add_server(path, name, address, hostname):
    """Store a display name and 127.0.0.1, or reject the entry.

    Host, port, username, and command are not arguments here and are never stored.
    """
    with _LOCK:
        try:
            current = load_servers(path)
        except ServerStoreError:
            return {"ok": False, "message": "Server list unavailable.", "server": None}
        cleaned = clean_display_name(name)
        if cleaned is None:
            return {"ok": False, "message": "Enter a display name.", "server": None}
        if not is_local_address(address, hostname):
            return {
                "ok": False,
                "message": "Only this machine is accepted.",
                "server": None,
            }
        server = {
            "id": uuid.uuid4().hex,
            "name": cleaned,
            "address": STORED_ADDRESS,
        }
        _write(path, current + [server])
        return {"ok": True, "message": "", "server": server}


def remove_server(path, server_id):
    """Drop one entry from the JSON file. This does not change the host."""
    with _LOCK:
        current = load_servers(path)
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
    if any(ch.isspace() for ch in text):
        return False
    lowered = text.lower()
    if lowered in LOCAL_ADDRESSES:
        return True
    host = str(hostname or "").strip().lower()
    return bool(host) and lowered == host


def clean_display_name(name):
    if not isinstance(name, str):
        return None
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 80:
        return None
    if any(ord(ch) < 32 for ch in cleaned):
        return None
    return cleaned


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
    if row.get("address") != STORED_ADDRESS:
        return None
    return {"id": server_id, "name": cleaned, "address": STORED_ADDRESS}


def _write(path, servers):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(servers, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
