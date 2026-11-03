from pathlib import Path

from flask import Flask, render_template

ROOT = Path(__file__).resolve().parent.parent


def create_app():
    app = Flask(
        __name__,
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )

    @app.get("/")
    def home():
        return render_template("home.html")

    return app
