import os
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import create_app


def make_app(servers_path, password="correct-horse", users_path=None):
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["ADMIN_PASSWORD_HASH"] = generate_password_hash(
        password, method="pbkdf2:sha256:1000"
    )
    if users_path is None:
        users_path = str(Path(servers_path).with_name("users.json"))
    app = create_app(
        servers_path=servers_path,
        users_path=users_path,
        start_collector=False,
        load_env_file=False,
    )
    app.config["TESTING"] = True
    return app


def login(client, password="correct-horse", username="admin"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
    )
