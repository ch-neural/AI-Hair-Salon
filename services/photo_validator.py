"""使用 LLM 驗證照片是否為半身正面照的服務。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


def _resolve_gemini_service():
    """動態解析 Gemini 服務。"""
    try:
        from common.services.gemini_service import GeminiService  # type: ignore
        return GeminiService
    except ImportError:  # pragma: no cover - fallback for standalone execution
        import sys

        # live_tryHair is at: 開發/live_tryHair
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

        from common.services.gemini_service import GeminiService  # type: ignore

        return GeminiService


GeminiService = _resolve_gemini_service()


class PhotoValidator:
    """驗證照片是否適合進行試換髮型的服務。"""

    def __init__(self, settings_path: Path) -> None:
        """
        初始化照片驗證器。
        
        Args:
            settings_path: 設定檔路徑，用於讀取 Gemini API 設定
        """
        self._settings_path = settings_path
        self._gemini = None
        self._init_gemini()

    def _init_gemini(self) -> None:
        """初始化 Gemini 服務。"""
        settings = self._load_settings()
        if not settings:
            print(f"[PhotoValidator] 無法載入設定檔: {self._settings_path}")
            return

        api_key = settings.get("GEMINI_API_KEY", "")
        llm_model = settings.get("GEMINI_LLM", "gemini-2.0-flash-exp")
        
        if not api_key:
            print("[PhotoValidator] 警告: GEMINI_API_KEY 未設定")
            return

        try:
            self._gemini = GeminiService(
                api_key=api_key,
                model_name="",  # 不使用圖像模型
                llm_model_name=llm_model
            )
            print(f"[PhotoValidator] Gemini LLM 初始化成功: {llm_model}")
        except Exception as exc:
            print(f"[PhotoValidator] Gemini 初始化失敗: {exc}")
            self._gemini = None

    def _load_settings(self) -> Optional[Dict[str, str]]:
        """載入設定檔。"""
        if not self._settings_path.exists():
            return None
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception as exc:
            print(f"[PhotoValidator] 設定檔讀取失敗 {self._settings_path}: {exc}")
        return None

    def validate_photo(self, image_data_url: str) -> Dict[str, any]:
        """
        驗證照片是否為半身正面照。
        
        Args:
            image_data_url: 圖片的 data URL (base64 編碼)
        
        Returns:
            Dict 包含:
            - is_valid: bool, 是否通過驗證
            - message: str, 說明訊息
            - details: str, 詳細分析（可選）
        """
        if not self._gemini:
            # 如果 Gemini 未初始化，跳過驗證
            print("[PhotoValidator] Gemini 未初始化，跳過驗證")
            return {
                "is_valid": True,
                "message": "照片驗證服務暫時無法使用，已自動跳過驗證。"
            }

        try:
            # 使用 Gemini LLM 分析照片
            prompt = """請分析這張照片，判斷是否符合以下條件：
1. 是否為人物照片
2. 是否為正面照或接近正面（臉部清晰可見）
3. 是否包含上半身（至少到肩膀以上）
4. 頭髮是否清晰可見
5. 照片品質是否足夠清晰

請以 JSON 格式回答，格式如下：
{
    "is_valid": true/false,
    "reason": "說明原因",
    "details": {
        "has_person": true/false,
        "is_frontal": true/false,
        "has_upper_body": true/false,
        "hair_visible": true/false,
        "good_quality": true/false
    }
}

請確保回答是純 JSON 格式，不要包含其他文字。"""

            # 調用 Gemini 分析
            response = self._gemini.analyze_with_llm(
                prompt=prompt,
                image_data_url=image_data_url
            )
            
            # 解析回應
            result = self._parse_validation_response(response)
            return result

        except Exception as exc:
            print(f"[PhotoValidator] 照片驗證過程發生錯誤: {exc}")
            # 發生錯誤時允許通過，避免阻擋用戶
            return {
                "is_valid": True,
                "message": "照片驗證遇到問題，已自動跳過。如果換髮型效果不佳，請嘗試使用正面半身照。"
            }

    def _parse_validation_response(self, response: str) -> Dict[str, any]:
        """解析 LLM 回應。"""
        try:
            # 嘗試提取 JSON
            response = response.strip()
            
            # 如果回應被包在 markdown 代碼塊中，提取出來
            if response.startswith("```"):
                lines = response.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```"):
                        in_json = not in_json
                        continue
                    if in_json:
                        json_lines.append(line)
                response = "\n".join(json_lines)
            
            data = json.loads(response)
            
            is_valid = data.get("is_valid", False)
            reason = data.get("reason", "")
            details = data.get("details", {})
            
            if is_valid:
                return {
                    "is_valid": True,
                    "message": "照片符合要求，可以進行試換髮型。"
                }
            else:
                # 生成具體的錯誤訊息
                issues = []
                if not details.get("has_person"):
                    issues.append("照片中未偵測到人物")
                if not details.get("is_frontal"):
                    issues.append("請使用正面照或接近正面的角度")
                if not details.get("has_upper_body"):
                    issues.append("請確保照片包含上半身（至少到肩膀）")
                if not details.get("hair_visible"):
                    issues.append("頭髮不夠清晰")
                if not details.get("good_quality"):
                    issues.append("照片品質不佳，請使用更清晰的照片")
                
                if issues:
                    message = "照片不符合要求：" + "、".join(issues) + "。"
                else:
                    message = reason or "照片不適合進行試換髮型。"
                
                return {
                    "is_valid": False,
                    "message": message,
                    "details": details
                }
                
        except json.JSONDecodeError:
            print(f"[PhotoValidator] 無法解析 JSON 回應: {response}")
            # 嘗試從文字中判斷
            response_lower = response.lower()
            if "true" in response_lower or "valid" in response_lower or "符合" in response_lower:
                return {
                    "is_valid": True,
                    "message": "照片符合要求。"
                }
            else:
                return {
                    "is_valid": False,
                    "message": "照片可能不符合要求。建議使用清晰的正面半身照，確保頭髮清晰可見。"
                }
        except Exception as exc:
            print(f"[PhotoValidator] 解析驗證結果時發生錯誤: {exc}")
            return {
                "is_valid": True,
                "message": "照片驗證過程發生錯誤，已自動跳過。"
            }

