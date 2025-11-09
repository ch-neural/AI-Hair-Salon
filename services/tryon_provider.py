"""封裝 TryOnService 以符合觸控展示需求。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def _resolve_tryon_service():
    try:
        from common.services.tryon_service import TryOnService  # type: ignore
        return TryOnService
    except ImportError:  # pragma: no cover - fallback for standalone execution
        import sys

        # live_tryon is at: 開發/live_tryon
        # common is at: 開發/storeTryon/common
        # So we need to go up to 開發 and then into storeTryon
        current_file = Path(__file__).resolve()
        dev_root = current_file.parents[2]  # 開發 directory
        store_tryon_root = dev_root / "storeTryon"
        
        insert_paths = [
            store_tryon_root,  # Add storeTryon to path so we can import common
            dev_root,  # Add dev root as well
        ]
        for path in insert_paths:
            if path.exists():
                path_str = str(path)
                if path_str not in sys.path:
                    sys.path.insert(0, path_str)

        from common.services.tryon_service import TryOnService  # type: ignore

        return TryOnService


TryOnService = _resolve_tryon_service()


class LiveDemoTryOnProvider:
    """提供展示專用的 TryOn 服務輔助函式。"""

    def __init__(self, project_root: Path, demo_root: Path) -> None:
        # 只使用 live-demo 本地的設定檔，不使用上層的設定
        settings_path = demo_root / "data" / "settings.json"
        self._service = TryOnService(
            base_dir=str(project_root),
            settings_json_path=str(settings_path)
        )
        self._apply_local_settings(project_root, demo_root)
        self._apply_demo_paths(demo_root)

    def start_session(
        self,
        *,
        user_image_data_url: str,
        garment_image_data_url: Optional[str],
        user_note: Optional[str] = None,
    ) -> Dict:
        return self._service.start_tryon(
            user_image_data_url=user_image_data_url,
            garment_image_url=garment_image_data_url,
            user_note=user_note,
        )

    def start_session_with_analysis(
        self,
        *,
        user_image_path: Path,
        user_image_data_url: str,
        garment: Any,
        garment_image_path: Path,
        garment_image_data_url: Optional[str],
        user_note: Optional[str] = None,
    ) -> Dict:
        garment_dict = garment.to_dict() if hasattr(garment, "to_dict") else vars(garment)
        print(
            f"[LiveDemoTryOnProvider] Start try-on (classic advanced) garment={garment_dict.get('name')} id={garment_dict.get('garment_id')}"
        )
        return self._service.start_tryon_advanced(
            user_image_data_url=user_image_data_url,
            garment_image_url=garment_image_data_url,
            user_note=user_note,
        )

    def check_session(self, session_id: str) -> Dict:
        return self._service.get_result(session_id)

    def _apply_demo_paths(self, demo_root: Path) -> None:
        static_root = demo_root / "static"
        inputs_dir = static_root / "inputs"
        outputs_dir = static_root / "outputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)
        self._service.legacy_inputs_dir = inputs_dir
        self._service.legacy_outputs_dir = outputs_dir
        self._service.outputs_dir = outputs_dir

    def _apply_local_settings(self, project_root: Path, demo_root: Path) -> None:
        gemini = getattr(self._service, "gemini", None)
        if gemini is None:
            return

        # 只讀取 live-demo 本地的設定檔，不 fallback 到上層
        local_path = demo_root / "data" / "settings.json"
        
        settings = self._load_settings(local_path)
        if not settings:
            print(f"[LiveDemoTryOnProvider] 未找到設定檔或設定為空: {local_path}")
            return

        api_key = settings.get("GEMINI_API_KEY") or getattr(gemini, "api_key", None)
        model = settings.get("GEMINI_MODEL") or getattr(gemini, "model_name", None)
        llm_model = settings.get("GEMINI_LLM") or getattr(gemini, "llm_model_name", None)

        gemini.api_key = api_key
        gemini.model_name = model
        gemini.llm_model_name = llm_model

        if hasattr(gemini, "_init_client") and gemini.api_key:
            try:
                gemini._init_client()  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - 重新初始化失敗時輸出說明
                print(f"[LiveDemoTryOnProvider] Gemini client 初始化失敗: {exc}")

    @staticmethod
    def _load_settings(path: Path) -> Optional[Dict[str, str]]:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception as exc:
            print(f"[LiveDemoTryOnProvider] 設定檔讀取失敗 {path}: {exc}")
        return None

