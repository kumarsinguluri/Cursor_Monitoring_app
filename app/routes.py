"""Pages. Metrics are view-only. The server list is the write path."""

import os
import socket

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for

from app.auth import verify_login
from app.servers import (
    ServerStoreError,
    add_server,
    is_local_address,
    load_servers,
    remove_server,
    server_record,
)
from app.users import UserStoreError, password_matches, public_usernames

_OPEN = {"login", "static"}


def register_routes(app):
    @app.before_request
    def require_login():
        if request.endpoint in _OPEN:
            return None
        if _signed_in():
            return None
        session.clear()
        return redirect(url_for("login"))

    @app.after_request
    def no_store(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def home():
        servers, error = _servers()
        return render_template(
            "home.html",
            servers=servers,
            servers_error=error,
            metrics=current_app.monitor.snapshot(),
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if _signed_in():
            return redirect(url_for("home"))
        if session.get("user"):
            session.clear()
        error = None
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
            if verify_login(username, password, password_hash):
                session.clear()
                session["user"] = "admin"
                return redirect(url_for("home"))
            if password_matches(_users_path(), username, password):
                session.clear()
                session["user"] = username
                return redirect(url_for("home"))
            error = "Invalid username or password."
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/servers/new", methods=["GET", "POST"])
    def server_new():
        hostname = _hostname()
        name = ""
        address = ""
        port = ""
        username = ""
        error = None
        if request.method == "POST":
            # A posted command is ignored. The SSH check uses a fixed read-only script.
            name = request.form.get("name", "")
            address = request.form.get("address", "")
            port = request.form.get("port", "")
            username = request.form.get("username", "")
            result = add_server(
                _path(),
                name,
                address,
                hostname,
                port=port,
                username=username,
                password=request.form.get("password", ""),
            )
            if result["ok"]:
                return redirect(url_for("home"))
            error = result["message"]
        return _render_server_form(hostname, name, address, port, username, error)

    @app.post("/servers/<server_id>/remove")
    def server_remove(server_id):
        try:
            remove_server(_path(), server_id)
        except ServerStoreError:
            pass
        return redirect(url_for("home"))

    @app.get("/servers/<server_id>")
    def server_detail(server_id):
        server = _find_server(server_id)
        if server is None:
            abort(404)
        return render_template(
            "detail.html",
            server=_public_server(server),
            metrics=_metrics_for(server),
        )

    @app.get("/api/metrics")
    def api_metrics():
        return jsonify(_metrics_for(None))

    @app.get("/metrics/fragment")
    def metrics_fragment():
        return render_template("_metrics.html", metrics=_metrics_for(None))

    @app.get("/servers/<server_id>/metrics")
    def server_metrics(server_id):
        server = _find_server(server_id)
        if server is None:
            abort(404)
        return render_template("_metrics.html", metrics=_metrics_for(server))

    @app.errorhandler(404)
    def not_found(_err):
        return render_template("error.html", message="That page does not exist."), 404

    @app.errorhandler(413)
    def too_large(_err):
        return render_template("error.html", message="That request is too large."), 413

    @app.errorhandler(500)
    def server_error(_err):
        return render_template("error.html", message="Something went wrong."), 500


def _signed_in():
    username = session.get("user")
    if username == "admin":
        return True
    if not isinstance(username, str) or not username:
        return False
    try:
        return username in public_usernames(_users_path())
    except UserStoreError:
        return False


def _render_server_form(hostname, name, address, port, username, error):
    return render_template(
        "server_form.html",
        error=error,
        name=name if isinstance(name, str) else "",
        address=address if isinstance(address, str) else "",
        port=port if isinstance(port, str) else "",
        username=username if isinstance(username, str) else "",
        hostname=hostname or "this machine",
    )


def _find_server(server_id):
    try:
        return server_record(_path(), server_id)
    except ServerStoreError:
        return None


def _metrics_for(server):
    if server is None or is_local_address(server.get("address"), _hostname()):
        snapshot = current_app.monitor.snapshot()
    else:
        snapshot = current_app.remote.snapshot(server)
    if isinstance(snapshot, dict) and "error" not in snapshot:
        snapshot = dict(snapshot)
        snapshot["error"] = None
    return snapshot


def _public_server(server):
    return {
        "id": server["id"],
        "name": server["name"],
        "address": server["address"],
        "port": server["port"],
        "username": server["username"],
    }


def _path():
    return current_app.config["SERVERS_PATH"]


def _users_path():
    return current_app.config["USERS_PATH"]


def _servers():
    try:
        return load_servers(_path()), None
    except ServerStoreError:
        return [], "Server list unavailable."


def _hostname():
    try:
        return socket.gethostname() or ""
    except OSError:
        return ""
