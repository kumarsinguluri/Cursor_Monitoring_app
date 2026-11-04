"""Pages. Metrics are view-only. Writes are the server list and the user list."""

import os
import socket

from flask import abort, current_app, jsonify, redirect, render_template, request, session, url_for

from app.auth import verify_login
from app.servers import ServerStoreError, add_server, load_servers, remove_server
from app.users import (
    UserStoreError,
    add_user,
    password_matches,
    public_usernames,
    remove_user,
)

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
        error = None
        if request.method == "POST":
            # host, port, username, and command are ignored so this cannot open SSH.
            name = request.form.get("name", "")
            address = request.form.get("address", "")
            result = add_server(_path(), name, address, hostname)
            if result["ok"]:
                return redirect(url_for("home"))
            error = result["message"]
        return _render_server_form(hostname, name, address, error)

    @app.post("/users")
    def user_add():
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        result = add_user(_users_path(), username, password)
        if result["ok"]:
            return redirect(url_for("server_new"))
        return _render_server_form(
            _hostname(),
            "",
            "",
            None,
            user_error=result["message"],
            user_name=username if isinstance(username, str) else "",
        )

    @app.post("/users/<username>/remove")
    def user_remove(username):
        try:
            remove_user(_users_path(), username)
        except UserStoreError:
            pass
        if session.get("user") == username:
            session.clear()
            return redirect(url_for("login"))
        return redirect(url_for("server_new"))

    @app.post("/servers/<server_id>/remove")
    def server_remove(server_id):
        try:
            remove_server(_path(), server_id)
        except ServerStoreError:
            pass
        return redirect(url_for("home"))

    @app.get("/servers/<server_id>")
    def server_detail(server_id):
        try:
            servers = load_servers(_path())
        except ServerStoreError:
            abort(404)
        server = next((item for item in servers if item["id"] == server_id), None)
        if server is None:
            abort(404)
        return render_template(
            "detail.html",
            server=server,
            metrics=current_app.monitor.snapshot(),
        )

    @app.get("/api/metrics")
    def api_metrics():
        return jsonify(current_app.monitor.snapshot())

    @app.get("/metrics/fragment")
    def metrics_fragment():
        return render_template("_metrics.html", metrics=current_app.monitor.snapshot())

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


def _render_server_form(hostname, name, address, error, user_error=None, user_name=""):
    try:
        names = public_usernames(_users_path())
        users_error = None
    except UserStoreError:
        names = []
        users_error = "User list unavailable."
    users = [{"username": "admin", "builtin": True}]
    users.extend({"username": item, "builtin": False} for item in names)
    return render_template(
        "server_form.html",
        error=error,
        name=name,
        address=address,
        hostname=hostname or "this machine",
        users=users,
        users_error=users_error,
        user_error=user_error,
        user_name=user_name,
    )


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
