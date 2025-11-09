"""Live demo 應用設定模組。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LiveDemoConfig:
    """封裝觸控換髮型系統的設定值。"""

    secret_key: str
    admin_username: str
    admin_password: str
    project_root: Path
    demo_root: Path

    @property
    def upload_dir(self) -> Path:
        return self.demo_root / "uploads"

    @property
    def user_photo_dir(self) -> Path:
        return self.demo_root / "static" / "inputs"

    @property
    def garment_image_dir(self) -> Path:
        return self.demo_root / "static" / "garments"

    @property
    def tryon_output_dir(self) -> Path:
        return self.demo_root / "static" / "outputs"

    @property
    def data_dir(self) -> Path:
        return self.demo_root / "data"

    @property
    def garment_data_file(self) -> Path:
        return self.data_dir / "garments.json"
    
    @property
    def settings_file(self) -> Path:
        return self.data_dir / "settings.json"
    
    @property
    def history_data_file(self) -> Path:
        return self.data_dir / "tryon_history.json"
    
    @property
    def admin_credentials_file(self) -> Path:
        return self.data_dir / "admin.json"

    @classmethod
    def load(cls) -> "LiveDemoConfig":
        """從環境變數建構設定，並確保必要目錄存在。"""

        demo_root = Path(__file__).resolve().parent
        project_root = demo_root.parent

        secret_key = os.environ.get("LIVE_DEMO_SECRET_KEY", "live-demo-touch-tryon")
        admin_username = os.environ.get("LIVE_DEMO_ADMIN_USER", "admin")
        admin_password = os.environ.get("LIVE_DEMO_ADMIN_PASS", "storepi")

        # 初始化基本設定
        config = cls(
            secret_key=secret_key,
            admin_username=admin_username,
            admin_password=admin_password,
            project_root=project_root,
            demo_root=demo_root,
        )

        config.upload_dir.mkdir(parents=True, exist_ok=True)
        config.user_photo_dir.mkdir(parents=True, exist_ok=True)
        config.garment_image_dir.mkdir(parents=True, exist_ok=True)
        config.tryon_output_dir.mkdir(parents=True, exist_ok=True)
        config.data_dir.mkdir(parents=True, exist_ok=True)

        # 如果存在 admin.json，從檔案讀取管理員帳密（優先於環境變數）
        if config.admin_credentials_file.exists():
            try:
                admin_data = json.loads(
                    config.admin_credentials_file.read_text(encoding="utf-8")
                )
                if isinstance(admin_data, dict):
                    config.admin_username = admin_data.get("username", admin_username)
                    config.admin_password = admin_data.get("password", admin_password)
                    print(f"[LiveDemoConfig] 已從 {config.admin_credentials_file} 載入管理員帳密")
            except Exception as e:
                print(f"[LiveDemoConfig] 讀取 admin.json 失敗: {e}")

        if not config.garment_data_file.exists():
            config.garment_data_file.write_text("[]", encoding="utf-8")
        
        # 確保 settings.json 存在，使用預設值（若不存在）
        # 這確保 live-demo 完全獨立，不依賴上層的設定檔
        if not config.settings_file.exists():
            default_settings = {
                "GEMINI_API_KEY": "",
                "GEMINI_MODEL": "gemini-2.5-flash-image",
                "GEMINI_LLM": "gemini-2.5-flash",
                "GEMINI_SAFETY_SETTINGS": "BLOCK_ONLY_HIGH",
                "KLINGAI_VIDEO_ACCESS_KEY": "",
                "KLINGAI_VIDEO_SECRET_KEY": "",
                "KLINGAI_VIDEO_MODEL": "kling-v2-5-turbo",
                "KLINGAI_VIDEO_MODE": "std",
                "KLINGAI_VIDEO_DURATION": "5",
                "VENDOR_TRYON": "Gemini"
            }
            config.settings_file.write_text(
                json.dumps(default_settings, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"[LiveDemoConfig] 已創建預設設定檔: {config.settings_file}")

        return config

