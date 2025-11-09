"""Live demo Raspberry Pi 觸控換髮型系統 Flask 應用。"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask


def _ensure_package_imports() -> None:
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    for target in (project_root, current_dir):
        insert_path = str(target)
        if insert_path not in sys.path:
            sys.path.insert(0, insert_path)


try:  # 支援以模組或獨立腳本啟動
    from .config import LiveDemoConfig
    from .routes import admin, api, user
    from .services import GarmentRepository, TryOnHistoryRepository, LiveDemoTryOnProvider, LiveDemoVideoService, PhotoService, PhotoValidator
except ImportError:  # pragma: no cover - 僅於 python app.py 觸發
    _ensure_package_imports()
    from config import LiveDemoConfig  # type: ignore
    from routes import admin, api, user  # type: ignore
    from services import (  # type: ignore
        GarmentRepository,
        TryOnHistoryRepository,
        LiveDemoTryOnProvider,
        LiveDemoVideoService,
        PhotoService,
        PhotoValidator,
    )


def create_app() -> Flask:
    config = LiveDemoConfig.load()
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = config.secret_key
    app.config["LIVE_DEMO_CONFIG"] = config

    components = {
        "garment_repo": GarmentRepository(config.garment_data_file),
        "history_repo": TryOnHistoryRepository(config.history_data_file),
        "photo_service": PhotoService(config.user_photo_dir, config.garment_image_dir),
        "photo_validator": PhotoValidator(config.settings_file),
        "tryon_provider": LiveDemoTryOnProvider(config.project_root, config.demo_root),
        "video_service": LiveDemoVideoService(config.project_root, config.demo_root),
    }
    app.extensions["live_demo_components"] = components

    app.register_blueprint(user.user_bp)
    app.register_blueprint(admin.admin_bp)
    app.register_blueprint(api.api_bp)

    return app


def main() -> None:
    app = create_app()
    app.run(host="0.0.0.0", port=6055, debug=False)


if __name__ == "__main__":
    main()

