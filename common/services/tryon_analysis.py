"""提供服飾與人物分析的 LLM 輔助工具。"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any, Dict, Optional


class TryOnAnalysisService:
    """封裝 Gemini LLM 描述流程，建立統一的換衣提示。"""

    def __init__(self, tryon_service: Any) -> None:
        self._svc = tryon_service

    # ------------------------------------------------------------------
    # Public helpers

    def analyze_garment(self, image_path: Path) -> Dict[str, Any]:
        default = {
            "has_model": "unknown",
            "exposure_level": "medium",
            "garment_description": "",
            "on_body_description": "",
            "category": "",
            "explicit_terms": "",
            "raw": "",
        }
        if not image_path or not image_path.exists():
            print(f"[TryOnAnalysis] garment image not found: {image_path}")
            return default

        prompt = (
            "你是一位髮型設計專家，請分析提供的髮型照片，輸出 JSON 物件且不要出現額外文字。"
            "必須包含下列鍵值："
            "has_model (boolean)、exposure_level (\"low\"/\"medium\"/\"high\")、garment_description (string)、"
            "on_body_description (string)、category (string)、explicit_terms (string)。"
            "\n判斷準則："
            "\n- has_model：若畫面中有真人或模特兒展示髮型，回傳 true。"
            "\n- exposure_level：根據髮型風格判斷，前衛或特殊造型屬於 high，"
            "流行時尚造型視為 medium，保守或傳統造型為 low。"
            "\n- garment_description：用中文精確描述髮型的長度、顏色、質感、捲度、層次等特徵。"
            "\n- on_body_description：描述這個髮型適合的臉型、場合，以及呈現的整體風格。"
            "\n- category：簡短標示類別，例如長髮、短髮、捲髮、直髮、染髮等。"
            "\n- explicit_terms：若偵測到特殊或需要注意的髮型特徵關鍵詞，請列出，否則給空字串。"
        )

        response = self._call_llm(prompt, image_path)
        default["raw"] = response
        parsed = self._parse_json_response(response)
        if not parsed:
            print("[TryOnAnalysis] Garment description JSON decode failed; fallback to defaults")
            return default

        info = {
            "has_model": bool(parsed.get("has_model")),
            "exposure_level": self._normalize_exposure(str(parsed.get("exposure_level", "medium"))),
            "garment_description": str(parsed.get("garment_description", "")),
            "on_body_description": str(parsed.get("on_body_description", "")),
            "category": str(parsed.get("category", "")),
            "explicit_terms": str(parsed.get("explicit_terms", "")),
            "raw": response,
        }
        if info["explicit_terms"]:
            info["exposure_level"] = "high"
        return info

    def analyze_user(self, image_path: Path) -> Dict[str, str]:
        default = {"summary": "", "details": "", "raw": ""}
        if not image_path or not image_path.exists():
            print(f"[TryOnAnalysis] user image not found: {image_path}")
            return default

        prompt = (
            "你是一位造型顧問，請以 JSON 格式描述照片中的人物。"
            "輸出必須只有 JSON，包含鍵：person_description (string)、pose (string)、lighting (string)、"
            "style_tips (string)。"
            "\n請描述人物的性別表現、臉型特徵、當前髮型、面部朝向、姿勢、燈光氛圍與可用於換髮型提示的重點。"
        )

        response = self._call_llm(prompt, image_path)
        default["raw"] = response
        parsed = self._parse_json_response(response)
        if not parsed:
            print("[TryOnAnalysis] User description JSON decode failed; fallback到預設")
            return default

        summary_parts = [str(parsed.get("person_description", "")).strip()]
        pose = str(parsed.get("pose", "")).strip()
        lighting = str(parsed.get("lighting", "")).strip()
        tips = str(parsed.get("style_tips", "")).strip()
        default["summary"] = "；".join([p for p in summary_parts if p])
        default["details"] = "；".join([p for p in (pose, lighting, tips) if p])
        return default

    def compose_note(
        self,
        garment_info: Dict[str, Any],
        user_info: Dict[str, str],
        user_note: Optional[str],
    ) -> str:
        exposure = garment_info.get("exposure_level", "medium")
        has_model = garment_info.get("has_model")
        garment_desc = garment_info.get("garment_description", "").strip()
        on_body = garment_info.get("on_body_description", "").strip()
        explicit_terms = garment_info.get("explicit_terms", "").strip()
        category = garment_info.get("category", "").strip()

        lines = [
            "Hairstyle analysis:",
            f"- Category: {category or '未分類'}",
            f"- Description: {garment_desc or '無詳細描述'}",
            f"- Styling notes: {on_body or '無說明'}",
            f"- Style level: {exposure}",
        ]

        if explicit_terms:
            lines.append(f"- Sensitive terms: {explicit_terms}")

        if has_model is True:
            lines.append(
                "CRITICAL: Extract ONLY the hairstyle characteristics from the reference image. DO NOT copy the reference person's face, body, pose, or clothing. Apply the hairstyle to the user's appearance."
            )

        lines.extend([
            "",
            "🚫 ABSOLUTE PROHIBITION - CLOTHING CHANGES ARE FORBIDDEN:",
            "- DO NOT change, modify, replace, or alter ANY clothing items from the user's photo",
            "- DO NOT copy clothing from the hairstyle reference image",
            "- Treat the user's clothing as READ-ONLY - it cannot be modified",
            "- If the user wears a shirt → keep the EXACT same shirt",
            "- If the user wears a dress → keep the EXACT same dress",
            "- If the user wears pants → keep the EXACT same pants",
            "- If the user wears a jacket → keep the EXACT same jacket",
            "- Changing clothing is a VIOLATION and is UNACCEPTABLE",
            "",
            "⚠️ MANDATORY REQUIREMENTS (FOLLOW EXACTLY):",
            "- Replace ONLY the user's hairstyle (the hair on the head)",
            "- NOTHING BELOW THE NECK should change",
            "- Keep the user's facial features, face shape, skin tone, and facial expression EXACTLY the same",
            "- Keep the user's neck, body pose, position, and proportions EXACTLY the same", 
            "- Keep the user's clothing EXACTLY the same - DO NOT change, replace, or modify ANY clothing items",
            "- Keep ALL accessories EXACTLY the same (jewelry, glasses, watches, bags, belts, shoes, etc.)",
            "- Keep the background, environment, scene, and all objects EXACTLY the same",
            "- Keep the lighting, shadows, and camera angle EXACTLY the same",
            "- The ONLY visible difference should be the hairstyle on the head - NOTHING ELSE may change",
            "",
            "⚠️ SPECIAL WARNING FOR FULL-BODY PHOTOS:",
            "- Even if the user's photo shows the full body with visible clothing, DO NOT change ANY clothing",
            "- The entire body from neck down must remain PIXEL-PERFECT IDENTICAL",
            "- All clothing items must be preserved exactly as they appear in the user's photo",
            "- If you see a shirt in the user's photo → the output MUST have the EXACT SAME shirt",
            "- If you see pants in the user's photo → the output MUST have the EXACT SAME pants",
            "- If you see a dress in the user's photo → the output MUST have the EXACT SAME dress",
            "- Clothing visibility does NOT give you permission to modify it"
        ])

        if exposure == "high":
            lines.extend(
                [
                    "Present the hairstyle as a professional hair salon portfolio demonstration—keep it tasteful, artistic, and suitable for commercial use.",
                    "Focus on showcasing the hairstyle design and technique; maintain professional salon photography standards.",
                    "Use professional studio lighting style consistent with high-end hair salon portfolios.",
                ]
            )
        else:
            lines.append(
                "Maintain fidelity to the hairstyle's design while keeping the result natural and professional for a hair salon catalog."
            )

        user_summary = user_info.get("summary", "").strip()
        user_details = user_info.get("details", "").strip()
        lines.append("User reference:")
        lines.append(f"- Appearance: {user_summary or '未提供'}")
        if user_details:
            lines.append(f"- Extra notes: {user_details}")

        if user_note:
            lines.append(f"User additional note: {user_note}")

        composed = "\n".join(lines)
        print(f"[TryOnAnalysis] Composed try-on note:\n{composed}")
        return composed

    # ------------------------------------------------------------------
    # Internal helpers

    def _call_llm(self, prompt: str, image_path: Path) -> str:
        # 支持两种调用方式：
        # 1. 从 TryOnService.gemini 获取（旧方式）
        # 2. 直接从 GeminiService 获取（新方式）
        gemini = getattr(self._svc, "gemini", None) or self._svc
        client = getattr(gemini, "client", None) if gemini else None
        if not client:
            print("[TryOnAnalysis] Gemini LLM 未啟用，跳過描述流程。")
            return ""

        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            print(f"[TryOnAnalysis] 讀取圖片失敗 {image_path}: {exc}")
            return ""

        parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_bytes).decode("utf-8"),
                }
            },
        ]

        print(f"[TryOnAnalysis] LLM prompt:\n{prompt}")

        try:
            llm_model = getattr(gemini, "llm_model_name", None) or getattr(gemini, "llm_name", "gemini-2.5-flash")
            print(f"[TryOnAnalysis] Calling LLM with model={llm_model}, client={type(client).__name__}")
            response = client.models.generate_content(
                model=llm_model,
                contents={"parts": parts},
            )
            print(f"[TryOnAnalysis] LLM response received, type={type(response).__name__}")
        except Exception as exc:
            print(f"[TryOnAnalysis] LLM 呼叫失敗: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
            return ""

        text = self._strip_markdown_fences(self._extract_text(response))
        print(f"[TryOnAnalysis] LLM response:\n{text}")
        return text

    @staticmethod
    def _extract_text(response: Any) -> str:
        if response is None:
            return ""
        if hasattr(response, "text") and response.text:
            return str(response.text)
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and getattr(candidate.content, "parts", None):
                texts = [getattr(part, "text", "") for part in candidate.content.parts]
                return "".join(t for t in texts if t)
        if hasattr(response, "result") and isinstance(response.result, str):
            return response.result
        return ""

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        if not text:
            return ""
        cleaned = text.strip()
        fence_match = re.match(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
        if fence_match:
            return fence_match.group(1).strip()
        return cleaned

    def _parse_json_response(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        stripped = self._strip_markdown_fences(text)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", stripped, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
        return None

    @staticmethod
    def _normalize_exposure(value: str) -> str:
        normalized = value.strip().lower()
        if normalized in {"low", "medium", "high"}:
            return normalized
        if re.search(r"(內衣|泳裝|比基尼|lingerie|underwear|swim)", value, re.IGNORECASE):
            return "high"
        return "medium"

