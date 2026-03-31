from __future__ import annotations

import logging

from flask import Flask, jsonify

from .config import Settings
from .service import SyncService


logging.basicConfig(level=logging.INFO)


def create_app() -> Flask:
    app = Flask(__name__)
    settings = Settings.from_env()
    service = SyncService(settings)

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.post("/sync")
    def sync():
        result = service.run()
        return jsonify(result.as_dict())

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

