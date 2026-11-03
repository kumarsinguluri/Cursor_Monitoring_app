"""Check the single admin password against a hash. Never store the password."""

from werkzeug.security import check_password_hash

ADMIN_USERNAME = "admin"


def verify_login(username, password, password_hash):
    """Return True only when the username is admin and the password matches."""
    candidate = password if isinstance(password, str) else ""
    matches = False
    try:
        if isinstance(password_hash, str) and password_hash:
            matches = check_password_hash(password_hash, candidate)
    except Exception:
        matches = False
    return username == ADMIN_USERNAME and matches
