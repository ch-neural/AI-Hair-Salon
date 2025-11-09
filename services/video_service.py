"""影片生成服務封裝，供 live-demo 使用。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional


def _resolve_video_service():
    """動態載入 KlingAI Video Service。"""
    try:
        from common.services.klingai_video_service import KlingAIVideoService  # type: ignore
        return KlingAIVideoService
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

        from common.services.klingai_video_service import KlingAIVideoService  # type: ignore

        return KlingAIVideoService


class LiveDemoVideoService:
    """封裝 KlingAI Video Service 以符合 live-demo 需求。"""

    def __init__(self, project_root: Path, demo_root: Path) -> None:
        self._project_root = project_root
        self._demo_root = demo_root
        
        # Determine outputs directory
        outputs_dir = demo_root / "static" / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine settings path
        local_settings = demo_root / "data" / "settings.json"
        parent_settings = project_root / "data" / "settings.json"
        settings_path = str(local_settings) if local_settings.exists() else str(parent_settings)
        
        # Initialize KlingAI Video Service
        KlingAIVideoService = _resolve_video_service()
        self._service = KlingAIVideoService(
            outputs_dir=str(outputs_dir),
            settings_json_path=settings_path
        )
        
        print(f"[LiveDemoVideoService] Initialized with outputs_dir={outputs_dir}")

    def generate_video(
        self,
        image_path: str,
        prompt: str = "保持微笑，慢慢地從正面輕柔地左右轉頭，展示髮型的側面和背面，動作自然流暢，充滿自信，最後回到正面微笑看鏡頭。整個過程優雅且專業，就像髮型設計師展示作品一樣。",
        duration: int = 5,
        session_id: Optional[str] = None,
    ) -> Dict:
        """啟動影片生成任務。
        
        默認動作：展示髮型的專業動作
        - 保持微笑
        - 慢慢左右轉頭
        - 展示側面和背面
        - 動作自然流暢
        - 最後回到正面看鏡頭
        """
        print(f"[LiveDemoVideoService] Generating video for {image_path}")
        print(f"[LiveDemoVideoService] Prompt: {prompt}")
        return self._service.generate_video(
            image_path=image_path,
            prompt=prompt,
            duration=duration,
            session_id=session_id
        )

    def poll_video_task(self, task_id: str) -> Dict:
        """輪詢影片生成狀態。"""
        return self._service.poll_video_task(task_id)
    
    def is_enabled(self) -> bool:
        """檢查影片生成服務是否已配置。"""
        return bool(self._service.access_key and self._service.secret_key)

