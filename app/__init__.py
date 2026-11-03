import os
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parent.parent


def create_app(servers_path=None, start_collector=True, load_env_file=True):
    if load_env_file:
        _load_env_file()
    secret = os.environ.get("SECRET_KEY", "").strip()
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "").strip()
    if not secret:
        raise RuntimeError("SECRET_KEY is not set")
    if not password_hash:
        raise RuntimeError("ADMIN_PASSWORD_HASH is not set")

    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    app.config["SECRET_KEY"] = secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    app.config["SERVERS_PATH"] = str(servers_path or (ROOT / "data" / "servers.json"))

    from app.charts import cpu_chart, memory_chart, network_chart
    from app.collect import Monitor
    from app.routes import register_routes

    app.monitor = Monitor()
    app.jinja_env.globals.update(
        cpu_chart=cpu_chart,
        memory_chart=memory_chart,
        network_chart=network_chart,
    )
    register_routes(app)
    if start_collector:
        app.monitor.start()
    return app


def _load_env_file():
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Do not override variables already set. Quote hashes in .env so "$" is kept.
    load_dotenv(env_path, override=False)
