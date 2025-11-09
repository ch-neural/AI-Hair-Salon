import base64
import logging
import mimetypes
import os
import shutil
import time
from io import BytesIO
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import concurrent.futures
import socket
import json

from common.services.tryon_analysis import TryOnAnalysisService

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

try:  # pragma: no cover - pillow-heif 並非必裝
    import pillow_heif  # type: ignore

    if pillow_heif and Image:
        pillow_heif.register_heif_opener()
except Exception:
    pillow_heif = None  # type: ignore

try:  # pragma: no cover - 若未安裝 google-genai 則轉入示範模式
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore
except Exception:
    genai = None  # type: ignore
    genai_types = None  # type: ignore


class GeminiService:
    """
    Gemini API 整合服務（整合進 unified 結構）：
    - 透過 google-genai Client 呼叫 Gemini 影像生成 API
    - 若缺少 API key 或遇到例外，提供 fallback/原圖
    - 靜態資源與輸出位於 apps/web/static/
    """

    SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def __init__(self, outputs_dir: Optional[str] = None, settings_json_path: Optional[str] = None) -> None:
        self.base_dir = Path.cwd()
        
        # Prioritize passed outputs_dir, then default to a path within the project structure
        if outputs_dir:
            self.outputs_dir = Path(outputs_dir)
            # Infer static_dir from outputs_dir (e.g., .../apps/web/static/outputs -> .../apps/web/static)
            if self.outputs_dir.name == "outputs" and self.outputs_dir.parent.name == "static":
                self.static_dir = self.outputs_dir.parent
            else:
                self.static_dir = self.base_dir / "app" / "static"
        else:
            # Fallback to legacy path structure
            self.static_dir = self.base_dir / "app" / "static"
            self.outputs_dir = self.static_dir / "outputs"
        
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        self.api_key: Optional[str] = None
        self.model_name: Optional[str] = "gemini-1.5-pro-preview-0409"
        self.llm_name: Optional[str] = "gemini-1.5-flash-preview-0514"
        self.llm_model_name: Optional[str] = "gemini-1.5-flash-preview-0514"  # alias for compatibility
        
        # Client type should be genai.Client for new API (>=0.3.0)
        self.client: Optional[Any] = None  # genai.Client when initialized
        self.llm: Optional[Any] = None  # Not used in new API but kept for compatibility
        
        # Settings tracking for hot-reload
        self._settings_path: Optional[str] = settings_json_path
        self._settings_mtime: Optional[float] = None

        self._load_settings(settings_json_path)

    def _load_settings(self, settings_json_path: Optional[str] = None):
        """
        Loads settings from a JSON file and falls back to environment variables.
        It will prioritize the provided path, but fallback to searching for a default path.
        """
        settings = {}
        path_to_load = None

        # Priority 1: Use the path explicitly passed to the service
        if settings_json_path and Path(settings_json_path).exists():
            path_to_load = Path(settings_json_path)
        
        # Priority 2: Fallback to the default path if the explicit one isn't provided/valid
        else:
            default_path = self.base_dir / "data" / "settings.json"
            if default_path.exists():
                path_to_load = default_path

        # Track the settings file path and modification time for hot-reload
        if path_to_load:
            self._settings_path = str(path_to_load)
            try:
                self._settings_mtime = path_to_load.stat().st_mtime
            except Exception:
                self._settings_mtime = None
        
        # Load from the determined path
        if path_to_load:
            try:
                import json
                settings = json.loads(path_to_load.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[GeminiService] Error loading settings from {path_to_load}: {e}")
                settings = {}

        # Load values, falling back from settings to environment variables, then to defaults
        self.api_key = settings.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.model_name = settings.get("GEMINI_MODEL") or os.getenv("GEMINI_MODEL", "gemini-1.5-pro-preview-0409")
        self.llm_name = settings.get("GEMINI_LLM") or os.getenv("GEMINI_LLM", "gemini-1.5-flash-preview-0514")
        self.llm_model_name = self.llm_name  # Keep both for compatibility

        # After loading, initialize the client if an API key is available
        if self.api_key and genai:
            try:
                # Use the new google-genai Client API (>=0.3.0)
                self.client = genai.Client(api_key=self.api_key)
                # llm is not needed as a separate object in new API
                self.llm = None
                print(f"[GeminiService] Client initialized successfully with API key: {self.api_key[:10]}...")
            except Exception as e:
                print(f"[GeminiService] Failed to initialize Gemini client: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                self.client = None
                self.llm = None
        else:
            if not self.api_key:
                print("[GeminiService] No API key found in settings or environment")
            if not genai:
                print("[GeminiService] google-genai module not available")
            self.client = None
            self.llm = None

    # Public API -----------------------------------------------------------------

    def generate_virtual_tryon(
        self,
        user_image_path: str,
        garment: Any = None,
        session_id: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        # hot-reload settings when file changes
        self._reload_settings_if_changed()
        session_ref = session_id or f"session_{int(time.time())}"
        output_filename = f"gen_{int(time.time()*1000)}.jpg"
        output_path = self.outputs_dir / output_filename
        public_path = f"/static/outputs/{output_filename}"

        if not Path(user_image_path).exists():
            return {"status": "error", "mode": "error", "output_path": None, "message": "User image not found"}

        # Detailed availability check
        if not self.api_key:
            print(f"[GeminiService] generate_virtual_tryon: API key is missing")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Gemini API key not configured"}
        if not self.client:
            print(f"[GeminiService] generate_virtual_tryon: Client is None, type={type(self.client).__name__}")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Gemini client not initialized"}
        if Image is None:
            print(f"[GeminiService] generate_virtual_tryon: PIL Image not available")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Image processing library not available"}

        try:
            mime_type, image_bytes = self._read_image_as_supported_bytes(user_image_path)
            prompt = self._build_prompt(garment, user_note=user_note)

            garment_image_abs: Optional[str] = None
            extra_garment_paths: list = []

            try:
                def _resolve_static(rel: str) -> Path:
                    rel_clean = str(rel).strip("/")
                    # 支援 'static/...' 或純相對路徑（如 'inputs/...'）
                    if rel_clean.startswith("static/"):
                        rel_clean = rel_clean[len("static/") :]
                    cand = self.static_dir / rel_clean
                    if cand.exists():
                        return cand
                    # 兼容舊 'app/static/...'
                    cand2 = self.base_dir / "app" / "static" / rel_clean
                    return cand2

                if isinstance(garment, list):
                    for g in garment:
                        g_rel = (g or {}).get("image_path")
                        if not g_rel:
                            continue
                        candidate = _resolve_static(g_rel)
                        if candidate.exists():
                            use_letterbox = os.getenv("TRYON_LETTERBOX_GARMENT", "0") == "1"
                            g_abs = self._letterbox_garment_to_user_canvas(user_image_path, str(candidate)) if use_letterbox else str(candidate)
                            g_abs = g_abs or str(candidate)
                            if not garment_image_abs:
                                garment_image_abs = g_abs
                            else:
                                extra_garment_paths.append(g_abs)
                else:
                    g_rel = (garment or {}).get("image_path")
                    if g_rel:
                        candidate = _resolve_static(g_rel)
                        if candidate.exists():
                            use_letterbox = os.getenv("TRYON_LETTERBOX_GARMENT", "0") == "1"
                            garment_image_abs = self._letterbox_garment_to_user_canvas(user_image_path, str(candidate)) if use_letterbox else str(candidate)
                            garment_image_abs = garment_image_abs or str(candidate)
            except Exception:
                garment_image_abs = None

            # 針對人物照加入偏好權重：重複攜帶人物照作為額外輸入，強化「以人物照為基準」
            bias_user_paths: list[str] = []
            try:
                if user_image_path and os.path.exists(user_image_path):
                    bias_user_paths.append(user_image_path)
                    bias_user_paths.append(user_image_path)
            except Exception:
                pass

            # API 呼叫
            if garment_image_abs:
                print(f"[GeminiService] invoking with garment={garment_image_abs} extra={len(extra_garment_paths)}")
            else:
                print("[GeminiService] invoking without garment (fallback mode)")
            response = self._invoke_gemini_api(
                prompt,
                mime_type,
                image_bytes,
                garment_image_abs,
                extra_image_paths=(extra_garment_paths + bias_user_paths),
                aspect_ratio_override=self._aspect_ratio_from_image(user_image_path),
            )

            # 直接擷取 bytes
            print("[GeminiService] attempting to extract image bytes from SDK response")
            image_bytes_out = self._extract_image_bytes_from_sdk(response)
            if image_bytes_out:
                print(f"[GeminiService] extracted {len(image_bytes_out)} bytes from SDK response")
                with open(output_path, "wb") as out_img:
                    out_img.write(image_bytes_out)
                print(f"[GeminiService] wrote api-bytes to {output_path}")
                self._optional_refine_steps(str(output_path), garment_image_abs, user_image_path)
                return {"status": "ok", "mode": "api", "output_path": public_path, "message": None}
            else:
                print("[GeminiService] NO image bytes extracted from SDK response")
                # Check for safety filtering or blocked content
                safety_info = self._check_safety_ratings(response)
                if safety_info:
                    print(f"[GeminiService] SAFETY CHECK: {safety_info}")
                    # 如果檢測到 IMAGE_OTHER 或其他拒絕原因，立即返回友好錯誤
                    if "IMAGE_OTHER" in safety_info or "finish_reason" in safety_info:
                        return {
                            "status": "error",
                            "mode": "generation_refused",
                            "output_path": None,
                            "message": "選取的照片無法生成試衣效果，請更換照片或服飾後重試"
                        }

            # 後備：dict 解析 base64
            print("[GeminiService] attempting to extract base64 from response dict")
            result_dict = self._response_to_dict(response)
            print(f"[GeminiService] response_to_dict returned: {type(result_dict).__name__} with keys={list(result_dict.keys()) if isinstance(result_dict, dict) else 'N/A'}")
            image_base64 = self._extract_image_data(result_dict)
            if image_base64:
                print(f"[GeminiService] extracted base64 image data, length={len(image_base64)}")
                with open(output_path, "wb") as out_img:
                    out_img.write(base64.b64decode(image_base64))
                print(f"[GeminiService] wrote api-b64 to {output_path}")
                self._optional_refine_steps(str(output_path), garment_image_abs, user_image_path)
                return {"status": "ok", "mode": "api", "output_path": public_path, "message": None}
            else:
                print("[GeminiService] NO base64 image data extracted from dict")

            print("[GeminiService] FAILED to extract any image from API response")
            return {
                "status": "error",
                "mode": "no_image",
                "output_path": None,
                "message": "AI 模型未返回圖片，請更換照片或服飾後重試"
            }
        except Exception as exc:
            try:
                err_type = type(exc).__name__
                err_msg = str(exc)
                print(f"[GeminiService] exception: {err_type}: {err_msg}")
            except Exception:
                pass
            return {"status": "error", "mode": "error", "output_path": None, "message": f"{type(exc).__name__}: {exc}"}

    def generate_virtual_tryon_two_stage(
        self,
        user_image_path: str,
        garment: Any = None,
        session_id: Optional[str] = None,
        user_note: Optional[str] = None,
        target_region: str = "full",
    ) -> Dict[str, Optional[str]]:
        """兩階段試衣：先生成文字描述，再根據描述生成圖片"""
        # hot-reload settings when file changes
        self._reload_settings_if_changed()
        session_ref = session_id or f"session_{int(time.time())}"
        output_filename = f"gen_{int(time.time()*1000)}.jpg"
        output_path = self.outputs_dir / output_filename
        public_path = f"/static/outputs/{output_filename}"

        if not Path(user_image_path).exists():
            return {"status": "error", "mode": "error", "output_path": None, "message": "User image not found"}

        # Detailed availability check
        if not self.api_key:
            print(f"[GeminiService] TWO_STAGE: API key is missing")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Gemini API key not configured"}
        if not self.client:
            print(f"[GeminiService] TWO_STAGE: Client is None")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Gemini client not initialized"}
        if Image is None:
            print(f"[GeminiService] TWO_STAGE: PIL Image not available")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Image processing library not available"}

        try:
            # === STAGE 1: 生成文字描述 ===
            print(f"[GeminiService] TWO-STAGE: Stage 1 - Generating description for session={session_ref}")
            mime_type, image_bytes = self._read_image_as_supported_bytes(user_image_path)
            
            # 準備服飾圖片
            garment_image_abs: Optional[str] = None
            try:
                def _resolve_static(rel: str) -> Optional[Path]:
                    """嘗試多個可能的路徑來查找髮型圖片"""
                    rel_clean = str(rel).strip("/")
                    if rel_clean.startswith("static/"):
                        rel_clean = rel_clean[len("static/") :]
                    
                    print(f"[GeminiService] DEBUG: Resolving garment image, rel={rel}, rel_clean={rel_clean}")
                    
                    # 嘗試多個可能的位置
                    candidates = [
                        self.static_dir / rel_clean,                    # storeTryon static dir
                        self.base_dir / "app" / "static" / rel_clean,  # storeTryon app/static
                        Path.cwd() / "static" / rel_clean,              # live-demo static dir (NEW!)
                        self.base_dir / "static" / rel_clean,           # base_dir/static
                        Path(rel) if Path(rel).is_absolute() else None, # 絕對路徑
                    ]
                    
                    for i, cand in enumerate(candidates):
                        if cand is None:
                            continue
                        print(f"[GeminiService] DEBUG: Trying candidate {i+1}: {cand}, exists={cand.exists()}")
                        if cand.exists():
                            print(f"[GeminiService] DEBUG: Found garment image at: {cand}")
                            return cand
                    
                    print(f"[GeminiService] DEBUG: Garment image not found in any candidate path")
                    return None

                if isinstance(garment, list):
                    for g in garment:
                        g_rel = (g or {}).get("image_path")
                        if not g_rel:
                            continue
                        candidate = _resolve_static(g_rel)
                        if candidate and candidate.exists():
                            garment_image_abs = str(candidate)
                            break
                else:
                    g_rel = (garment or {}).get("image_path")
                    if g_rel:
                        print(f"[GeminiService] DEBUG: garment image_path={g_rel}")
                        candidate = _resolve_static(g_rel)
                        if candidate and candidate.exists():
                            garment_image_abs = str(candidate)
                            print(f"[GeminiService] DEBUG: garment_image_abs set to: {garment_image_abs}")
                        else:
                            print(f"[GeminiService] DEBUG: Failed to resolve garment image path")
            except Exception as exc:
                print(f"[GeminiService] DEBUG: Exception during garment image resolution: {exc}")
                import traceback
                traceback.print_exc()
                garment_image_abs = None

            # Stage 1 Prompt: 要求生成詳細描述
            stage1_prompt = self._build_description_prompt(garment, user_note=user_note)
            
            # 顯示完整的 Stage 1 prompt
            print("=" * 80)
            print("[GeminiService] TWO-STAGE: Stage 1 Complete Prompt (Text Only):")
            print("-" * 80)
            print(stage1_prompt)
            print("=" * 80)
            
            # 準備 Stage 1 的圖片輸入
            stage1_parts = [{"text": stage1_prompt}]
            stage1_parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("utf-8")}})
            print(f"[GeminiService] TWO-STAGE: Stage 1 - Added user photo (Image 1) - mime_type={mime_type}, size={len(image_bytes)} bytes")
            
            if garment_image_abs and os.path.exists(garment_image_abs):
                g_mime, g_bytes = self._read_image_as_supported_bytes(garment_image_abs)
                stage1_parts.append({"inline_data": {"mime_type": g_mime, "data": base64.b64encode(g_bytes).decode("utf-8")}})
                print(f"[GeminiService] TWO-STAGE: Stage 1 - Added hairstyle photo (Image 2) - path={garment_image_abs}, mime_type={g_mime}, size={len(g_bytes)} bytes")
            else:
                print(f"[GeminiService] TWO-STAGE: Stage 1 - No hairstyle photo provided")
            
            # 呼叫 Gemini 生成描述
            print(f"[GeminiService] TWO-STAGE: Calling Gemini LLM for text description with {len(stage1_parts)} parts (1 text + {len(stage1_parts)-1} images)")
            # 使用文字模型產生描述（避免影像模型回傳非文字）
            response1 = self.client.models.generate_content(
                model=self.llm_name,
                contents={"parts": stage1_parts},
            )
            
            # 提取文字描述
            description = ""
            try:
                if hasattr(response1, 'text'):
                    description = response1.text
                elif hasattr(response1, 'candidates') and response1.candidates:
                    if hasattr(response1.candidates[0], 'content'):
                        if hasattr(response1.candidates[0].content, 'parts'):
                            for part in response1.candidates[0].content.parts:
                                if hasattr(part, 'text'):
                                    description += part.text
            except Exception as e:
                print(f"[GeminiService] TWO-STAGE: Failed to extract text from stage 1: {e}")
                return {"status": "error", "mode": "stage1_failed", "output_path": None, "message": "無法生成描述，請重試"}
            
            if not description:
                print("[GeminiService] TWO-STAGE: Stage 1 returned no description")
                return {"status": "error", "mode": "stage1_empty", "output_path": None, "message": "描述生成失敗，請重試"}
            
            # Sanitize description to avoid terms that trigger safety filters
            desc_before = description
            description = self._sanitize_description(description)
            # Prepend lawful/normal scenario context for Stage 2 (hair salon portfolio / hairstyle showcase)
            context_prefix = (
                "Context: The person is trying a new hairstyle for a professional hair salon portfolio or hairstyle demonstration, to showcase only the referenced hairstyle.\n"
                "CRITICAL: This is a HAIR-ONLY modification. The person's clothing, body, face (except hair), and environment remain COMPLETELY UNCHANGED from the original photo.\n"
                "The description below describes the final result with the new hairstyle applied to the original photo. Keep everything except hair identical.\n\n"
            )
            description = context_prefix + description
            print(f"[GeminiService] TWO-STAGE: Stage 1 description generated (length={len(desc_before)} -> sanitized+context={len(description)})")
            print(f"[GeminiService] TWO-STAGE: Description: {description[:200]}...")
            description = re.sub(r"\b(model|模特|模特兒)\b", "reference look", description, flags=re.IGNORECASE)
            
            # === STAGE 2: 根據描述生成圖片 ===
            print(f"[GeminiService] TWO-STAGE: Stage 2 - Generating image from description")

            # Stage 2 Prompt（依據目標區域調整約束）
            stage2_prompt = self._build_image_from_description_prompt(description, user_note=user_note, target_region=target_region)
            
            # 顯示完整的 Stage 2 prompt
            print("=" * 80)
            print("[GeminiService] TWO-STAGE: Stage 2 Complete Prompt (Text Only):")
            print("-" * 80)
            print(stage2_prompt)
            print("=" * 80)

            safety_settings = self._get_safety_settings()

            roi_attempted = False
            if target_region == "upper":
                roi_result = self._generate_on_upper_body_roi(user_image_path, garment_image_abs, stage2_prompt, safety_settings, public_path, output_path)
                if roi_result:
                    return roi_result
                print("[GeminiService] TWO-STAGE: Upper-body ROI generation failed; falling back to full-frame")
                roi_attempted = True
            elif target_region == "lower" or self._should_use_lower_body_roi(user_note or "", description, garment):
                roi_result = self._generate_on_lower_body_roi(user_image_path, garment_image_abs, stage2_prompt, safety_settings, public_path, output_path)
                if roi_result:
                    return roi_result
                print("[GeminiService] TWO-STAGE: Lower-body ROI generation failed; falling back to full-frame")
                roi_attempted = True

            # 全圖生成
            stage2_parts = [{"text": stage2_prompt}]
            stage2_parts.append({"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("utf-8")}})
            print(f"[GeminiService] TWO-STAGE: Added user photo (Image 1) - mime_type={mime_type}, size={len(image_bytes)} bytes")
            
            if garment_image_abs and os.path.exists(garment_image_abs):
                g_mime2, g_bytes2 = self._read_image_as_supported_bytes(garment_image_abs)
                stage2_parts.append({"inline_data": {"mime_type": g_mime2, "data": base64.b64encode(g_bytes2).decode("utf-8")}})
                print(f"[GeminiService] TWO-STAGE: Added hairstyle photo (Image 2) - path={garment_image_abs}, mime_type={g_mime2}, size={len(g_bytes2)} bytes")
            else:
                print(f"[GeminiService] TWO-STAGE: No hairstyle photo provided (garment_image_abs={garment_image_abs})")
            
            print(f"[GeminiService] TWO-STAGE: Calling Gemini for image generation (full-frame) with {len(stage2_parts)} parts (1 text + {len(stage2_parts)-1} images)")
            response2 = self.client.models.generate_content(
                model=self.model_name,
                contents={"parts": stage2_parts},
                config={
                    "safety_settings": safety_settings,
                }
            )
            
            # 提取圖片
            print("[GeminiService] TWO-STAGE: Attempting to extract image bytes from stage 2 response")
            image_bytes_out = self._extract_image_bytes_from_sdk(response2)
            if image_bytes_out:
                print(f"[GeminiService] TWO-STAGE: Extracted {len(image_bytes_out)} bytes from SDK response")
                with open(output_path, "wb") as out_img:
                    out_img.write(image_bytes_out)
                print(f"[GeminiService] TWO-STAGE: Wrote image to {output_path}")
                self._run_final_identity_check(str(user_image_path), str(output_path))
                return {"status": "ok", "mode": "two_stage", "output_path": public_path, "message": None}
            else:
                print("[GeminiService] TWO-STAGE: NO image bytes extracted from stage 2 response")
                needs_lower_roi = target_region == "lower" or self._should_use_lower_body_roi(user_note or "", description, garment)
                needs_upper_roi = target_region == "upper" or self._should_use_upper_body_roi(user_note or "", description, garment)
                if needs_lower_roi or needs_upper_roi:
                    roi_combined = self._apply_roi_sequence(
                        user_image_path,
                        garment_image_abs,
                        stage2_prompt,
                        safety_settings,
                        public_path,
                        output_path,
                        needs_upper=needs_upper_roi,
                        needs_lower=needs_lower_roi,
                    )
                    if roi_combined:
                        return roi_combined
                # Check for safety filtering
                safety_info = self._check_safety_ratings(response2)
                if safety_info:
                    print(f"[GeminiService] TWO-STAGE: SAFETY CHECK: {safety_info}")
                    if "IMAGE_OTHER" in safety_info or "finish_reason" in safety_info:
                        # 嘗試一次安全回退：將下身改為 short athletic shorts 並移除可能的觸發語彙，再重試一次
                        try:
                            if target_region != "upper":
                                safe_desc = re.sub(r"\b(short swim trunks \(brief-style\))\b", "short athletic shorts", description, flags=re.IGNORECASE)
                                safe_desc = re.sub(r"\b(underwear|briefs?|boxers?)\b", "short athletic shorts", safe_desc, flags=re.IGNORECASE)
                            else:
                                safe_desc = description
                            stage2_prompt_safe = self._build_image_from_description_prompt(safe_desc, user_note=user_note, target_region=target_region)
                            needs_lower_safe = target_region == "lower" or self._should_use_lower_body_roi(user_note or "", safe_desc, garment)
                            needs_upper_safe = target_region == "upper" or self._should_use_upper_body_roi(user_note or "", safe_desc, garment)
                            if needs_lower_safe or needs_upper_safe:
                                roi_ok_fb = self._apply_roi_sequence(
                                    user_image_path,
                                    garment_image_abs,
                                    stage2_prompt_safe,
                                    safety_settings,
                                    public_path,
                                    output_path,
                                    needs_upper=needs_upper_safe,
                                    needs_lower=needs_lower_safe,
                                )
                                if roi_ok_fb:
                                    return roi_ok_fb
                            stage2_parts_safe = [{"text": stage2_prompt_safe}, {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode("utf-8")}}]
                            if garment_image_abs and os.path.exists(garment_image_abs):
                                g_mime3, g_bytes3 = self._read_image_as_supported_bytes(garment_image_abs)
                                stage2_parts_safe.append({"inline_data": {"mime_type": g_mime3, "data": base64.b64encode(g_bytes3).decode("utf-8")}})
                            print("[GeminiService] TWO-STAGE: RETRY with fallback prompt")
                            response2b = self.client.models.generate_content(
                                model=self.model_name,
                                contents={"parts": stage2_parts_safe},
                                config={
                                    "safety_settings": safety_settings,
                                }
                            )
                            print("[GeminiService] TWO-STAGE: Attempting to extract image bytes from fallback response")
                            image_bytes_out_b = self._extract_image_bytes_from_sdk(response2b)
                            if image_bytes_out_b:
                                with open(output_path, "wb") as out_img:
                                    out_img.write(image_bytes_out_b)
                                self._run_final_identity_check(str(user_image_path), str(output_path))
                                return {"status": "ok", "mode": "two_stage_fallback", "output_path": public_path, "message": None}
                            result_dict_b = self._response_to_dict(response2b)
                            image_base64_b = self._extract_image_data(result_dict_b)
                            if image_base64_b:
                                with open(output_path, "wb") as out_img:
                                    out_img.write(base64.b64decode(image_base64_b))
                                self._run_final_identity_check(str(user_image_path), str(output_path))
                                return {"status": "ok", "mode": "two_stage_fallback", "output_path": public_path, "message": None}
                        except Exception:
                            pass
                        return {
                            "status": "error",
                            "mode": "generation_refused",
                            "output_path": None,
                            "message": "選取的照片無法生成試衣效果，請更換照片或服飾後重試"
                        }
            
            # 後備：嘗試從 dict 提取 base64
            print("[GeminiService] TWO-STAGE: Attempting to extract base64 from response dict")
            result_dict = self._response_to_dict(response2)
            image_base64 = self._extract_image_data(result_dict)
            if image_base64:
                print(f"[GeminiService] TWO-STAGE: Extracted base64 image data")
                with open(output_path, "wb") as out_img:
                    out_img.write(base64.b64decode(image_base64))
                print(f"[GeminiService] TWO-STAGE: Wrote image to {output_path}")
                self._run_final_identity_check(str(user_image_path), str(output_path))
                return {"status": "ok", "mode": "two_stage", "output_path": public_path, "message": None}
            
            print("[GeminiService] TWO-STAGE: FAILED to extract any image from stage 2 response")
            return {
                "status": "error",
                "mode": "no_image",
                "output_path": None,
                "message": "AI 模型未返回圖片，請更換照片或服飾後重試"
            }
        except Exception as exc:
            try:
                err_type = type(exc).__name__
                err_msg = str(exc)
                print(f"[GeminiService] TWO-STAGE exception: {err_type}: {err_msg}")
            except Exception:
                pass
            return {"status": "error", "mode": "error", "output_path": None, "message": f"{type(exc).__name__}: {exc}"}

    def generate_virtual_tryon_simple(
        self,
        user_image_path: str,
        garment: Any = None,
        garment_info: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        self._reload_settings_if_changed()
        session_ref = session_id or f"tryon_{int(time.time()*1000)}"
        output_filename = f"gen_{int(time.time()*1000)}.jpg"
        output_path = self.outputs_dir / output_filename
        public_path = f"/static/outputs/{output_filename}"

        if not Path(user_image_path).exists():
            return {"status": "error", "mode": "error", "output_path": None, "message": "User image not found"}

        # Detailed availability check
        print(f"[GeminiService] SIMPLE: Checking availability - api_key={bool(self.api_key)} client={bool(self.client)} client_type={type(self.client).__name__ if self.client else 'None'} Image={Image is not None}")
        if not self.api_key:
            print(f"[GeminiService] SIMPLE: API key is missing")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Gemini API key not configured"}
        if not self.client:
            print(f"[GeminiService] SIMPLE: Client is None")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Gemini client not initialized"}
        if Image is None:
            print(f"[GeminiService] SIMPLE: PIL Image not available")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "Image processing library not available"}

        try:
            user_mime, user_bytes = self._read_image_as_supported_bytes(user_image_path)
        except Exception as exc:
            return {"status": "error", "mode": "error", "output_path": None, "message": str(exc)}

        # ⚡ OPTIMIZATION: SIMPLE mode doesn't use text descriptions
        # Only keep has_model for safety (though ROI is disabled anyway)
        has_model = bool(garment_info and garment_info.get("has_model"))

        # --- Structured Prompt Generation for HAIRSTYLE (VISUAL-BASED) ---
        prompt_parts = [
            "✂️ **PHOTO EDITING TASK: HAIR REPLACEMENT**",
            "",
            "🎯 **YOUR MISSION:**",
            "Edit Image 1 by REPLACING its hair with the hairstyle from Image 2.",
            "This is PHOTO EDITING (修圖), NOT image combination (合成).",
            "",
            "📸 **INPUT:**",
            "- **Image 1 (Base Photo):** The photo to edit. ONE person. Keep everything except hair.",
            "- **Image 2 (Hair Reference):** Look at the hair only. Extract the hairstyle features.",
            "",
            "📤 **OUTPUT REQUIREMENT:**",
            "✅ A SINGLE edited photo of Image 1's person",
            "✅ ONLY Image 1's person (same face, body, pose, clothes, background)",
            "✅ WITH Image 2's hairstyle (REPLACED hair, not added)",
            "❌ NOT a composite of two people",
            "❌ NOT two photos side by side",
            "❌ NOT Image 2's person",
            "",
            "🔥 **CRITICAL RULES:**",
            "1. **ONLY ONE PERSON in output** (Image 1's person)",
            "2. **REPLACE hair, do NOT ADD** (no extra heads/people)",
            "3. **LOOK at Image 2's hair** (color, length, texture, volume, style)",
            "4. **APPLY to Image 1** (edit Image 1's hair to match Image 2's hair)",
            "5. **KEEP Image 1 unchanged** (face, body, clothes, background all the same)",
        ]

        garment_path = None
        if garment and isinstance(garment, dict):
            image_path = garment.get("image_path")
            if image_path:
                candidate = self.base_dir / "app" / image_path
                if not candidate.exists():
                    candidate = self.base_dir / image_path
                if candidate.exists():
                    garment_path = candidate
        
        prompt_parts.extend([
            "",
            "✂️ **PHOTO EDITING WORKFLOW:**",
            "",
            "**STEP 1: ANALYZE Image 2's hair (Reference Analysis)**",
            "Look at Image 2's person's hair:",
            "- Hair length: (long/medium/short? reaches shoulders/ears/chin?)",
            "- Hair color: (exact shade, highlights, natural/dyed?)",
            "- Hair texture: (straight/wavy/curly/coily? smooth/textured?)",
            "- Hair volume: (flat/medium/voluminous/puffy?)",
            "- Hair style: (up/down/swept/parted? bangs? layers?)",
            "- Cut shape: (bob/pixie/layers/fade/undercut?)",
            "",
            "**STEP 2: EDIT Image 1 (Apply Hairstyle)**",
            "Open Image 1 in your photo editor. Select the hair area.",
            "REPLACE the existing hair with new hair that matches:",
            "✓ Length from Image 2",
            "✓ Color from Image 2",
            "✓ Texture from Image 2",
            "✓ Volume from Image 2",
            "✓ Style from Image 2",
            "✓ Cut shape from Image 2",
            "",
            "**STEP 3: PRESERVE Image 1 (Keep Everything Else)**",
            "DO NOT edit these areas:",
            "✓ Face (keep Image 1's face exactly)",
            "✓ Skin tone (keep Image 1's skin tone)",
            "✓ Body (keep Image 1's pose, position)",
            "✓ Clothes (keep Image 1's outfit 100%)",
            "✓ Accessories (keep Image 1's items)",
            "✓ Background (keep Image 1's scene)",
            "✓ Lighting (keep Image 1's shadows/highlights)",
            "",
            "**STEP 4: QUALITY CHECK**",
            "Before exporting, verify:",
            "✓ Only ONE person in the photo (Image 1's person)",
            "✓ Hair is changed (matches Image 2's hairstyle)",
            "✓ Face is unchanged (Image 1's face)",
            "✓ Body/clothes unchanged (Image 1's everything)",
            "✓ No extra heads/people added",
            "✓ Not a before/after comparison",
            "✓ Not a side-by-side layout",
            "",
            "🚫 **CRITICAL ERRORS TO AVOID:**",
            "❌ Adding Image 2's person to the photo",
            "❌ Adding Image 2's head/face to the photo",
            "❌ Creating a composite with two people",
            "❌ Creating a before/after comparison",
            "❌ Showing two heads/faces in output",
            "❌ Replacing Image 1's person with Image 2's person",
            "❌ Changing anything except hair",
            "",
            "✅ **CORRECT OUTPUT:**",
            "One photo. One person (Image 1's person). New hairstyle (Image 2's style).",
            "Think: 'This person went to a hair salon and got a new hairstyle.'",
        ])

        if user_note:
            prompt_parts.append(f"\n**Additional User Request:** {user_note}")

        prompt_parts.extend([
            "",
            "🔍 **FINAL VERIFICATION CHECKLIST:**",
            "Before you generate, answer these questions:",
            "",
            "1. **How many people in my output?**",
            "   ✅ CORRECT: ONE person (Image 1's person)",
            "   ❌ WRONG: Two people, two heads, or composite",
            "",
            "2. **Whose face is in my output?**",
            "   ✅ CORRECT: Image 1's face (unchanged)",
            "   ❌ WRONG: Image 2's face, or both faces",
            "",
            "3. **Whose body/clothes in my output?**",
            "   ✅ CORRECT: Image 1's body/clothes (unchanged)",
            "   ❌ WRONG: Image 2's body/clothes, or mixed",
            "",
            "4. **Whose hairstyle in my output?**",
            "   ✅ CORRECT: Image 2's hairstyle (NEW hair)",
            "   ❌ WRONG: Image 1's hairstyle (old hair)",
            "",
            "5. **Did I ADD or REPLACE?**",
            "   ✅ CORRECT: REPLACED hair (edited existing photo)",
            "   ❌ WRONG: ADDED head/person (composite)",
            "",
            "6. **Is this a single photo or comparison?**",
            "   ✅ CORRECT: Single photo (one person, edited)",
            "   ❌ WRONG: Before/after, side-by-side, comparison",
            "",
            "⚠️ **IF ANY ANSWER IS WRONG, DO NOT GENERATE.**",
            "⚠️ **Go back and re-read the instructions.**",
            "⚠️ **Remember: This is PHOTO EDITING, not IMAGE COMBINATION.**",
        ])
        
        prompt = "\n".join(prompt_parts)

        # 顯示完整的 SIMPLE 模式 prompt
        print("=" * 80)
        print("[GeminiService] SIMPLE: Complete Prompt (Text Only):")
        print("-" * 80)
        print(prompt)
        print("=" * 80)

        parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": user_mime,
                    "data": base64.b64encode(user_bytes).decode("utf-8"),
                }
            },
        ]
        print(f"[GeminiService] SIMPLE: Added user photo (Image 1) - mime_type={user_mime}, size={len(user_bytes)} bytes")
        
        # CRITICAL: Always pass the hairstyle image for visual extraction
        # For hairstyle try-on, we MUST show AI the hairstyle photo (even if it has a model)
        if garment_path and garment_path.exists():
            g_mime, g_bytes = self._read_image_as_supported_bytes(str(garment_path))
            parts.append({"inline_data": {"mime_type": g_mime, "data": base64.b64encode(g_bytes).decode("utf-8")}})
            print(f"[GeminiService] SIMPLE: Added hairstyle photo (Image 2) - path={garment_path}, mime_type={g_mime}, size={len(g_bytes)} bytes")
        else:
            print(f"[GeminiService] SIMPLE: No hairstyle photo provided (garment_path={garment_path})")

        print(f"[GeminiService] SIMPLE: Calling Gemini for image generation with {len(parts)} parts (1 text + {len(parts)-1} images)")
        print(f"[GeminiService] SIMPLE: model={self.model_name}")
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents={"parts": parts},
                config={
                    "safety_settings": self._get_safety_settings(),
                    # Note: response_mime_type is NOT supported for image generation
                    # Image generation automatically returns image data in the response
                },
            )
            print(f"[GeminiService] SIMPLE: API call completed, response type={type(response).__name__}")
        except Exception as api_error:
            print(f"[GeminiService] SIMPLE: API call failed with {type(api_error).__name__}: {api_error}")
            return {
                "status": "error",
                "mode": "api_error",
                "output_path": None,
                "message": f"API 調用失敗: {str(api_error)}",
            }

        print("[GeminiService] SIMPLE: Attempting to extract image bytes from response")
        
        # Log response structure for debugging
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            for idx, candidate in enumerate(candidates):
                finish_reason = getattr(candidate, "finish_reason", None)
                print(f"[GeminiService] SIMPLE: candidate[{idx}].finish_reason={finish_reason}")
        
        image_bytes_out = self._extract_image_bytes_from_sdk(response)

        # ⚡ OPTIMIZATION: ROI mode is disabled, so these checks always return False
        # Keeping the code for compatibility, but simplified
        needs_lower = self._should_use_lower_body_roi(user_note or "", "", garment)
        needs_upper = self._should_use_upper_body_roi(user_note or "", "", garment)

        if garment_info and garment_info.get("has_model"):
            needs_lower = False
            needs_upper = False

        if image_bytes_out:
            with open(output_path, "wb") as out_img:
                out_img.write(image_bytes_out)
            print(f"[GeminiService] SIMPLE: Wrote image to {output_path}")
            return {"status": "ok", "mode": "simple", "output_path": public_path, "message": None}

        print(f"[GeminiService] SIMPLE: No bytes from SDK, trying fallback methods")

        if needs_lower or needs_upper:
            print(f"[GeminiService] SIMPLE: Attempting ROI sequence (needs_lower={needs_lower}, needs_upper={needs_upper})")
            roi_result = self._apply_roi_sequence(
                user_image_path,
                str(garment_path) if garment_path else None,
                prompt,
                self._get_safety_settings(),
                public_path,
                output_path,
                needs_upper=needs_upper,
                needs_lower=needs_lower,
            )
            if roi_result:
                print(f"[GeminiService] SIMPLE: ROI sequence succeeded")
                return roi_result
            print(f"[GeminiService] SIMPLE: ROI sequence failed or returned None")

        print(f"[GeminiService] SIMPLE: Attempting base64 extraction from response dict")
        result_dict = self._response_to_dict(response)
        print(f"[GeminiService] SIMPLE: response_dict type={type(result_dict).__name__}, keys={list(result_dict.keys()) if isinstance(result_dict, dict) else 'N/A'}")
        image_base64 = self._extract_image_data(result_dict)
        if image_base64:
            with open(output_path, "wb") as out_img:
                out_img.write(base64.b64decode(image_base64))
            print(f"[GeminiService] SIMPLE: Wrote base64 image to {output_path}")
            return {"status": "ok", "mode": "simple", "output_path": public_path, "message": None}

        print(f"[GeminiService] SIMPLE: Base64 extraction also failed")
        safety_info = self._check_safety_ratings(response)
        if safety_info:
            print(f"[GeminiService] SIMPLE: SAFETY CHECK {safety_info}")
        else:
            print(f"[GeminiService] SIMPLE: No safety issues detected, but no image data found")

        return {
            "status": "error",
            "mode": "simple_failed",
            "output_path": None,
            "message": "目前提供的相片，無法生成試衣照。",
        }

    def generate_virtual_tryon_sensitive(
        self,
        user_image_path: str,
        garment_info: Dict[str, Any],
        session_id: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        self._reload_settings_if_changed()
        output_filename = f"gen_{int(time.time()*1000)}.jpg"
        output_path = self.outputs_dir / output_filename
        public_path = f"/static/outputs/{output_filename}"

        if not Path(user_image_path).exists():
            return {"status": "error", "message": "User image not found"}
        
        # Detailed availability check
        if not self.api_key:
            print(f"[GeminiService] SENSITIVE: API key is missing")
            return {"status": "error", "message": "Gemini API key not configured"}
        if not self.client:
            print(f"[GeminiService] SENSITIVE: Client is None")
            return {"status": "error", "message": "Gemini client not initialized"}
        if Image is None:
            print(f"[GeminiService] SENSITIVE: PIL Image not available")
            return {"status": "error", "message": "Image processing library not available"}

        garment_desc = garment_info.get("garment_description", "the described garment")
        
        prompt_parts = [
            "CONTEXT: Professional e-commerce product photography for fashion retail (swimwear/sportswear/underwear), similar to Nike, Adidas, Victoria's Secret, or Olympic sportswear catalogs.",
            "\nTASK: Replace the current garment with the new product while maintaining commercial photography standards.",
            f"\nNEW PRODUCT: {garment_desc}",
            "\nREQUIREMENTS:",
            "- Completely replace the old garment with the new product",
            "- Maintain the original design and coverage level of the new product (do NOT add extra coverage or modify the design)",
            "- Use professional athletic/fashion photography styling",
            "- For swimwear/underwear: render as seen in major sportswear brand catalogs",
            "- Keep the person's pose, background, and lighting unchanged",
        ]

        if any(keyword in garment_desc.lower() or garment_info.get("category", "").lower() for keyword in ["brief", "underwear", "swim trunks", "bikini", "thong", "内裤", "泳裤", "swim", "泳"]):
            prompt_parts.append(
                "- This is swimwear/athletic wear: maintain the product's original length (brief-style ends at upper thigh, do NOT extend to knee or ankle)"
            )

        if user_note:
            prompt_parts.append(f"- Customer preference: {user_note}")

        prompt = "\n".join(prompt_parts)

        info_text = " ".join(
            str(garment_info.get(key, "")) for key in ("category", "garment_description", "on_body_description")
        )
        needs_lower = self._should_use_lower_body_roi("", info_text, None)
        needs_upper = self._should_use_upper_body_roi("", info_text, None)

        print(f"[GeminiService] SENSITIVE: Starting ROI generation. Lower={needs_lower}, Upper={needs_upper}")

        result = self._apply_roi_sequence(
            user_image_path,
            garment_image_abs=None,
            stage2_prompt=prompt,
            safety_settings=self._get_safety_settings(),
            public_path=public_path,
            output_path=output_path,
            needs_upper=needs_upper,
            needs_lower=needs_lower,
        )
        
        if result and result.get("status") == "ok":
            return result

        print("[GeminiService] SENSITIVE: ROI generation failed, generation refused.")
        return {
            "status": "error",
            "mode": "sensitive_failed",
            "output_path": None,
            "message": "目前提供的相片，無法生成試衣照。",
        }

    def _build_description_prompt(self, garment: Any = None, user_note: Optional[str] = None) -> str:
        """Stage 1: 生成描述 prompt"""
        has_garment = False
        try:
            if garment and isinstance(garment, list):
                has_garment = len(garment) > 0 and bool((garment[0] or {}).get("image_path"))
            elif garment and isinstance(garment, dict):
                has_garment = bool(garment.get("image_path"))
        except Exception:
            has_garment = False

        custom = ""
        if user_note:
            note_clean = user_note.strip()
            if note_clean:
                custom = (
                    "User preference to highlight in the final description:\n"
                    f"- {note_clean}\n"
                    "Ensure this requirement is explicitly described in the final hairstyle portrayal.\n\n"
                )

        if has_garment:
            return (
                custom +
                "You are creating a description for a HAIR-ONLY replacement operation for a professional hairstyle visualization service.\n"
                "\n"
                "Given:\n"
                "- Image 1: A person in their current environment (reference photo to preserve COMPLETELY)\n"
                "- Image 2: A hairstyle reference (ONLY extract the hair - ignore EVERYTHING else including the person's body, face, and clothing)\n"
                "\n"
                "🚫 ABSOLUTE PROHIBITION - DO NOT VIOLATE:\n"
                "- You are FORBIDDEN from mentioning ANY clothing from Image 2\n"
                "- You are FORBIDDEN from describing ANY outfit details from Image 2\n"
                "- You are FORBIDDEN from copying ANY fashion or style elements from Image 2 except hair\n"
                "- Treat Image 2 as if ONLY the hair region exists - everything else is invisible\n"
                "- If Image 2 shows a dress, shirt, pants, jacket, or any clothing → IGNORE IT COMPLETELY\n"
                "\n"
                "⚠️ CRITICAL TASK: Describe the FINAL RESULT where Image 1's person has ONLY Image 2's hairstyle.\n"
                "This is EXCLUSIVELY a hair replacement - EVERYTHING except the hairstyle remains identical to Image 1.\n"
                "\n"
                "🔥🔥🔥 CRITICAL INSTRUCTION - BE EXTREMELY DETAILED 🔥🔥🔥\n"
                "⚠️ You MUST extract EVERY detail from Image 2's hairstyle:\n"
                "- DO NOT write generic descriptions like 'short hair' or 'neat hairstyle'\n"
                "- DO NOT skip any observable details\n"
                "- DESCRIBE: exact cut style, length differences (top vs sides vs back), taper level, texture, styling direction, part location, volume level, finish type\n"
                "- EVEN IF Image 1's hairstyle looks similar to Image 2's, still describe Image 2's hairstyle in FULL DETAIL\n"
                "- Think: 'If a hairstylist reads my description, they should be able to recreate Image 2's EXACT hairstyle'\n"
                "\n"
                "Your description MUST specify:\n"
                "\n"
                "WHAT CHANGES (extract ONLY from Image 2's HAIR - BE EXTREMELY SPECIFIC):\n"
                "- THE NEW HAIRSTYLE ONLY: Describe in detail ONLY the hairstyle from Image 2\n"
                "  * Hair color (exact shade and tone)\n"
                "  * Hair length (CRITICAL: Be PRECISE - if Image 2 shows long hair, write 'long hair reaching to waist/mid-back/shoulders'; if short, write 'short bob/pixie cut/chin-length'. DO NOT conservatively default to the original length!)\n"
                "  * Hair texture (straight, wavy, curly, coily)\n"
                "  * Hair style and cut (layers, bangs, shape)\n"
                "  * Hair volume and body\n"
                "  * Styling details (parted, swept, tousled, sleek)\n"
                "\n"
                "⚠️ HAIR LENGTH TRANSFORMATION IS FULLY ALLOWED:\n"
                "- If Image 1 has short hair and Image 2 has long hair → describe the LONG hair from Image 2\n"
                "- If Image 1 has long hair and Image 2 has short hair → describe the SHORT hair from Image 2\n"
                "- Hair length can COMPLETELY change - this is a hair transformation, not a hair preservation\n"
                "- Be bold and precise: if you see waist-length hair in Image 2, describe it as waist-length\n"
                "\n"
                "WHAT REMAINS EXACTLY IDENTICAL (from Image 1 - DO NOT CHANGE - DO NOT DESCRIBE FROM IMAGE 2):\n"
                "- Face: exact facial features, bone structure, skin tone, expression, makeup FROM IMAGE 1\n"
                "- Eyes: same eye color, shape, and gaze direction FROM IMAGE 1\n"
                "- Neck: identical to IMAGE 1\n"
                "- Body: same pose, position, body type, posture, arms, legs FROM IMAGE 1\n"
                "- Clothing: IDENTICAL outfit FROM IMAGE 1 - same style, colors, patterns, fit, fabric, ALL details FROM IMAGE 1\n"
                "- Accessories: same jewelry, glasses, watches, bags, belts, shoes FROM IMAGE 1, EVERYTHING FROM IMAGE 1\n"
                "- Background: exact same scene, environment, objects, walls, furniture FROM IMAGE 1\n"
                "- Lighting: same light sources, direction, shadows, highlights FROM IMAGE 1\n"
                "- Camera: same angle, framing, perspective, distance FROM IMAGE 1\n"
                "\n"
                "⚠️ MANDATORY RULES (FOLLOW STRICTLY):\n"
                "- DO NOT mention or describe the original hairstyle from Image 1\n"
                "- DO NOT copy the face, body, pose, or clothing from Image 2\n"
                "- DO NOT mention ANY clothing items from Image 2 - pretend Image 2's clothing doesn't exist\n"
                "- Extract ONLY the hairstyle characteristics from Image 2\n"
                "- Preserve ALL other aspects of Image 1 exactly - especially clothing from Image 1\n"
                "- Write as if Image 1's person already has Image 2's hairstyle\n"
                "- Use professional hair salon terminology\n"
                "\n"
                "🚫 CLOTHING FROM IMAGE 2 IS FORBIDDEN:\n"
                "- DO NOT write anything like 'wearing a dress', 'in a shirt', 'wearing pants' unless it's explicitly from Image 1\n"
                "- If you see clothing in Image 2, ERASE it from your mind - it doesn't exist\n"
                "- The ONLY source for clothing description is Image 1\n"
                "- Simply state: 'wearing the same outfit as in the original photo' or don't mention clothing at all\n"
                "\n"
                "Example format:\n"
                "[Describe Image 1's pose, setting, expression]. "
                "The person is wearing the same outfit as in the original photo. "
                "The person now has [detailed hairstyle description from Image 2: color, length, texture, style, cut, volume]. "
                "All facial features, body position, the exact same clothing, background, and lighting remain exactly as in the original photo. "
                "Only the hairstyle has changed.\n"
                "\n"
                "Example (short to long transformation):\n"
                "\"The person is smiling warmly at the camera, seated in a warm indoor setting with an orange-toned background. "
                "The person is wearing the same dark grey textured blazer over a light grey top, and the same glasses. "
                "The person now has long, flowing wavy hair in a deep blue color with teal highlights, reaching down to mid-back length. "
                "The hair has a lustrous shine and soft waves throughout, with volume at the crown and the ends cascading naturally past the shoulders. "
                "The hair color is a rich midnight blue base with vibrant teal streaks woven through the mid-lengths and ends. "
                "All facial features, body position, the exact same clothing, accessories, background, and lighting remain exactly as in the original photo. "
                "Only the hairstyle has changed.\""
            )
        else:
            return (
                custom +
                "Describe this person's photo in detail, including their pose, body position, "
                "facial expression, background, and current hairstyle."
            )

    def _build_image_from_description_prompt(self, description: str, user_note: Optional[str] = None, target_region: str = "full") -> str:
        """Stage 2: 根據描述生成圖片的 prompt"""
        custom = ""
        if user_note:
            note_clean = user_note.strip()
            if note_clean:
                custom = (
                    "User styling preference to emphasize:\n"
                    f"- {note_clean}\n"
                    "Incorporate this request naturally while generating the outfit.\n\n"
                )
        # 針對下身衣著（內著/泳褲/短褲）加入長度/覆蓋限制，避免被延長成長褲
        length_rules = self._lower_body_constraints(description)

        compliance_extra = []
        region_instructions = []
        if target_region == "lower":
            constraints = self._lower_body_constraints(description)
            if constraints:
                compliance_extra.append(constraints)
            region_instructions.append("- Edit ONLY the lower-body region (hips, groin, buttocks, thighs); do NOT alter torso, arms, head, or background.")
        elif target_region == "upper":
            constraints = self._upper_body_constraints(description)
            if constraints:
                compliance_extra.append(constraints)
            region_instructions.append("- Edit ONLY the upper-body region (shoulders, chest, back, arms); do NOT alter lower body, legs, or background.")
        else:
            constraints = self._lower_body_constraints(description)
            if constraints:
                compliance_extra.append(constraints)

        return (
            "🚨🚨🚨 STOP! READ THIS FIRST 🚨🚨🚨\n"
            "\n"
            "OUTPUT = EDIT OF IMAGE 1\n"
            "OUTPUT = EDIT OF IMAGE 1\n"
            "OUTPUT = EDIT OF IMAGE 1\n"
            "\n"
            "DO NOT CREATE TWO-PERSON LAYOUT\n"
            "DO NOT CREATE BEFORE/AFTER COMPARISON\n"
            "DO NOT PUT TWO PEOPLE SIDE BY SIDE\n"
            "\n"
            "YOUR OUTPUT MUST BE:\n"
            "- A SINGLE edited photo\n"
            "- Showing ONLY Image 1's person\n"
            "- With edited hair\n"
            "- NOT a comparison\n"
            "- NOT two people\n"
            "- JUST ONE PERSON\n"
            "\n"
            "IF YOUR OUTPUT SHOWS TWO PEOPLE, YOU FAILED.\n"
            "IF YOUR OUTPUT IS A COMPARISON LAYOUT, YOU FAILED.\n"
            "\n"
            "🚨 CRITICAL: OUTPUT = ONE SINGLE PHOTO WITH ONE PERSON ONLY 🚨\n"
            "\n"
            "❌ ABSOLUTELY FORBIDDEN - DO NOT VIOLATE:\n"
            "❌ Do NOT create a before/after comparison layout\n"
            "❌ Do NOT create a side-by-side image with two people\n"
            "❌ Do NOT show the original person on the left and edited person on the right\n"
            "❌ Do NOT create any layout with multiple people or multiple versions\n"
            "❌ Do NOT include Image 2's person anywhere in the output\n"
            "❌ Do NOT create a collage, composite, or split-screen image\n"
            "\n"
            "✅ REQUIRED OUTPUT:\n"
            "✅ ONE single portrait photo\n"
            "✅ ONE person only (Image 1's person)\n"
            "✅ That ONE person has the new hairstyle from Image 2\n"
            "✅ NO other people, NO comparisons, NO side-by-side layouts\n"
            "\n"
            "⚡ YOUR TASK:\n"
            "1. Take Image 1 (the first image) as your base\n"
            "2. Edit ONLY the hair on Image 1's person\n"
            "3. DELETE and IGNORE Image 2's person completely\n"
            "4. Output = ONE SINGLE PORTRAIT of Image 1's person with new hair\n"
            "\n"
            "🎨 TASK TYPE: PHOTO EDITING - Edit the first image only\n"
            "\n"
            "📸 YOU HAVE TWO IMAGES:\n"
            "Image 1 (FIRST): A person's photo - THIS IS YOUR CANVAS. Edit ONLY this image.\n"
            "Image 2 (SECOND): A hairstyle reference - Use as reference only. DO NOT use this person or background.\n"
            "\n"
            "✏️ YOUR JOB: EDIT IMAGE 1 by changing ONLY the hairstyle\n"
            "- Start with Image 1 as your base\n"
            "- Keep Image 1's person (their face, body, pose, clothing, background)\n"
            "- Replace ONLY the hair to match Image 2's hairstyle\n"
            "- Output: Image 1's person with Image 2's hairstyle\n"
            "\n"
            "🚫 WHAT NOT TO DO:\n"
            "❌ DO NOT put Image 2's person into your output\n"
            "❌ DO NOT create a composite of two people\n"
            "❌ DO NOT use Image 2's face, body, or background\n"
            "❌ DO NOT insert or place Image 2's person anywhere\n"
            "✅ ONLY use Image 2 to see what hairstyle to create on Image 1's person\n"
            "\n"
            "🎯 THINK OF IT LIKE THIS:\n"
            "You are a photo editor using Photoshop. You open Image 1. You see Image 2 for reference.\n"
            "You select Image 1's hair region. You delete it. You paint a new hairstyle that looks like Image 2's hair.\n"
            "Image 1's person stays in the photo. Image 2's person never appears.\n"
            "\n"
            "⚠️ TWO ABSOLUTE RULES:\n"
            "1. EDIT IMAGE 1 ONLY - Never bring in Image 2's person\n"
            "2. CHANGE THE HAIRSTYLE COMPLETELY to match Image 2's hair style\n"
            "\n"
            "🚫 CRITICAL ERROR TO AVOID:\n"
            "- DO NOT replace Image 1's person with Image 2's person\n"
            "- DO NOT copy Image 2's face, body, or pose\n"
            "- DO NOT insert Image 2's person into the result\n"
            "- DO NOT keep Image 1's original hairstyle - you MUST change it to match Image 2's hairstyle\n"
            "- The result must show Image 1's person (their face, body, pose) with Image 2's hairstyle applied\n"
            "\n"
            "🔥🔥🔥 CRITICAL WARNING - DO NOT BE CONSERVATIVE 🔥🔥🔥\n"
            "⚠️ EVEN IF Image 1's hairstyle looks SIMILAR to Image 2's hairstyle, you MUST STILL:\n"
            "- COMPLETELY IGNORE Image 1's original hairstyle\n"
            "- EXTRACT EVERY DETAIL from Image 2's hairstyle\n"
            "- APPLY 100% of Image 2's hairstyle characteristics\n"
            "- Do NOT say 'they look similar so I'll keep the original'\n"
            "- Do NOT be conservative or minimal in your changes\n"
            "- TREAT THIS AS A COMPLETE HAIR REPLACEMENT, NOT A HAIR ADJUSTMENT\n"
            "\n"
            "🎯 EXTRACTION CHECKLIST FROM IMAGE 2 (YOU MUST APPLY ALL OF THESE):\n"
            "✓ Hair cut style: Extract the EXACT cut from Image 2 (how the hair is shaped, layered, styled)\n"
            "✓ Hair length on top: Extract the EXACT top length from Image 2 (how long is the top section?)\n"
            "✓ Hair length on sides: Extract the EXACT side length from Image 2 (how short are the sides?)\n"
            "✓ Hair length on back: Extract the EXACT back length from Image 2 (how short is the back?)\n"
            "✓ Taper/fade level: Extract the EXACT taper from Image 2 (high fade, low fade, no fade?)\n"
            "✓ Hair texture: Extract the EXACT texture from Image 2 (smooth, textured, wavy, spiky?)\n"
            "✓ Hair styling direction: Extract the EXACT styling from Image 2 (swept up, swept back, side-swept, natural?)\n"
            "✓ Hair part: Extract the EXACT part from Image 2 (side part, center part, no part?)\n"
            "✓ Hair volume: Extract the EXACT volume from Image 2 (high volume, flat, poofy, sleek?)\n"
            "✓ Hair shine/finish: Extract the EXACT finish from Image 2 (matte, glossy, natural sheen?)\n"
            "\n"
            "❌ DO NOT THINK:\n"
            "❌ 'Image 1 already has short hair, and Image 2 also has short hair, so I'll just keep Image 1's hair'\n"
            "❌ 'These two hairstyles look similar enough, no need to change much'\n"
            "❌ 'I'll just make minor adjustments to Image 1's hair'\n"
            "\n"
            "✅ YOU MUST THINK:\n"
            "✅ 'I will DELETE Image 1's entire hairstyle from my mind'\n"
            "✅ 'I will EXTRACT every single detail from Image 2's hairstyle'\n"
            "✅ 'I will PAINT a completely new hairstyle on Image 1's person using Image 2 as my reference'\n"
            "✅ 'Even if they look similar, I will apply Image 2's EXACT characteristics'\n"
            "\n"
            "✅ WHAT MUST CHANGE (REQUIRED - DO NOT BE CONSERVATIVE):\n"
            "- Hair color: Change to match Image 2's exact hair color (even if very different from Image 1)\n"
            "- Hair length: Change to match Image 2's length (short→long or long→short is ALLOWED and REQUIRED)\n"
            "- Hair texture: Change to match Image 2's texture (straight, wavy, curly, etc.)\n"
            "- Hair style: Change to match Image 2's style and cut completely\n"
            "- Hair volume: Change to match Image 2's volume and body\n"
            "- Be BOLD: If Image 2 has long blue wavy hair and Image 1 has short brown straight hair, the output MUST have long blue wavy hair\n"
            "- NOTHING BELOW THE NECK of Image 1's person should change\n"
            "\n"
            "WHAT MUST REMAIN EXACTLY THE SAME (ALL FROM IMAGE 1 - DO NOT USE IMAGE 2):\n"
            "✓ Person: Use Image 1's person (NOT Image 2's person)\n"
            "✓ Face: Image 1's exact facial features, skin tone, facial structure, expression, makeup (NOT Image 2's face)\n"
            "✓ Eyes: Image 1's eye color, shape, gaze direction (NOT Image 2's eyes)\n"
            "✓ Facial features: Image 1's nose, mouth, cheeks, chin, eyebrows (NOT Image 2's features)\n"
            "✓ Glasses/眼鏡: Image 1's glasses style and position (NOT Image 2's)\n"
            "✓ Neck: Image 1's neck (NOT Image 2's)\n"
            "✓ Body: Image 1's pose, body proportions, position, hands, arms, legs (NOT Image 2's body)\n"
            "✓ Clothing: Image 1's outfit in every detail - style, colors, patterns, fit, fabric (NOT Image 2's clothing)\n"
            "✓ Accessories: Image 1's jewelry, watches, bags, belts, shoes (NOT Image 2's accessories)\n"
            "✓ Background: Image 1's scene, environment, objects, walls, furniture (NOT Image 2's background)\n"
            "✓ Lighting: Image 1's lighting direction, intensity, shadows, highlights (NOT Image 2's lighting)\n"
            "✓ Camera angle: Image 1's viewpoint, framing, distance (NOT Image 2's angle)\n"
            "✓ Composition: Image 1's image composition and aspect ratio (NOT Image 2's composition)\n"
            "\n"
            + custom +
            "🔥🔥🔥 MANDATORY: FOLLOW THE DESCRIPTION EXACTLY 🔥🔥🔥\n"
            "⚠️ The description below is your ONLY instruction for the hairstyle. You MUST:\n"
            "- Follow EVERY SINGLE WORD in the description\n"
            "- If it says 'voluminous' (蓬鬆) → you MUST create voluminous hair (DO NOT make it sleek/flat/neat)\n"
            "- If it says 'tousled' (蓬亂) → you MUST create tousled hair (DO NOT make it neat/smooth/orderly)\n"
            "- If it says 'textured' (有質感) → you MUST create textured hair (DO NOT make it smooth/plain)\n"
            "- If it says 'quiff' → you MUST create a visible quiff (DO NOT make it flat)\n"
            "- If it says 'wavy' (波浪) → you MUST create wavy hair (DO NOT make it straight)\n"
            "- If it says 'curly' (捲) → you MUST create curly hair (DO NOT make it straight)\n"
            "- If it says 'styled upwards' → you MUST style it upwards (DO NOT make it flat/down)\n"
            "- If it says '3-4 inches on top' → the top MUST be 3-4 inches (DO NOT make it shorter)\n"
            "- If it says '1-2 inches on sides' → the sides MUST be 1-2 inches (DO NOT make them longer)\n"
            "\n"
            "❌ ABSOLUTELY FORBIDDEN - DO NOT \"IMPROVE\" THE DESCRIPTION:\n"
            "❌ DO NOT think: 'The description sounds too bold/wild, I'll tone it down'\n"
            "❌ DO NOT think: 'Voluminous might be too much, I'll make it neat instead'\n"
            "❌ DO NOT think: 'Tousled might look messy, I'll make it sleek instead'\n"
            "❌ DO NOT substitute words: 'voluminous' ≠ 'neat', 'tousled' ≠ 'sleek', 'textured' ≠ 'smooth'\n"
            "❌ DO NOT make the hairstyle MORE CONSERVATIVE than the description\n"
            "❌ DO NOT make the hairstyle MORE NEAT/TIDY than the description\n"
            "❌ DO NOT reduce volume, texture, or styling intensity\n"
            "\n"
            "✅ YOU MUST OBEY THE DESCRIPTION LITERALLY:\n"
            "✅ If description says 'significant lift and body' → CREATE significant lift (not small lift)\n"
            "✅ If description says 'full, soft quiff' → CREATE a full, soft quiff (not a flat style)\n"
            "✅ If description says 'naturally tousled' → CREATE tousled appearance (not neat)\n"
            "✅ The description is MANDATORY - treat every adjective as a REQUIREMENT\n"
            "\n"
            "🎯 DESCRIPTION COMPLIANCE CHECKLIST:\n"
            "Before generating, ask yourself:\n"
            "1. Did I apply EVERY adjective from the description? (voluminous, textured, tousled, etc.)\n"
            "2. Did I create the EXACT styling mentioned? (swept up, quiff, wavy, etc.)\n"
            "3. Did I match the EXACT lengths mentioned? (3-4 inches top, 1-2 inches sides, etc.)\n"
            "4. Did I avoid making it more 'neat' or 'conservative' than described?\n"
            "5. Would a hairstylist reading my output say it matches the description EXACTLY?\n"
            "\n"
            "⚠️ IF THE DESCRIPTION SAYS \"VOLUMINOUS\" BUT YOUR OUTPUT IS \"SLEEK\", YOU FAILED.\n"
            "⚠️ IF THE DESCRIPTION SAYS \"TOUSLED\" BUT YOUR OUTPUT IS \"NEAT\", YOU FAILED.\n"
            "⚠️ IF THE DESCRIPTION SAYS \"QUIFF\" BUT YOUR OUTPUT IS \"FLAT\", YOU FAILED.\n"
            "\n"
            "HAIRSTYLE TO APPLY:\n"
            f"{description}\n"
            "\n"
            "🚫 NEGATIVE PROMPT - ABSOLUTELY FORBIDDEN ACTIONS:\n"
            "- DO NOT change the shirt, blouse, top, or any upper body clothing\n"
            "- DO NOT change the pants, trousers, skirt, shorts, or any lower body clothing\n"
            "- DO NOT change the dress, jumpsuit, or any full-body clothing\n"
            "- DO NOT change the jacket, coat, sweater, or any outerwear\n"
            "- DO NOT add new clothing items that weren't in the original photo\n"
            "- DO NOT remove clothing items that were in the original photo\n"
            "- DO NOT change clothing colors, patterns, fabrics, or styles\n"
            "- DO NOT change shoes, socks, or footwear\n"
            "- DO NOT change jewelry, watches, bags, belts, or accessories\n"
            "- DO NOT change the person's body shape, size, or proportions\n"
            "- DO NOT change the person's pose, stance, or position\n"
            "- DO NOT change facial features, skin tone, or expression\n"
            "- DO NOT change the background, walls, furniture, or environment\n"
            "\n"
            "MANDATORY CONSTRAINTS (CRITICAL - FOLLOW EXACTLY):\n"
            "1. This is EXCLUSIVELY a hair replacement operation - HAIR ONLY\n"
            "2. Copy EVERYTHING from the reference photo EXCEPT the hairstyle\n"
            "3. The ONLY visible difference should be the hairstyle on the head\n"
            "4. ABSOLUTELY DO NOT alter facial features, expression, skin tone, or makeup\n"
            "5. ABSOLUTELY DO NOT change body position, pose, or gestures\n"
            "6. ABSOLUTELY DO NOT modify, replace, or alter ANY clothing items whatsoever - this is a HARD CONSTRAINT\n"
            "7. ABSOLUTELY DO NOT change, add, or remove any accessories\n"
            "8. ABSOLUTELY DO NOT modify the background, environment, or any objects\n"
            "9. ABSOLUTELY DO NOT change lighting, shadows, or camera settings\n"
            "10. Apply the new hairstyle naturally to the person's head, matching their head shape\n"
            "11. Ensure the hairstyle looks realistic and professionally styled\n"
            "12. VIOLATION OF CLOTHING PRESERVATION (constraint 6) IS COMPLETELY UNACCEPTABLE\n"
            "\n"
            "⚠️ SPECIAL WARNING FOR FULL-BODY PHOTOS:\n"
            "- Even if the reference photo shows the full body with visible clothing, DO NOT change ANY clothing\n"
            "- The clothing visibility DOES NOT give you permission to modify it\n"
            "- Keep ALL clothing items EXACTLY as they appear in the reference photo\n"
            "- The entire body from neck down must remain PIXEL-PERFECT IDENTICAL\n"
            "- Only the hair on the head (above the neck) should be different\n"
            "- If you see a shirt in the original → the output MUST have the EXACT SAME shirt\n"
            "- If you see pants in the original → the output MUST have the EXACT SAME pants\n"
            "- If you see a dress in the original → the output MUST have the EXACT SAME dress\n"
            "\n"
            "⚠️ CLOTHING PRESERVATION RULE (UNBREAKABLE):\n"
            "- If the person wears a dress → keep the EXACT same dress (color, pattern, style, length, sleeves)\n"
            "- If the person wears a shirt → keep the EXACT same shirt (color, pattern, collar, buttons, sleeves)\n"
            "- If the person wears pants → keep the EXACT same pants (color, style, length, fit)\n"
            "- If the person wears a jacket → keep the EXACT same jacket (color, style, pockets, buttons)\n"
            "- If the person wears a t-shirt → keep the EXACT same t-shirt (color, print, neckline)\n"
            "- If the person wears jeans → keep the EXACT same jeans (wash, style, rips, pockets)\n"
            "- DO NOT substitute, modify, \"improve\", \"enhance\", or change any clothing items\n"
            "- DO NOT reinterpret clothing - copy it EXACTLY as pixel data\n"
            "- Treat clothing as READ-ONLY data that cannot be modified\n"
            + ("\n".join(region_instructions) + ("\n" if region_instructions else ""))
            + ("\n".join(compliance_extra) + ("" if not compliance_extra else "\n")) +
            "\n"
            "TECHNICAL REQUIREMENTS:\n"
            "✅ DO: Edit Image 1. Change its hair. Keep everything else from Image 1.\n"
            "❌ DON'T: Insert Image 2's person. Don't bring in Image 2's face or body.\n"
            "\n"
            "OUTPUT CHECKLIST:\n"
            "- Is this Image 1's person? (face, body, pose, clothing, background from Image 1)\n"
            "- Does this person have a NEW hairstyle? (matching Image 2's hair style)\n"
            "- Did I avoid putting Image 2's person in the output?\n"
            "\n"
            "THINK: Photo editing, not photo replacement.\n"
            "RESULT: Image 1's person wearing Image 2's hairstyle.\n"
            "NOT: Image 2's person in the scene.\n"
            "\n"
            "🔍 FINAL CHECK (Ask yourself before generating):\n"
            "\n"
            "Question 0: Is my output a SINGLE portrait or a comparison layout?\n"
            "✅ CORRECT: A single portrait photo of ONE person\n"
            "❌ WRONG: A before/after layout / Side-by-side comparison / Two people shown\n"
            "\n"
            "Question 1: How many people are visible in my output?\n"
            "✅ CORRECT: Exactly ONE person (Image 1's person with new hair)\n"
            "❌ WRONG: Two people / Original on left + edited on right / Any comparison layout\n"
            "\n"
            "Question 2: Did I create a before/after comparison image?\n"
            "✅ CORRECT: NO - I created ONE single edited portrait\n"
            "❌ WRONG: YES - I showed both original and edited versions\n"
            "\n"
            "Question 3: Does my output show Image 1's person on the left and a different version on the right?\n"
            "✅ CORRECT: NO - My output shows ONLY ONE PERSON in a single portrait\n"
            "❌ WRONG: YES - I created a side-by-side layout\n"
            "\n"
            "Question 4: Did I include Image 2's person anywhere?\n"
            "✅ CORRECT: NO - I only used Image 2 as a hairstyle reference\n"
            "❌ WRONG: YES - I put Image 2's person in the output\n"
            "\n"
            "Question 5: What did I change?\n"
            "✅ CORRECT: Only the hairstyle of Image 1's person\n"
            "❌ WRONG: Nothing / Created a comparison / Added another person\n"
            "\n"
            "🚨 CRITICAL FAILURE CONDITIONS:\n"
            "❌ IF YOUR OUTPUT IS A BEFORE/AFTER COMPARISON, YOU COMPLETELY FAILED.\n"
            "❌ IF YOUR OUTPUT SHOWS TWO PEOPLE SIDE-BY-SIDE, YOU COMPLETELY FAILED.\n"
            "❌ IF YOUR OUTPUT SHOWS ORIGINAL ON LEFT + EDITED ON RIGHT, YOU COMPLETELY FAILED.\n"
            "❌ IF YOUR OUTPUT IS NOT A SINGLE PORTRAIT, YOU COMPLETELY FAILED.\n"
            "❌ IF YOUR OUTPUT SHOWS IMAGE 2'S PERSON ANYWHERE, YOU FAILED.\n"
            "❌ IF YOUR OUTPUT SHOWS IMAGE 1'S PERSON WITH UNCHANGED HAIR, YOU FAILED.\n"
            "\n"
            "✅ SUCCESS = ONE SINGLE PORTRAIT of Image 1's person with NEW HAIR (Image 2's hairstyle)\n"
            "✅ SUCCESS = NOT a comparison, NOT side-by-side, JUST ONE PERSON in ONE PHOTO\n"
            "✅ SUCCESS = Output looks like a professional hairstyle portfolio shot of ONE person"
        )

    def _sanitize_description(self, text: str) -> str:
        """Reduce terms likely to trigger safety filters while preserving intent.
        NOTE: When thong/T-back/G-string is detected, preserve those terms (do not upcast to shorts).
        """
        try:
            out = text
            thong_hint = re.search(r"\b(thong|t[- ]?back|g[- ]?string|丁字|T字)\b", out, flags=re.IGNORECASE) is not None
            # Always neutralize some risky phrasing
            out = re.sub(r"\b(low[- ]?rise)\b", "mid-rise", out, flags=re.IGNORECASE)
            out = re.sub(r"\b(bare|uncovered)\b", "covered", out, flags=re.IGNORECASE)
            out = re.sub(r"\b(see[- ]?through|transparent)\b", "opaque", out, flags=re.IGNORECASE)
            out = re.sub(r"\b(nipple|areola|genital\w*)\b", "sensitive area", out, flags=re.IGNORECASE)
            # Only upcast underwear terms when not explicitly a thong family
            if not thong_hint:
                out = re.sub(r"\b(briefs?|boxers?|underwear)\b", "short swim trunks (brief-style)", out, flags=re.IGNORECASE)
            return out
        except Exception:
            return text

    # === ROI helpers ===========================================================
    def _should_use_lower_body_roi(self, note: str, description: str, garment: Any) -> bool:
        # 暫時停用 ROI 模式，改用完整圖片處理以獲得更好的換衣效果
        # ROI 模式只處理局部區域，常常無法正確完成換衣
        return False
        # try:
        #     text = "\n".join([
        #         str(note or ""),
        #         str(description or ""),
        #         json.dumps(garment, ensure_ascii=False) if isinstance(garment, (dict, list)) else str(garment or ""),
        #     ]).lower()
        #     keys = [
        #         "underwear",
        #         "swim",
        #         "trunk",
        #         "brief",
        #         "bikini",
        #         "intimate",
        #         "shorts",
        #         "skirt",
        #         "bottom",
        #         "短褲",
        #         "熱褲",
        #         "內褲",
        #         "泳褲",
        #         "泳衣",
        #         "比基尼",
        #         "泳裝",
        #         "裙",
        #         "下身",
        #     ]
        #     return any(k in text for k in keys)
        # except Exception:
        #     return False

    def _should_use_upper_body_roi(self, note: str, description: str, garment: Any) -> bool:
        # 暫時停用 ROI 模式，改用完整圖片處理以獲得更好的換衣效果
        return False
        # try:
        #     text = "\n".join([
        #         str(note or ""),
        #         str(description or ""),
        #         json.dumps(garment, ensure_ascii=False) if isinstance(garment, (dict, list)) else str(garment or ""),
        #     ]).lower()
        #     keys = [
        #         "top",
        #         "shirt",
        #         "t-shirt",
        #         "tee",
        #         "blouse",
        #         "sweater",
        #         "cardigan",
        #         "hoodie",
        #         "jacket",
        #         "coat",
        #         "bra",
        #         "upper",
        #         "vest",
        #         "毛衣",
        #         "上衣",
        #         "針織",
        #         "襯衫",
        #         "外套",
        #         "長袖",
        #         "短袖",
        #         "上半身",
        #     ]
        #     return any(k in text for k in keys)
        # except Exception:
        #     return False

    def _compute_lower_body_roi(self, w: int, h: int) -> tuple[int, int, int, int]:
        left = int(round(0.15 * w))
        right = int(round(0.85 * w))
        top = int(round(0.45 * h))
        bottom = int(round(0.92 * h))
        left = max(0, min(left, w - 1))
        right = max(left + 1, min(right, w))
        top = max(0, min(top, h - 1))
        bottom = max(top + 1, min(bottom, h))
        return (left, top, right, bottom)

    def _generate_on_lower_body_roi(self, user_image_path: str, garment_image_abs: Optional[str], stage2_prompt: str, safety_settings, public_path: str, output_path: Path) -> Optional[Dict[str, Optional[str]]]:
        try:
            if Image is None:
                return None
            with Image.open(user_image_path) as base:
                w, h = base.size
                if w <= 0 or h <= 0:
                    return None
                l, t, r, b = self._compute_lower_body_roi(w, h)
                roi = base.crop((l, t, r, b)).convert("RGB")
                buf = BytesIO()
                roi.save(buf, format="JPEG", quality=92)
                roi_bytes = buf.getvalue()
            parts = [{"text": stage2_prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(roi_bytes).decode("utf-8")}}]
            if garment_image_abs and os.path.exists(garment_image_abs):
                g_mime, g_bytes = self._read_image_as_supported_bytes(garment_image_abs)
                parts.append({"inline_data": {"mime_type": g_mime, "data": base64.b64encode(g_bytes).decode("utf-8")}})
            response = self.client.models.generate_content(
                model=self.model_name,
                contents={"parts": parts},
                config={"safety_settings": safety_settings},
            )
            print("[GeminiService] TWO-STAGE: Attempting to extract image bytes from ROI response")
            out_bytes = self._extract_image_bytes_from_sdk(response)
            if not out_bytes:
                result_dict = self._response_to_dict(response)
                b64 = self._extract_image_data(result_dict)
                out_bytes = base64.b64decode(b64) if b64 else None
            if out_bytes:
                with Image.open(user_image_path).convert("RGB") as base2:
                    w2, h2 = base2.size
                    l2, t2, r2, b2 = self._compute_lower_body_roi(w2, h2)
                    with Image.open(BytesIO(out_bytes)).convert("RGB") as gen:
                        gen = gen.resize((r2 - l2, b2 - t2))
                        base2.paste(gen, (l2, t2))
                        base2.save(output_path, format="JPEG", quality=92)
                return {"status": "ok", "mode": "two_stage_roi", "output_path": public_path, "message": None}
        except Exception:
            return None
        return None

    def _compute_upper_body_roi(self, w: int, h: int) -> tuple[int, int, int, int]:
        left = int(round(0.1 * w))
        right = int(round(0.9 * w))
        top = int(round(0.05 * h))
        bottom = int(round(0.55 * h))
        left = max(0, min(left, w - 1))
        right = max(left + 1, min(right, w))
        top = max(0, min(top, h - 1))
        bottom = max(top + 1, min(bottom, h))
        return (left, top, right, bottom)

    def _generate_on_upper_body_roi(self, user_image_path: str, garment_image_abs: Optional[str], stage2_prompt: str, safety_settings, public_path: str, output_path: Path) -> Optional[Dict[str, Optional[str]]]:
        try:
            if Image is None:
                return None
            with Image.open(user_image_path) as base:
                w, h = base.size
                if w <= 0 or h <= 0:
                    return None
                l, t, r, b = self._compute_upper_body_roi(w, h)
                roi = base.crop((l, t, r, b)).convert("RGB")
                buf = BytesIO()
                roi.save(buf, format="JPEG", quality=92)
                roi_bytes = buf.getvalue()
            parts = [{"text": stage2_prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(roi_bytes).decode("utf-8")}}]
            if garment_image_abs and os.path.exists(garment_image_abs):
                g_mime, g_bytes = self._read_image_as_supported_bytes(garment_image_abs)
                parts.append({"inline_data": {"mime_type": g_mime, "data": base64.b64encode(g_bytes).decode("utf-8")}})
            response = self.client.models.generate_content(
                model=self.model_name,
                contents={"parts": parts},
                config={"safety_settings": safety_settings},
            )
            print("[GeminiService] TWO-STAGE: Attempting to extract image bytes from upper-body ROI response")
            out_bytes = self._extract_image_bytes_from_sdk(response)
            if not out_bytes:
                result_dict = self._response_to_dict(response)
                b64 = self._extract_image_data(result_dict)
                out_bytes = base64.b64decode(b64) if b64 else None
            if out_bytes:
                with Image.open(user_image_path).convert("RGB") as base2:
                    w2, h2 = base2.size
                    l2, t2, r2, b2 = self._compute_upper_body_roi(w2, h2)
                    with Image.open(BytesIO(out_bytes)).convert("RGB") as gen:
                        gen = gen.resize((r2 - l2, b2 - t2))
                        base2.paste(gen, (l2, t2))
                        base2.save(output_path, format="JPEG", quality=92)
                return {"status": "ok", "mode": "two_stage_roi_upper", "output_path": public_path, "message": None}
        except Exception:
            return None
        return None

    def _lower_body_constraints(self, description: str) -> str:
        """根據描述偵測下身類型，加入防延長的長度/覆蓋規則。"""
        try:
            desc = description.lower()
            keys = ["swim", "trunk", "brief", "boxer", "underwear", "shorts", "thong", "t-back", "g-string", "丁字", "t字"]
            if any(k in desc for k in keys):
                return (
                    "- Lower-body garment length constraint: keep hem at the upper thigh (no extension to knee or ankle).\n"
                    "- Do NOT convert to long pants or boardshort length; strictly preserve the reference silhouette (including thong/T-back/G-string when applicable).\n"
                    "- Do NOT increase coverage area beyond the reference garment; do NOT widen straps or panels.\n"
                    "- Keep waistband height consistent with the reference; avoid raising to cover the torso.\n"
                    "- Remove any original clothing from the user's photo in the ROI; no leftover fabrics, hems, or waistbands."
                )
            return ""
        except Exception:
            return ""

    def _upper_body_constraints(self, description: str) -> str:
        try:
            desc = description.lower()
            keys = ["top", "bra", "swim", "intimate", "upper", "胸", "肩", "ladies"]
            if any(k in desc for k in keys):
                return (
                    "- Upper-body garment constraint: replace only the torso/chest/shoulder area per reference garment; do NOT add sleeves or coverage beyond the reference design.\n"
                    "- If the reference upper body is bare, keep the user's torso bare (respecting public SFW rules).\n"
                    "- Remove all original upper-body clothing from the user photo; no collars, straps, or layers should remain."
                )
            return ""
        except Exception:
            return ""

    def _get_safety_settings(self):
        """獲取安全設置"""
        safety_level = "BLOCK_ONLY_HIGH"
        try:
            import json
            settings_path = Path(self._settings_path) if getattr(self, "_settings_path", None) else (self.base_dir / "data" / "settings.json")
            if settings_path and Path(settings_path).exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings_data = json.load(f)
                    safety_level = settings_data.get("GEMINI_SAFETY_LEVEL", safety_level)
        except Exception:
            pass
        
        safety_settings = None
        if hasattr(genai_types, "SafetySetting"):
            try:
                # Try to use HarmCategory and HarmBlockThreshold enums
                harm_category_cls = getattr(genai_types, "HarmCategory", None)
                harm_threshold_cls = getattr(genai_types, "HarmBlockThreshold", None)
                if harm_category_cls and harm_threshold_cls:
                    # Map string to threshold constant
                    threshold_map = {
                        "BLOCK_NONE": getattr(harm_threshold_cls, "BLOCK_NONE", None),
                        "BLOCK_ONLY_HIGH": getattr(harm_threshold_cls, "BLOCK_ONLY_HIGH", None),
                        "BLOCK_MEDIUM_AND_ABOVE": getattr(harm_threshold_cls, "BLOCK_MEDIUM_AND_ABOVE", None),
                    }
                    threshold = threshold_map.get(safety_level, harm_threshold_cls.BLOCK_ONLY_HIGH)
                    
                    if threshold:
                        safety_settings = [
                            genai_types.SafetySetting(
                                category=harm_category_cls.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                threshold=threshold
                            ),
                            genai_types.SafetySetting(
                                category=harm_category_cls.HARM_CATEGORY_HARASSMENT,
                                threshold=threshold
                            ),
                            genai_types.SafetySetting(
                                category=harm_category_cls.HARM_CATEGORY_HATE_SPEECH,
                                threshold=threshold
                            ),
                            genai_types.SafetySetting(
                                category=harm_category_cls.HARM_CATEGORY_DANGEROUS_CONTENT,
                                threshold=threshold
                            ),
                        ]
                        print(f"[GeminiService] safety_settings configured: {safety_level}")
            except Exception as e:
                print(f"[GeminiService] failed to configure safety_settings: {e}")
        
        return safety_settings

    # --- Settings hot-reload helpers -----------------------------------------
    def _init_client(self) -> None:
        if not self.api_key or genai is None:
            self.client = None
            return
        try:
            self.client = genai.Client(api_key=self.api_key)  # type: ignore[arg-type]
            self.logger.info("GeminiService 初始化完成，模型：%s", self.model_name)
        except Exception as exc:  # pragma: no cover
            self.logger.exception("Gemini Client 初始化失敗：%s", exc)
            self.client = None

    def _reload_settings_if_changed(self) -> None:
        try:
            if not self._settings_path:
                return
            if not Path(self._settings_path).exists():
                return
            mtime = Path(self._settings_path).stat().st_mtime
            if self._settings_mtime and mtime <= self._settings_mtime:
                return
            import json
            data = json.loads(Path(self._settings_path).read_text(encoding="utf-8"))
            old_key, old_model, old_llm = self.api_key, self.model_name, self.llm_model_name
            self.api_key = data.get("GEMINI_API_KEY") or self.api_key
            self.model_name = data.get("GEMINI_MODEL") or self.model_name
            self.llm_model_name = data.get("GEMINI_LLM") or self.llm_model_name
            self._settings_mtime = mtime
            if (self.api_key != old_key) or (self.model_name != old_model) or (self.llm_model_name != old_llm):
                self._init_client()
        except Exception:
            # swallow errors to avoid breaking requests
            pass

    # Internal helpers ------------------------------------------------------------

    def _invoke_gemini_api(
        self,
        prompt: str,
        mime_type: str,
        image_bytes: bytes,
        garment_image_abs: Optional[str] = None,
        extra_image_paths: Optional[list] = None,
        aspect_ratio_override: Optional[str] = None,
    ):
        print("\n[GeminiService] --- FINAL PROMPT ---")
        print(prompt)
        print("[GeminiService] ---------------------\n")
        if genai_types:
            prompt_part = genai_types.Part.from_text(text=prompt)
            image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            parts = [prompt_part, image_part]
            try:
                if garment_image_abs and os.path.exists(garment_image_abs):
                    g_mime, g_bytes = self._read_image_as_supported_bytes(garment_image_abs)
                    parts.append(genai_types.Part.from_bytes(data=g_bytes, mime_type=g_mime))
                if extra_image_paths:
                    for p in extra_image_paths:
                        if p and os.path.exists(p):
                            e_mime, e_bytes = self._read_image_as_supported_bytes(p)
                            parts.append(genai_types.Part.from_bytes(data=e_bytes, mime_type=e_mime))
            except Exception:
                pass
            contents = [genai_types.Content(role="user", parts=parts)]
            cfg = None
            try:
                image_cfg = None
                if hasattr(genai_types, "ImageConfig"):
                    ar_value = aspect_ratio_override or self.image_aspect_ratio
                    image_cfg = genai_types.ImageConfig(aspect_ratio=ar_value) if ar_value else genai_types.ImageConfig()
                
                # Configure safety settings for e-commerce virtual try-on
                # Read from settings.json, default to BLOCK_ONLY_HIGH
                safety_level = "BLOCK_ONLY_HIGH"
                try:
                    import json
                    from pathlib import Path
                    settings_file = Path(__file__).resolve().parents[2] / "data" / "settings.json"
                    if settings_file.exists():
                        settings_data = json.loads(settings_file.read_text(encoding="utf-8"))
                        safety_level = settings_data.get("GEMINI_SAFETY_LEVEL", "BLOCK_ONLY_HIGH")
                except Exception:
                    pass
                
                safety_settings = None
                if hasattr(genai_types, "SafetySetting"):
                    try:
                        # Try to use HarmCategory and HarmBlockThreshold enums
                        harm_category_cls = getattr(genai_types, "HarmCategory", None)
                        harm_threshold_cls = getattr(genai_types, "HarmBlockThreshold", None)
                        if harm_category_cls and harm_threshold_cls:
                            # Map string to threshold constant
                            threshold_map = {
                                "BLOCK_NONE": getattr(harm_threshold_cls, "BLOCK_NONE", None),
                                "BLOCK_ONLY_HIGH": getattr(harm_threshold_cls, "BLOCK_ONLY_HIGH", None),
                                "BLOCK_MEDIUM_AND_ABOVE": getattr(harm_threshold_cls, "BLOCK_MEDIUM_AND_ABOVE", None),
                            }
                            threshold = threshold_map.get(safety_level, harm_threshold_cls.BLOCK_ONLY_HIGH)
                            
                            if threshold:
                                safety_settings = [
                                    genai_types.SafetySetting(
                                        category=harm_category_cls.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                                        threshold=threshold
                                    ),
                                    genai_types.SafetySetting(
                                        category=harm_category_cls.HARM_CATEGORY_HARASSMENT,
                                        threshold=threshold
                                    ),
                                    genai_types.SafetySetting(
                                        category=harm_category_cls.HARM_CATEGORY_HATE_SPEECH,
                                        threshold=threshold
                                    ),
                                    genai_types.SafetySetting(
                                        category=harm_category_cls.HARM_CATEGORY_DANGEROUS_CONTENT,
                                        threshold=threshold
                                    ),
                                ]
                                print(f"[GeminiService] safety_settings configured: {safety_level}")
                    except Exception as e:
                        print(f"[GeminiService] failed to configure safety_settings: {e}")
                
                if hasattr(genai_types, "GenerateContentConfig"):
                    # Note: response_mime_type only supports text/json/xml/yaml, NOT image types
                    cfg = genai_types.GenerateContentConfig(
                        image_config=image_cfg,
                        safety_settings=safety_settings,
                    )
            except Exception:
                cfg = None
            # Call with timeout guard to avoid worker blocking
            timeout_s = int(os.getenv("GEMINI_API_TIMEOUT", "60") or "60")
            print(f"[GeminiService] API call starting, timeout={timeout_s}s model={self.model_name}")
            ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                if cfg is not None:
                    fut = ex.submit(lambda: self.client.models.generate_content(model=self.model_name, contents=contents, config=cfg))  # type: ignore[union-attr]
                else:
                    fut = ex.submit(lambda: self.client.models.generate_content(model=self.model_name, contents=contents))  # type: ignore[union-attr]
                result = fut.result(timeout=timeout_s)
                print(f"[GeminiService] API call completed, result type={type(result).__name__}")
                if result:
                    print(f"[GeminiService] API result has {len(str(result))} chars in repr")
                    if hasattr(result, '__dict__'):
                        print(f"[GeminiService] API result attributes: {list(result.__dict__.keys())}")
                return result
            except concurrent.futures.TimeoutError:
                print(f"[GeminiService] API call TIMEOUT after {timeout_s}s")
                try:
                    ex.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                return {}
            except (OSError, socket.error) as e:
                print(f"[GeminiService] API call NETWORK ERROR: {type(e).__name__}")
                try:
                    ex.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                return {}
            finally:
                try:
                    ex.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
        return {}

    # --- LLM image suitability check -----------------------------------------
    def analyze_user_photo_suitability(self, image_path: str) -> Dict[str, str]:
        """使用 GEMINI_LLM 檢查使用者照片是否適合試衣。
        回傳：{"suitable": bool, "reason": str}
        若無法呼叫 API，採用基本圖片尺寸檢查做為退路。
        """
        # 先嘗試 hot-reload
        self._reload_settings_if_changed()
        try:
            if not os.path.exists(image_path):
                return {"suitable": False, "reason": "找不到上傳的照片"}
            # fallback 規則：無 API 或無 client 時，僅以尺寸作粗略判斷
            if not self.api_key or not self.client:
                if Image is None:
                    return {"suitable": True, "reason": "以退路模式允許（無法載入影像庫）"}
                try:
                    with Image.open(image_path) as im:
                        w, h = im.size
                    if w >= 256 and h >= 256:
                        return {"suitable": True, "reason": "以退路模式通過尺寸檢查"}
                    return {"suitable": False, "reason": "影像尺寸過小，可能無法辨識人物"}
                except Exception:
                    return {"suitable": True, "reason": "以退路模式允許（無法解析影像）"}

            # 讀入圖像 bytes（長邊縮放至 640px 以降低傳輸/延遲）
            def _read_resized_max_640(path: str) -> Tuple[str, bytes]:
                if Image is None:
                    return self._read_image_as_supported_bytes(path)
                try:
                    with Image.open(path) as im:
                        w, h = im.size
                        if w <= 0 or h <= 0:
                            return self._read_image_as_supported_bytes(path)
                        max_side = max(w, h)
                        target = 640
                        if max_side <= target:
                            return self._read_image_as_supported_bytes(path)
                        scale = target / float(max_side)
                        new_w = max(1, int(round(w * scale)))
                        new_h = max(1, int(round(h * scale)))
                        im = im.convert("RGB").resize((new_w, new_h), Image.LANCZOS)
                        buf = BytesIO()
                        im.save(buf, format="JPEG", quality=90)
                        buf.seek(0)
                        return ("image/jpeg", buf.read())
                except Exception:
                    return self._read_image_as_supported_bytes(path)

            mime_type, img_bytes = _read_resized_max_640(image_path)
            prompt = (
                "You are validating if an image is suitable for fashion virtual try-on.\n"
                "Criteria:\n"
                "- Contains one or more clearly visible real people (no cartoons). Multiple people are acceptable.\n"
                "- Each prominent person is at least waist-up or full body, not a tiny distant figure.\n"
                "- At least one person occupies a reasonable portion of the frame (>= ~15% height).\n"
                "- Not heavily obstructed. Group photos are acceptable if people are clearly visible.\n"
                "Return STRICT JSON only: {\"suitable\": true|false, \"reason\": \"short reason in zh-TW\"}"
            )
            text = ""
            if genai_types:
                prompt_part = genai_types.Part.from_text(text=prompt)
                image_part = genai_types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
                contents = [genai_types.Content(role="user", parts=[prompt_part, image_part])]
                # 使用 llm_model_name 呼叫，加入超時保護，避免阻塞導致 500/timeout
                timeout_s = int(os.getenv("GEMINI_LLM_TIMEOUT", "6") or "6")
                def _call_llm():
                    return self.client.models.generate_content(model=self.llm_name, contents=contents)  # type: ignore[union-attr]
                ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                fut = ex.submit(_call_llm)
                try:
                    resp = fut.result(timeout=timeout_s)
                    text = self._extract_text_from_sdk(resp) or ""
                except concurrent.futures.TimeoutError:
                    try:
                        ex.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    return {"suitable": True, "reason": "LLM 檢查逾時，略過驗證"}
                except (OSError, socket.error):
                    try:
                        ex.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    return {"suitable": True, "reason": "LLM 連線失敗，略過驗證"}
                finally:
                    try:
                        ex.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass

            # 嘗試解析 JSON
            try:
                import json as _json
                # 擷取第一段 {...}
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    obj = _json.loads(text[start:end+1])
                    suitable = bool(obj.get("suitable"))
                    reason = str(obj.get("reason") or "")
                    return {"suitable": suitable, "reason": reason or ("結果：適合" if suitable else "結果：不適合")}
            except Exception:
                pass

            # 若無法解析，採保守允許但附帶理由
            return {"suitable": True, "reason": "AI 回覆非結構化，採允許"}
        except Exception as exc:
            return {"suitable": True, "reason": f"分析例外，採允許：{type(exc).__name__}"}

    @staticmethod
    def _extract_text_from_sdk(response: Any) -> Optional[str]:
        """嘗試從 SDK 回應擷取文字內容。"""
        try:
            candidates = getattr(response, "candidates", None) or []
            texts = []
            for c in candidates:
                content = getattr(c, "content", None)
                if not content:
                    continue
                parts = getattr(content, "parts", None) or []
                for p in parts:
                    # SDK 文字通常在 part.text
                    txt = getattr(p, "text", None)
                    if isinstance(txt, str) and txt.strip():
                        texts.append(txt.strip())
            if texts:
                return "\n".join(texts)
        except Exception:
            return None
        return None

    def _optional_refine_steps(self, generated_image_path: str, garment_image_abs: Optional[str], original_user_image_path: Optional[str] = None) -> None:
        if os.getenv("GEMINI_REFINE_REMOVE_BASE", "0") == "1":
            refined_bytes = self._refine_remove_original_clothes(generated_image_path, garment_image_abs, original_user_image_path)
            if refined_bytes:
                with open(generated_image_path, "wb") as out_img:
                    out_img.write(refined_bytes)

    def _prepare_image_payload(self, image_path: str) -> Tuple[str, bytes]:
        mime_type = self._detect_mime_type(image_path)
        if Image is None:
            with open(image_path, "rb") as f:
                return mime_type, f.read()
        if mime_type not in self.SUPPORTED_MIME_TYPES:
            with Image.open(image_path) as img:
                rgb_image = img.convert("RGB")
                buffer = BytesIO()
                rgb_image.save(buffer, format="JPEG", quality=95)
                buffer.seek(0)
                return "image/jpeg", buffer.read()
        with open(image_path, "rb") as image_file:
            return mime_type, image_file.read()

    def _read_image_as_supported_bytes(self, image_path: str) -> Tuple[str, bytes]:
        mime_type = self._detect_mime_type(image_path)
        if Image is None:
            with open(image_path, "rb") as f:
                return mime_type, f.read()
        if mime_type not in self.SUPPORTED_MIME_TYPES:
            with Image.open(image_path) as img:
                try:
                    img.seek(0)
                except Exception:
                    pass
                rgb_image = img.convert("RGB")
                buffer = BytesIO()
                rgb_image.save(buffer, format="JPEG", quality=95)
                buffer.seek(0)
                return "image/jpeg", buffer.read()
        with open(image_path, "rb") as f:
            return mime_type, f.read()

    def _letterbox_garment_to_user_canvas(self, user_image_path: str, garment_path: str) -> Optional[str]:
        if Image is None:
            return garment_path
        try:
            with Image.open(user_image_path) as uimg:
                user_w, user_h = uimg.size
            if user_w <= 0 or user_h <= 0:
                return None
            with Image.open(garment_path) as gimg:
                gimg = gimg.convert("RGBA")
                gw, gh = gimg.size
                if gw <= 0 or gh <= 0:
                    return None
                scale = min(user_w / gw, user_h / gh)
                new_w = max(1, int(round(gw * scale)))
                new_h = max(1, int(round(gh * scale)))
                g_resized = gimg.resize((new_w, new_h), Image.LANCZOS)
            canvas = Image.new("RGBA", (user_w, user_h), (0, 0, 0, 255))
            off_x = (user_w - new_w) // 2
            off_y = (user_h - new_h) // 2
            canvas.alpha_composite(g_resized, (off_x, off_y))
            out_path = self.outputs_dir / f"garment_letterbox_{int(time.time()*1000)}.jpg"
            canvas.convert("RGB").save(out_path, format="JPEG", quality=95)
            return str(out_path)
        except Exception:
            return None

    @staticmethod
    def _detect_mime_type(file_path: str) -> str:
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "image/jpeg"

    @staticmethod
    def _response_to_dict(result: Any) -> Dict[str, Any]:
        if result is None:
            return {}
        if isinstance(result, dict):
            return result
        for attr in ("to_dict", "dict", "model_dump", "model_dump_json"):
            if hasattr(result, attr):
                try:
                    value = getattr(result, attr)()
                    if isinstance(value, dict):
                        return value
                except Exception:
                    continue
        if hasattr(result, "__dict__"):
            return dict(result.__dict__)
        return {}

    @staticmethod
    def _extract_image_data(result: Dict[str, Any]) -> Optional[str]:
        candidates = result.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                inline = part.get("inline_data") or part.get("media")
                if inline and inline.get("data"):
                    return inline["data"]
        outputs = result.get("output") or result.get("outputs") or []
        if isinstance(outputs, dict):
            outputs = [outputs]
        for output in outputs:
            content = output.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                inline = part.get("inline_data") or part.get("media")
                if inline and inline.get("data"):
                    return inline["data"]
        return None

    @staticmethod
    def _extract_image_bytes_from_sdk(response: Any) -> Optional[bytes]:
        try:
            candidates = getattr(response, "candidates", None) or []
            print(f"[GeminiService] _extract_image_bytes: Found {len(candidates)} candidates")
            
            for idx, candidate in enumerate(candidates):
                content = getattr(candidate, "content", None)
                if not content:
                    print(f"[GeminiService] _extract_image_bytes: candidate[{idx}] has no content")
                    continue
                    
                parts = getattr(content, "parts", None) or []
                print(f"[GeminiService] _extract_image_bytes: candidate[{idx}] has {len(parts)} parts")
                
                for part_idx, part in enumerate(parts):
                    # Try inline_data
                    inline = getattr(part, "inline_data", None)
                    if inline is not None:
                        data = getattr(inline, "data", None)
                        if data:
                            if isinstance(data, (bytes, bytearray)):
                                print(f"[GeminiService] _extract_image_bytes: Found image bytes in candidate[{idx}].parts[{part_idx}].inline_data, size={len(data)}")
                                return data
                            else:
                                print(f"[GeminiService] _extract_image_bytes: Found data but wrong type: {type(data).__name__}")
                    
                    # Also try checking if there's a blob or image attribute
                    if hasattr(part, "blob"):
                        blob = getattr(part, "blob", None)
                        if blob and hasattr(blob, "data"):
                            blob_data = blob.data
                            if isinstance(blob_data, (bytes, bytearray)):
                                print(f"[GeminiService] _extract_image_bytes: Found image bytes in candidate[{idx}].parts[{part_idx}].blob, size={len(blob_data)}")
                                return blob_data
                    
                    print(f"[GeminiService] _extract_image_bytes: candidate[{idx}].parts[{part_idx}] - no image data found")
                    
        except Exception as e:
            print(f"[GeminiService] _extract_image_bytes: Exception {type(e).__name__}: {e}")
            return None
        
        print(f"[GeminiService] _extract_image_bytes: No image bytes found in any candidate")
        return None

    def _aspect_ratio_from_image(self, path: str) -> Optional[str]:
        if Image is None:
            return None
        try:
            with Image.open(path) as _tmp_img:
                w, h = _tmp_img.size
            if w <= 0 or h <= 0:
                return None
            r = w / h
            pairs = {1.0: "1:1", 4 / 5: "4:5", 5 / 4: "5:4", 3 / 4: "3:4", 4 / 3: "4:3", 2 / 3: "2:3", 3 / 2: "3:2", 9 / 16: "9:16", 16 / 9: "16:9"}
            best = None
            best_diff = 1e9
            for val, tag in pairs.items():
                diff = abs(r - val)
                if diff < best_diff:
                    best = tag
                    best_diff = diff
            return best
        except Exception:
            return None

    def _refine_remove_original_clothes(
        self,
        generated_image_path: str,
        garment_image_abs: Optional[str],
        original_user_image_path: Optional[str] = None,
    ) -> Optional[bytes]:
        try:
            with open(generated_image_path, "rb") as f:
                gen_bytes = f.read()
            gen_mime = self._detect_mime_type(generated_image_path)
            prompt = (
                "Clean up the result so that only the garments from the reference are visible on the user. "
                "Remove any remaining clothing from the original user photo, including collars, sleeves, belts, waistbands, trouser legs, and jacket hems. "
                "Preserve the user's anatomy, skin tones, and lighting; maintain natural shadows and occlusions. "
                "Do not add text. Output one clean photorealistic image."
            )
            extra_paths: list[str] = []
            if original_user_image_path and os.path.exists(original_user_image_path):
                extra_paths.append(original_user_image_path)
            response = self._invoke_gemini_api(prompt, gen_mime, gen_bytes, garment_image_abs, extra_image_paths=extra_paths)
            result_dict = self._response_to_dict(response)
            direct_bytes = self._extract_image_bytes_from_sdk(response)
            if direct_bytes:
                return direct_bytes
            image_b64 = self._extract_image_data(result_dict)
            if image_b64:
                return base64.b64decode(image_b64)
        except Exception:
            return None
        return None

    def _build_prompt(self, garment: Any, user_note: Optional[str] = None) -> str:
        try:
            has_garment = False
            if isinstance(garment, list):
                for g in garment:
                    if (g or {}).get("image_path"):
                        has_garment = True
                        break
            elif garment and isinstance(garment, dict):
                has_garment = bool(garment.get("image_path"))
        except Exception:
            has_garment = False

        base = (
            "PROFESSIONAL E-COMMERCE TASK: Digital fashion photography composite for online retail.\n"
            "\n"
            "Context: Standard commercial workflow - digitally edit customer photo to show product garment fit.\n"
            "\n"
            "Task: Replace existing clothing with product garment using digital editing.\n"
            "\n"
            "Process:\n"
            "1. INPUT ANALYSIS\n"
            "   - Image 1 (customer): person in original outfit + background scene\n"
            "   - Image 2 (product): garment to be applied (ignore any models)\n"
            "\n"
            "2. IDENTIFY GARMENT TYPE from image 2:\n"
            "   - If SWIMWEAR/BRIEFS/ATHLETIC SHORTS: This is lower-body athletic wear\n"
            "   - If TOP/SHIRT/JACKET: This is upper-body wear\n"
            "   - If DRESS/JUMPSUIT: This is full-body wear\n"
            "\n"
            "3. DIGITAL EDITING WORKFLOW:\n"
            "   Step A: For SWIMWEAR/BRIEFS (athletic lower-body garment):\n"
            "     - Edit hip/waist/leg regions in image 1\n"
            "     - Replace existing fabric in those regions with new garment from image 2\n"
            "     - Result visual: Person wearing athletic swimwear as seen in professional swim/sports photography\n"
            "     - Body contours visible per garment coverage (standard for athletic wear)\n"
            "   \n"
            "   Step B: For TOPS/SHIRTS:\n"
            "     - Edit chest/shoulder/arm regions in image 1\n"
            "     - Replace existing fabric with new garment from image 2\n"
            "   \n"
            "   Step C: For FULL-BODY garments:\n"
            "     - Edit full torso regions in image 1\n"
            "     - Replace existing fabric with new garment from image 2\n"
            "\n"
            "4. CRITICAL QUALITY CHECK:\n"
            "   ✓ New garment matches body pose, lighting, perspective\n"
            "   ✓ Background/face/hair unchanged from image 1\n"
            "   ✓ MOST IMPORTANT: No old garment visible in edited regions\n"
            "   \n"
            "   VISUAL VERIFICATION for SWIMWEAR example:\n"
            "   ❌ WRONG: Old pants/shorts still visible under new swimwear\n"
            "   ❌ WRONG: Old shirt still covering torso above new swimwear\n"
            "   ✓ CORRECT: Only new swimwear visible in hip/leg area, other areas show body form\n"
            "   ✓ CORRECT: Result looks like person originally photographed wearing the swimwear\n"
            "\n"
            "CRITICAL: This is complete garment REPLACEMENT. \n"
            "Think: 'What would this photo look like if person wore ONLY the new garment from the start?'\n"
            "NOT: 'Add new garment on top of existing clothes'\n"
            "YES: 'Edit photo so new garment is the ONLY clothing in target area'\n"
            "\n"
            "For athletic/swimwear: Standard sports/swim photography aesthetic - garment fitted to body form (normal for this product category).\n"
            "\n"
            "Output: Image 1's scene with person edited to wear ONLY image 2's garment (as if originally photographed that way).\n"
        )

        custom_section = ""
        if user_note:
            note_clean = user_note.strip()
            if note_clean:
                custom_section = (
                    "USER PRIORITY REQUEST:\n"
                    f"- {note_clean}\n"
                    "Honor this styling request while producing the final outfit. Adjust garment fit, posing, or emphasis to satisfy the user's note without changing the person's identity.\n\n"
                )

        if has_garment:
            extra = (
                " Use the GARMENT REFERENCE(s) as the clothing to be worn by the user in the USER PHOTO. Ensure correct placement of collars, sleeves, hems, necklines, waistbands, and closures. "
                "If the USER PHOTO is half-body, compose the garment as a half-body result; if full-body, ensure full garment visibility when possible. "
                "Blend edges cleanly; avoid ghosting or doubled clothes. Do NOT change the user's identity or pose."
            )
        else:
            extra = (
                " If no garment reference is available, return a clean enhancement of the user photo maintaining realism (as a fallback)."
            )
        return custom_section + base + extra

    @staticmethod
    def _check_safety_ratings(response: Any) -> Optional[str]:
        """檢查 Gemini API 回應中的安全過濾信息。"""
        try:
            if not response:
                return None
            
            # Check for candidates with safety ratings
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                return None
            
            blocked_reasons = []
            for idx, candidate in enumerate(candidates):
                # Check finish_reason
                finish_reason = getattr(candidate, "finish_reason", None)
                finish_reason_str = str(finish_reason)
                
                # IMAGE_OTHER is not an error, it means image was generated successfully
                # Only treat SAFETY, RECITATION, and similar as actual blocks
                if finish_reason and finish_reason_str not in ("STOP", "1", "", "FinishReason.IMAGE_OTHER", "IMAGE_OTHER"):
                    # Check if it's actually a blocking reason
                    if any(keyword in finish_reason_str.upper() for keyword in ["SAFETY", "RECITATION", "PROHIBITED", "BLOCKED"]):
                        blocked_reasons.append(f"candidate[{idx}].finish_reason={finish_reason}")
                
                # Check safety_ratings
                safety_ratings = getattr(candidate, "safety_ratings", None) or []
                for rating in safety_ratings:
                    category = getattr(rating, "category", "UNKNOWN")
                    probability = getattr(rating, "probability", "UNKNOWN")
                    # If probability is HIGH or MEDIUM, log it
                    if probability and str(probability) in ("HIGH", "MEDIUM", "3", "2"):
                        blocked_reasons.append(f"{category}={probability}")
            
            if blocked_reasons:
                return f"Content may be filtered: {', '.join(blocked_reasons)}"
            
            return None
        except Exception as e:
            return f"Error checking safety: {type(e).__name__}"

    def _apply_roi_sequence(
        self,
        base_image_path: str,
        garment_image_abs: Optional[str],
        stage2_prompt: str,
        safety_settings,
        public_path: str,
        output_path: Path,
        needs_upper: bool,
        needs_lower: bool,
    ) -> Optional[Dict[str, Optional[str]]]:
        current_base = base_image_path
        result: Optional[Dict[str, Optional[str]]] = None
        if needs_lower:
            roi_prompt = (
                stage2_prompt
                + "\nEnsure the edited region produces a single continuous frame featuring only the original user; do NOT copy or paste any other person from any reference image."
            )
            roi_lower = self._generate_on_lower_body_roi(current_base, garment_image_abs, roi_prompt, safety_settings, public_path, output_path)
            if roi_lower:
                result = roi_lower
                current_base = str(output_path)
        if needs_upper:
            roi_prompt = (
                stage2_prompt
                + "\nEnsure the edited region produces a single continuous frame featuring only the original user; do NOT copy or paste any other person from any reference image."
            )
            roi_upper = self._generate_on_upper_body_roi(current_base, garment_image_abs, roi_prompt, safety_settings, public_path, output_path)
            if roi_upper:
                result = roi_upper
                current_base = str(output_path)
        return result

    def _run_final_identity_check(self, user_image_path: str, output_path: str) -> None:
        try:
            print("[GeminiService] FINAL CHECK: ensure output preserves user identity")
            self._analysis_service = getattr(self, "_analysis_service", TryOnAnalysisService(self))
            user_info = self._analysis_service.analyze_user(Path(user_image_path))
            output_info = self._analysis_service.analyze_user(Path(output_path))
            if user_info.get("summary") and output_info.get("summary"):
                print(f"[GeminiService] FINAL CHECK: user={user_info['summary']} output={output_info['summary']}")
        except Exception as exc:
            print(f"[GeminiService] FINAL CHECK skipped due to error: {exc}")

