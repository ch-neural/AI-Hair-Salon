import os
import shutil
import time
import base64
from io import BytesIO
import threading
try:
    from PIL import Image  # type: ignore
except Exception:
    Image = None  # type: ignore

HEIF_SUPPORTED = False
HEIF_MIME_TYPES = {
    "image/heic",
    "image/heif",
    "image/heic-sequence",
    "image/heif-sequence",
}

try:
    from pillow_heif import register_heif_opener  # type: ignore

    register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:
    HEIF_SUPPORTED = False
from pathlib import Path
from typing import Any, Dict, Optional, Union

from common.services.tryon_analysis import TryOnAnalysisService
from urllib.parse import urlparse

try:
    # 使用整合後的新位置（優先）
    from common.services.gemini_service import GeminiService  # type: ignore
except Exception as _e1:  # pragma: no cover - 匯入失敗時改用次要位置
    try:
        # 後備：web_app 版本（避免環境路徑問題）
        from web_app.app.services.gemini_service import GeminiService  # type: ignore
        print("[TryOn] fallback: using web_app.app.services.gemini_service.GeminiService")
    except Exception as _e2:
        print(f"[TryOn] failed to import GeminiService: primary={type(_e1).__name__}, fallback={type(_e2).__name__}")
        GeminiService = None  # type: ignore

try:
    from common.services.klingai_service import KlingAIService  # type: ignore
except Exception as _e3:
    print(f"[TryOn] failed to import KlingAIService: {type(_e3).__name__}")
    KlingAIService = None  # type: ignore
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None  # type: ignore

try:
    from common.db.session import get_session
    from common.models.tryon_record import TryOnRecord
except Exception:
    get_session = None  # type: ignore
    TryOnRecord = None  # type: ignore


class TryOnService:
    """Minimal try-on service (mock): copies user image as output.
    Later can integrate real models (e.g., Gemini / custom pipeline).
    """

    def __init__(self, base_dir: Optional[str] = None, 
                 app_path_map: Optional[dict] = None,
                 settings_json_path: Optional[str] = None) -> None:
        
        self.base_dir = Path(base_dir or Path.cwd())
        
        # Determine paths based on the app context (web or live-demo)
        path_map = app_path_map or {}
        self._inputs_dir = Path(path_map.get("inputs") or self.base_dir / "app" / "static" / "inputs")
        self._outputs_dir = Path(path_map.get("outputs") or self.base_dir / "app" / "static" / "outputs")
        self._garments_dir = Path(path_map.get("garments") or self.base_dir / "app" / "static" / "garments")
        
        self._inputs_dir.mkdir(parents=True, exist_ok=True)
        self._outputs_dir.mkdir(parents=True, exist_ok=True)
        self._garments_dir.mkdir(parents=True, exist_ok=True)

        # Legacy paths for backward compatibility if needed, though direct path injection is better
        self.legacy_outputs_dir = self.base_dir / "app" / "static" / "outputs"
        self.legacy_inputs_dir = self.base_dir / "app" / "static" / "inputs"
        self.legacy_outputs_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_inputs_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if load_dotenv:
                load_dotenv(self.base_dir / ".env")
        except Exception:
            pass
        
        # Load vendor selection from settings
        self._settings_json_path = settings_json_path
        self._vendor = self._load_vendor_setting()
        
        # Initialize both services
        self.gemini = GeminiService(
            outputs_dir=str(self._outputs_dir),
            settings_json_path=settings_json_path
        ) if GeminiService else None
        
        self.klingai = KlingAIService(
            outputs_dir=str(self._outputs_dir),
            settings_json_path=settings_json_path
        ) if KlingAIService else None
        
        try:
            api_set = bool(getattr(self.gemini, "api_key", None)) if self.gemini else False
            client = getattr(self.gemini, "client", None) if self.gemini else None
            client_on = client is not None
            client_type = type(client).__name__ if client else "None"
            print(f"[TryOn] gemini available={bool(self.gemini)} api_key={'set' if api_set else 'missing'} client={'on' if client_on else 'off'} client_type={client_type}")
        except Exception as e:
            print(f"[TryOn] Error checking gemini status: {e}")
        
        try:
            klingai_access_set = bool(getattr(self.klingai, "access_key", None)) if self.klingai else False
            klingai_secret_set = bool(getattr(self.klingai, "secret_key", None)) if self.klingai else False
            print(f"[TryOn] klingai available={bool(self.klingai)} access_key={'set' if klingai_access_set else 'missing'} secret_key={'set' if klingai_secret_set else 'missing'}")
        except Exception as e:
            print(f"[TryOn] Error checking klingai status: {e}")
        
        print(f"[TryOn] Selected vendor: {self._vendor}")
        
        self._session_outputs: dict[str, str] = {}
        self._session_errors: dict[str, str] = {}
        import threading
        self._lock = threading.Lock()
        self._analysis = TryOnAnalysisService(self)

    @property
    def outputs_dir(self) -> Path:
        """Get the current outputs directory."""
        return self._outputs_dir
    
    @outputs_dir.setter
    def outputs_dir(self, value: Union[str, Path]) -> None:
        """Set the outputs directory and update dependent services."""
        self._outputs_dir = Path(value)
        self._outputs_dir.mkdir(parents=True, exist_ok=True)
        # Update gemini service if it exists
        if self.gemini and hasattr(self.gemini, 'outputs_dir'):
            self.gemini.outputs_dir = self._outputs_dir
        # Update klingai service if it exists
        if self.klingai and hasattr(self.klingai, 'outputs_dir'):
            self.klingai.outputs_dir = self._outputs_dir
    
    @property
    def inputs_dir(self) -> Path:
        """Get the current inputs directory."""
        return self._inputs_dir
    
    @inputs_dir.setter
    def inputs_dir(self, value: Union[str, Path]) -> None:
        """Set the inputs directory."""
        self._inputs_dir = Path(value)
        self._inputs_dir.mkdir(parents=True, exist_ok=True)

    def _load_vendor_setting(self) -> str:
        """Load VENDOR_TRYON setting from settings.json"""
        try:
            if self._settings_json_path and Path(self._settings_json_path).exists():
                import json
                settings = json.loads(Path(self._settings_json_path).read_text(encoding="utf-8"))
                vendor = settings.get("VENDOR_TRYON", "Gemini")
                return vendor
            else:
                # Fallback to default settings path
                default_path = self.base_dir / "data" / "settings.json"
                if default_path.exists():
                    import json
                    settings = json.loads(default_path.read_text(encoding="utf-8"))
                    vendor = settings.get("VENDOR_TRYON", "Gemini")
                    return vendor
        except Exception as e:
            print(f"[TryOn] Error loading vendor setting: {e}")
        return "Gemini"  # Default to Gemini

    def _to_web_url(self, abs_path: Union[str, Path, None]) -> Optional[str]:
        """Converts an absolute filesystem path to a relative web URL."""
        if not abs_path:
            return None
        
        abs_path_str = str(abs_path)
        
        # Find the 'static' directory component in the path
        try:
            # This finds the last occurrence of 'static' and splits the string there
            # e.g., /path/to/project/apps/web/static/outputs/img.jpg
            # -> ('/path/to/project/apps/web/', 'static/outputs/img.jpg')
            _head, _sep, tail = abs_path_str.rpartition(os.path.sep + 'static' + os.path.sep)
            if tail:
                # We want '/static/outputs/img.jpg'
                return f"/static/{tail.replace(os.path.sep, '/')}"
        except Exception:
            pass

        # Fallback for unexpected path formats, just return the filename
        # This is not ideal but prevents catastrophic failure.
        print(f"[TryOn] Warning: could not convert path to web URL: {abs_path_str}")
        return Path(abs_path_str).name

    def _public_to_abs(self, public_path: Optional[str]) -> Optional[str]:
        if not public_path or not isinstance(public_path, str):
            return None
        try:
            if public_path.startswith("/static/"):
                rel = public_path[len("/static/"):]
                candidate = self.base_dir / "apps" / "web" / "static" / rel
                if candidate.exists():
                    return str(candidate)
            return None
        except Exception:
            return None

    def start_tryon(
        self,
        *,
        user_image_data_url: str,
        garment_image_url: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict:
        """Start try-on and return session info.
        For now, we decode data URL or, if already data URL, just store it as-is.
        """
        session_id = f"tryon_{int(time.time()*1000)}"
        out_path = self._outputs_dir / f"{session_id}.jpg"

        # Reload vendor setting (hot-reload support)
        self._vendor = self._load_vendor_setting()
        
        print(f"[TryOn] start session={session_id} garment_url={garment_image_url} vendor={self._vendor}")

        # Route to appropriate vendor
        if self._vendor == "KlingAI":
            return self._start_tryon_klingai(
                session_id=session_id,
                user_image_data_url=user_image_data_url,
                garment_image_url=garment_image_url,
                user_note=user_note,
            )
        else:
            # Default to Gemini
            return self._start_tryon_gemini(
                session_id=session_id,
                user_image_data_url=user_image_data_url,
                garment_image_url=garment_image_url,
                user_note=user_note,
            )

    def _start_tryon_klingai(
        self,
        *,
        session_id: str,
        user_image_data_url: str,
        garment_image_url: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict:
        """Start try-on using KlingAI service"""
        if not self.klingai:
            print(f"[TryOn] KlingAI service not available")
            return {"status": "error", "message": "KlingAI service not initialized"}
        
        # 熱重載 KlingAI 設定（確保取得最新的 API 金鑰）
        try:
            self.klingai._reload_settings_if_changed()
        except Exception as e:
            print(f"[TryOn] KlingAI reload settings failed: {e}")
        
        klingai_access_set = bool(getattr(self.klingai, "access_key", None))
        klingai_secret_set = bool(getattr(self.klingai, "secret_key", None))
        
        print(f"[TryOn] KlingAI keys check: access={klingai_access_set}, secret={klingai_secret_set}")
        
        if not (klingai_access_set and klingai_secret_set):
            print(f"[TryOn] KlingAI API keys not configured")
            return {"status": "error", "message": "KlingAI API 金鑰未設定，請至管理控制台→系統設定中填入 KLINGAI_ACCESS_KEY 和 KLINGAI_SECRET_KEY"}
        
        try:
            # 1) 將使用者 data-url 轉為檔案
            user_path = self._write_data_url_to_file(
                user_image_data_url, self.legacy_inputs_dir / f"user_{session_id}.jpg"
            )
        except ValueError as exc:
            print(f"[TryOn] invalid user image: {exc}")
            return {"status": "error", "message": str(exc)}
        
        try:
            # 記錄試衣開始
            self._save_tryon_record(session_id, user_path=str(user_path), status="processing")

            # 2) 解析 garment 路徑
            garment_for_klingai = None
            garment_abs_path = None
            norm_url = garment_image_url
            try:
                if garment_image_url and not garment_image_url.startswith("data:image") and not garment_image_url.startswith("/static/"):
                    p = urlparse(garment_image_url)
                    if p.path and p.path.startswith("/static/"):
                        norm_url = p.path
            except Exception:
                pass

            if norm_url and isinstance(norm_url, str) and norm_url.startswith("/static/"):
                rel = garment_image_url[len("/static/"):]
                src = self.base_dir / "apps" / "web" / "static" / rel
                dst = self.base_dir / "app" / "static" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    try:
                        shutil.copyfile(src, dst)
                        garment_for_klingai = {"image_path": rel}
                        garment_abs_path = str(dst)
                        print(f"[TryOn] garment copied src={src} -> dst={dst}")
                    except Exception as ce:
                        print(f"[TryOn] garment copy failed: {ce}")
            elif norm_url and isinstance(norm_url, str) and norm_url.startswith("data:image"):
                g_path = self._write_data_url_to_file(norm_url, self.legacy_inputs_dir / f"garment_{session_id}.jpg")
                rel = f"static/inputs/{g_path.name}"
                garment_for_klingai = {"image_path": rel}
                garment_abs_path = str(g_path)
                print(f"[TryOn] garment data-url saved {g_path}")
            
            if garment_abs_path:
                self._save_tryon_record(session_id, garment_path=garment_abs_path, status="processing")
            
            # 3) 背景執行 KlingAI
            def _bg_job_klingai() -> None:
                result_abs_path = None
                try:
                    print(f"[TryOn] bg_job KlingAI start for session={session_id}")
                    res = self.klingai.generate_virtual_tryon(
                        user_image_path=str(user_path),
                        garment=garment_for_klingai,
                        session_id=session_id,
                        user_note=user_note,
                    )
                    print(f"[TryOn] KlingAI result status={res.get('status')} mode={res.get('mode')} out={res.get('output_path')}")
                    out_public = res.get("output_path")
                    if res.get("status") == "ok" and out_public:
                        if out_public.startswith("/static/outputs/"):
                            fname = out_public.split("/")[-1]
                            result_abs_path = str(self.base_dir / "apps" / "web" / "static" / "outputs" / fname)
                        with self._lock:
                            self._session_outputs[session_id] = out_public
                        self._save_tryon_record(session_id, result_path=result_abs_path, status="ok")
                        print(f"[TryOn] bg_job KlingAI SUCCESS for session={session_id} output={out_public}")
                    else:
                        msg = res.get("message") if isinstance(res, dict) else "try-on failed"
                        with self._lock:
                            self._session_errors[session_id] = msg or "try-on failed"
                        self._save_tryon_record(session_id, status="error", error_msg=msg)
                        print(f"[TryOn] bg_job KlingAI FAILED for session={session_id} msg={msg}")
                except Exception as e:
                    print(f"[TryOn] background KlingAI generation error: {e}")
                    import traceback
                    traceback.print_exc()
                    err_msg = f"error: {type(e).__name__}"
                    with self._lock:
                        self._session_errors[session_id] = err_msg
                    self._save_tryon_record(session_id, status="error", error_msg=err_msg)

            threading.Thread(target=_bg_job_klingai, daemon=True).start()
            print(f"[TryOn] bg_job KlingAI thread started for session={session_id}")
            return {"session_id": session_id, "status": "processing", "preview": user_image_data_url}
        except ValueError as exc:
            print(f"[TryOn] garment image invalid: {exc}")
            return {"status": "error", "message": str(exc)}
        except Exception as ge:
            print(f"[TryOn] KlingAI pipeline error: {ge}")
            return {"status": "error", "message": str(ge)}

    def _start_tryon_gemini(
        self,
        *,
        session_id: str,
        user_image_data_url: str,
        garment_image_url: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict:
        """Start try-on using Gemini service"""
        client_on = bool(getattr(self.gemini, "client", None)) if self.gemini else False
        print(f"[TryOn] start Gemini session={session_id} garment_url={garment_image_url} gemini={'on' if client_on else 'off'}")

        # 若可用，走 Gemini 真實流程（改為背景執行，避免請求阻塞/超時）
        if self.gemini and user_image_data_url and user_image_data_url.startswith("data:image"):
            try:
                # 1) 將使用者 data-url 轉為檔案供 Gemini 使用
                user_path = self._write_data_url_to_file(
                    user_image_data_url, self.legacy_inputs_dir / f"user_{session_id}.jpg"
                )
            except ValueError as exc:
                print(f"[TryOn] invalid user image: {exc}")
                return {"status": "error", "message": str(exc)}
            try:
                # 記錄試衣開始
                self._save_tryon_record(session_id, user_path=str(user_path), status="processing")

                # 2) 解析 garment：若為 /static/ 開頭，複製到 app/static 對應位置並傳入相對路徑
                garment_for_gemini = None
                garment_abs_path = None
                # 正規化 garment 路徑（支援完整 URL）：抽出 /static/ 相對路徑
                norm_url = garment_image_url
                try:
                    if garment_image_url and not garment_image_url.startswith("data:image") and not garment_image_url.startswith("/static/"):
                        p = urlparse(garment_image_url)
                        if p.path and p.path.startswith("/static/"):
                            norm_url = p.path
                except Exception:
                    pass

                if norm_url and isinstance(norm_url, str) and norm_url.startswith("/static/"):
                    rel = garment_image_url[len("/static/"):]
                    src = self.base_dir / "apps" / "web" / "static" / rel
                    dst = self.base_dir / "app" / "static" / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if src.exists():
                        try:
                            shutil.copyfile(src, dst)
                            garment_for_gemini = {"image_path": rel}
                            garment_abs_path = str(dst)
                            print(f"[TryOn] garment copied src={src} -> dst={dst}")
                        except Exception as ce:
                            print(f"[TryOn] garment copy failed: {ce}")
                elif norm_url and isinstance(norm_url, str) and norm_url.startswith("data:image"):
                    # 將 data-url 服飾圖寫入 app/static/inputs 並傳相對路徑
                    g_path = self._write_data_url_to_file(norm_url, self.legacy_inputs_dir / f"garment_{session_id}.jpg")
                    rel = f"static/inputs/{g_path.name}"
                    garment_for_gemini = {"image_path": rel}
                    garment_abs_path = str(g_path)
                    print(f"[TryOn] garment data-url saved {g_path}")
                
                # 更新記錄：添加服飾圖片路徑
                if garment_abs_path:
                    self._save_tryon_record(session_id, garment_path=garment_abs_path, status="processing")
                # 3) 背景執行，完成後寫入輸出供輪詢取得
                def _bg_job() -> None:
                    result_abs_path = None
                    try:
                        print(f"[TryOn] bg_job start for session={session_id}")
                        res = self.gemini.generate_virtual_tryon(
                            user_image_path=str(user_path),
                            garment=garment_for_gemini,
                            session_id=session_id,
                            user_note=user_note,
                        )
                        print(f"[TryOn] gemini result status={res.get('status')} mode={res.get('mode')} out={res.get('output_path')}")
                        out_public = res.get("output_path")
                        if res.get("status") == "ok" and out_public:
                            # 將 public URL (/static/outputs/xxx.jpg) 轉為絕對路徑
                            # Gemini 保存到 apps/web/static/outputs/
                            if out_public.startswith("/static/outputs/"):
                                fname = out_public.split("/")[-1]
                                result_abs_path = str(self.base_dir / "apps" / "web" / "static" / "outputs" / fname)
                            with self._lock:
                                self._session_outputs[session_id] = out_public
                            # 更新記錄：成功
                            self._save_tryon_record(session_id, result_path=result_abs_path, status="ok")
                            print(f"[TryOn] bg_job SUCCESS for session={session_id} output={out_public}")
                        else:
                            # 標記錯誤，讓輪詢可結束
                            msg = res.get("message") if isinstance(res, dict) else "try-on failed"
                            with self._lock:
                                self._session_errors[session_id] = msg or "try-on failed"
                            # 更新記錄：失敗
                            self._save_tryon_record(session_id, status="error", error_msg=msg)
                            print(f"[TryOn] bg_job FAILED for session={session_id} msg={msg}")
                    except Exception as e:
                        print(f"[TryOn] background generation error: {e}")
                        import traceback
                        traceback.print_exc()
                        err_msg = f"error: {type(e).__name__}"
                        with self._lock:
                            self._session_errors[session_id] = err_msg
                        # 更新記錄：異常
                        self._save_tryon_record(session_id, status="error", error_msg=err_msg)

                threading.Thread(target=_bg_job, daemon=True).start()
                print(f"[TryOn] bg_job thread started for session={session_id}")
                # 立即回覆：提供上傳預覽但不標記為最終輸出，前端改以輪詢確認最終合成
                return {"session_id": session_id, "status": "processing", "preview": user_image_data_url}
            except ValueError as exc:
                print(f"[TryOn] garment image invalid: {exc}")
                return {"status": "error", "message": str(exc)}
            except Exception as ge:
                print(f"[TryOn] gemini pipeline error: {ge}")

        # Fallback：只回傳預覽（不標記為最終輸出，避免誤判完成）
        try:
            if user_image_data_url and user_image_data_url.startswith("data:image"):
                return {"session_id": session_id, "status": "processing", "preview": user_image_data_url}
        except Exception:
            pass
        return {"session_id": session_id, "status": "processing", "preview": None}

    def get_result(self, session_id: str) -> Dict:
        # mock: immediately done, return preview url
        if not session_id:
            print("[TryOn] get_result missing session_id")
            return {"status": "error", "message": "session_id missing"}
        
        # 使用鎖保護字典讀取，避免競爭條件
        with self._lock:
            # 優先檢查錯誤（確保錯誤不被覆蓋）
            err_msg = self._session_errors.get(session_id)
            if err_msg:
                print(f"[TryOn] result ERROR session={session_id} msg={err_msg}")
                return {"status": "error", "message": err_msg, "output": None}
            
            # 檢查成功輸出
            if session_id in self._session_outputs:
                out = self._session_outputs.get(session_id)
                print(f"[TryOn] result OK (memo) session={session_id} out={out}")
                return {"status": "ok", "output": out}
        
        # 檢查檔案系統（不需要鎖）
        fname = f"{session_id}.jpg"
        candidate = self._outputs_dir / fname
        if candidate.exists():
            pub = f"/static/outputs/{fname}"
            with self._lock:
                self._session_outputs[session_id] = pub
            print(f"[TryOn] result OK (file) session={session_id} path={pub}")
            return {"status": "ok", "output": pub}
        
        # 仍在處理中
        print(f"[TryOn] result PENDING session={session_id}")
        return {"status": "pending"}

    def start_tryon_advanced(
        self,
        *,
        user_image_data_url: str,
        garment_image_url: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict:
        """進階試衣：根據服飾類型自動選擇適合的 prompt 與流程。"""
        session_id = f"tryon_{int(time.time()*1000)}"

        # Reload vendor setting (hot-reload support)
        self._vendor = self._load_vendor_setting()
        
        # KlingAI doesn't have advanced mode, use standard mode
        if self._vendor == "KlingAI":
            print(f"[TryOn] KlingAI doesn't support advanced mode, using standard try-on")
            return self._start_tryon_klingai(
                session_id=session_id,
                user_image_data_url=user_image_data_url,
                garment_image_url=garment_image_url,
                user_note=user_note,
            )

        client_on = bool(getattr(self.gemini, "client", None)) if self.gemini else False
        print(f"[TryOn] start ADVANCED session={session_id} garment_url={garment_image_url} gemini={'on' if client_on else 'off'}")

        if not self.gemini or not getattr(self.gemini, "client", None):
            print(f"[TryOn] ADVANCED FAILED session={session_id} reason=gemini_unavailable gemini={bool(self.gemini)} client={getattr(self.gemini, 'client', None) if self.gemini else None}")
            with self._lock:
                self._session_errors[session_id] = "Gemini client unavailable"
            return {"session_id": session_id, "status": "error", "message": "Gemini client unavailable"}

        if not (user_image_data_url and user_image_data_url.startswith("data:image")):
            return {"session_id": session_id, "status": "processing", "preview": None}

        try:
            user_path = self._write_data_url_to_file(
                user_image_data_url, self.legacy_inputs_dir / f"user_{session_id}.jpg"
            )
        except ValueError as exc:
            print(f"[TryOn] invalid user image (advanced): {exc}")
            return {"status": "error", "message": str(exc)}

        try:
            self._save_tryon_record(session_id, user_path=str(user_path), status="processing")

            garment_for_gemini = None
            garment_abs_path = None
            norm_url = garment_image_url
            print(f"[TryOn] DEBUG: garment_image_url={garment_image_url}")
            try:
                if garment_image_url and not garment_image_url.startswith("data:image") and not garment_image_url.startswith("/static/"):
                    parsed = urlparse(garment_image_url)
                    if parsed.path and parsed.path.startswith("/static/"):
                        norm_url = parsed.path
            except Exception:
                pass

            print(f"[TryOn] DEBUG: norm_url={norm_url}")
            
            if norm_url and isinstance(norm_url, str) and norm_url.startswith("/static/"):
                rel = norm_url[len("/static/"):]
                print(f"[TryOn] DEBUG: rel={rel}")
                
                # 尝试多个可能的源路径
                possible_sources = [
                    self.base_dir / "apps" / "web" / "static" / rel,  # 原路径
                    Path.cwd() / "static" / rel,  # live-demo 路径
                    self.base_dir / "static" / rel,  # base_dir 下的 static
                ]
                
                src = None
                for candidate in possible_sources:
                    print(f"[TryOn] DEBUG: Trying source path: {candidate}, exists={candidate.exists()}")
                    if candidate.exists():
                        src = candidate
                        break
                
                if src:
                    dst = self.base_dir / "app" / "static" / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copyfile(src, dst)
                        garment_for_gemini = {"image_path": rel}
                        garment_abs_path = str(dst)
                        print(f"[TryOn] garment copied src={src} -> dst={dst}")
                    except Exception as ce:
                        print(f"[TryOn] garment copy failed: {ce}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"[TryOn] ERROR: garment image not found in any source path! rel={rel}")
            elif norm_url and isinstance(norm_url, str) and norm_url.startswith("data:image"):
                try:
                    g_path = self._write_data_url_to_file(norm_url, self.legacy_inputs_dir / f"garment_{session_id}.jpg")
                    rel = f"static/inputs/{g_path.name}"
                    garment_for_gemini = {"image_path": rel}
                    garment_abs_path = str(g_path)
                    print(f"[TryOn] garment data-url saved {g_path}")
                except Exception as ce:
                    print(f"[TryOn] garment data-url save failed: {ce}")

            if garment_abs_path:
                self._save_tryon_record(session_id, garment_path=garment_abs_path, status="processing")

            garment_info: Dict[str, Any] = {}
            analysis_source = Path(garment_abs_path) if garment_abs_path else None
            if analysis_source and analysis_source.exists():
                try:
                    garment_info = self._analysis.analyze_garment(analysis_source)
                    category = (garment_info or {}).get("category", "").lower() if garment_info else ""
                    print(f"[TryOn] Hairstyle classification: category='{category}'")
                except Exception as exc:
                    print(f"[TryOn] hairstyle analysis failed: {exc}")

            def _bg_job_advanced() -> None:
                result_abs_path = None
                try:
                    print(f"[TryOn] bg_job ADVANCED start for session={session_id}")

                    # 對於換髮型系統，使用 SIMPLE 模式讓 AI 直接看圖片來提取髮型
                    # 視覺提取比文字描述更精確
                    res = self.gemini.generate_virtual_tryon_simple(
                        user_image_path=str(user_path),
                        garment=garment_for_gemini,
                        garment_info=garment_info,
                        session_id=session_id,
                        user_note=user_note,
                    )

                    print(f"[TryOn] gemini ADVANCED result status={res.get('status')} mode={res.get('mode')} out={res.get('output_path')}")
                    out_public = res.get("output_path")
                    if res.get("status") == "ok" and out_public:
                        if out_public.startswith("/static/outputs/"):
                            fname = out_public.split("/")[-1]
                            result_abs_path = str(self.base_dir / "apps" / "web" / "static" / "outputs" / fname)
                        with self._lock:
                            self._session_outputs[session_id] = out_public
                        self._save_tryon_record(session_id, result_path=result_abs_path, status="ok")
                        print(f"[TryOn] bg_job ADVANCED SUCCESS session={session_id} output={out_public}")
                    else:
                        msg = res.get("message") if isinstance(res, dict) else "try-on failed"
                        with self._lock:
                            self._session_errors[session_id] = msg or "try-on failed"
                        self._save_tryon_record(session_id, status="error", error_msg=msg)
                        print(f"[TryOn] bg_job ADVANCED FAILED session={session_id} msg={msg}")
                except Exception as e:
                    print(f"[TryOn] background ADVANCED generation error: {e}")
                    import traceback
                    traceback.print_exc()
                    err_msg = f"error: {type(e).__name__}"
                    with self._lock:
                        self._session_errors[session_id] = err_msg
                    self._save_tryon_record(session_id, status="error", error_msg=err_msg)

            threading.Thread(target=_bg_job_advanced, daemon=True).start()
            print(f"[TryOn] bg_job ADVANCED thread started for session={session_id}")
            return {"session_id": session_id, "status": "processing", "preview": user_image_data_url}
        except ValueError as exc:
            print(f"[TryOn] garment image invalid (advanced): {exc}")
            return {"status": "error", "message": str(exc)}
        except Exception as ge:
            print(f"[TryOn] gemini ADVANCED pipeline error: {ge}")

        return {"session_id": session_id, "status": "processing", "preview": None}

    def start_tryon_intimate_two_phase(
        self,
        *,
        user_image_data_url: str,
        garment_image_url: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict:
        session_id = f"tryon_{int(time.time()*1000)}"
        
        # Reload vendor setting (hot-reload support)
        self._vendor = self._load_vendor_setting()
        
        # KlingAI doesn't have two-phase mode, use standard mode
        if self._vendor == "KlingAI":
            print(f"[TryOn] KlingAI doesn't support two-phase mode, using standard try-on")
            return self._start_tryon_klingai(
                session_id=session_id,
                user_image_data_url=user_image_data_url,
                garment_image_url=garment_image_url,
                user_note=user_note,
            )
        
        client_on = bool(getattr(self.gemini, "client", None)) if self.gemini else False
        print(f"[TryOn] start INTIMATE 2-PHASE session={session_id} garment_url={garment_image_url} gemini={'on' if client_on else 'off'}")

        if not self.gemini or not getattr(self.gemini, "client", None):
            with self._lock:
                self._session_errors[session_id] = "Gemini API 未配置或不可用，請檢查 API 金鑰設定"
            return {"session_id": session_id, "status": "error", "message": "Gemini API 未配置或不可用"}

        if not user_image_data_url or not user_image_data_url.startswith("data:image"):
            return {"status": "error", "message": "請提供 data-url 圖片"}

        try:
            user_path = self._write_data_url_to_file(
                user_image_data_url, self.legacy_inputs_dir / f"user_{session_id}.jpg"
            )
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}

        garment_for_gemini = None
        garment_abs_path = None
        norm_url = garment_image_url
        try:
            if garment_image_url and not garment_image_url.startswith("data:image") and not garment_image_url.startswith("/static/"):
                p = urlparse(garment_image_url)
                if p.path and p.path.startswith("/static/"):
                    norm_url = p.path
        except Exception:
            pass

        if norm_url and isinstance(norm_url, str) and norm_url.startswith("/static/"):
            rel = norm_url[len("/static/"):]
            src = self.base_dir / "apps" / "web" / "static" / rel
            dst = self.base_dir / "app" / "static" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                try:
                    shutil.copyfile(src, dst)
                    garment_for_gemini = {"image_path": rel}
                    garment_abs_path = str(dst)
                    print(f"[TryOn] garment copied src={src} -> dst={dst}")
                except Exception as ce:
                    print(f"[TryOn] garment copy failed: {ce}")
        elif norm_url and isinstance(norm_url, str) and norm_url.startswith("data:image"):
            try:
                g_path = self._write_data_url_to_file(norm_url, self.legacy_inputs_dir / f"garment_{session_id}.jpg")
                rel = f"static/inputs/{g_path.name}"
                garment_for_gemini = {"image_path": rel}
                garment_abs_path = str(g_path)
                print(f"[TryOn] garment data-url saved {g_path}")
            except Exception as ce:
                print(f"[TryOn] garment data-url save failed: {ce}")

        self._save_tryon_record(session_id, user_path=str(user_path), status="processing")
        if garment_abs_path:
            self._save_tryon_record(session_id, garment_path=garment_abs_path, status="processing")
        else:
            msg = "無法取得服飾參考圖，請確認商品圖片"
            with self._lock:
                self._session_errors[session_id] = msg
            return {"status": "error", "message": msg}

        upper_note = "Ensure upper-body clothing matches the reference garment exactly; if the reference torso is bare, keep the torso bare (within SFW rules)."
        lower_note = "Ensure lower-body garment matches the reference silhouette exactly, with no added coverage or leftover original clothing."
        if user_note:
            upper_note = upper_note + " " + user_note
            lower_note = lower_note + " " + user_note

        def _bg_job_two_phase() -> None:
            result_abs_path = None
            try:
                print(f"[TryOn] two-phase TOP start session={session_id}")
                res_upper = self.gemini.generate_virtual_tryon_simple(
                    user_image_path=str(user_path),
                    garment=garment_for_gemini,
                    garment_info=garment_info,
                    session_id=f"{session_id}_upper",
                    user_note=upper_note,
                )
                if res_upper.get("status") != "ok" or not res_upper.get("output_path"):
                    msg = res_upper.get("message") or "upper stage failed"
                    with self._lock:
                        self._session_errors[session_id] = msg
                    self._save_tryon_record(session_id, status="error", error_msg=msg)
                    print(f"[TryOn] two-phase TOP failed session={session_id} msg={msg}")
                    return

                upper_public = res_upper.get("output_path")
                upper_abs = self._public_to_abs(upper_public)
                if upper_abs:
                    self._save_tryon_record(session_id, result_path=upper_abs, status="processing")
                else:
                    upper_abs = str(user_path)

                print(f"[TryOn] two-phase BOTTOM start session={session_id}")
                res_lower = self.gemini.generate_virtual_tryon_simple(
                    user_image_path=upper_abs,
                    garment=garment_for_gemini,
                    garment_info=garment_info,
                    session_id=f"{session_id}_lower",
                    user_note=lower_note,
                )
                if res_lower.get("status") == "ok" and res_lower.get("output_path"):
                    out_public = res_lower.get("output_path")
                    if out_public and out_public.startswith("/static/outputs/"):
                        fname = out_public.split("/")[-1]
                        result_abs_path = str(self.base_dir / "apps" / "web" / "static" / "outputs" / fname)
                    with self._lock:
                        self._session_outputs[session_id] = out_public
                    self._save_tryon_record(session_id, result_path=result_abs_path, status="ok")
                    print(f"[TryOn] two-phase SUCCESS session={session_id} output={out_public}")
                else:
                    msg = res_lower.get("message") or "lower stage failed"
                    with self._lock:
                        self._session_errors[session_id] = msg
                    self._save_tryon_record(session_id, status="error", error_msg=msg)
                    print(f"[TryOn] two-phase BOTTOM failed session={session_id} msg={msg}")
            except Exception as e:
                print(f"[TryOn] two-phase pipeline error: {e}")
                import traceback
                traceback.print_exc()
                err_msg = f"two_phase error: {type(e).__name__}"
                with self._lock:
                    self._session_errors[session_id] = err_msg
                self._save_tryon_record(session_id, status="error", error_msg=err_msg)

        threading.Thread(target=_bg_job_two_phase, daemon=True).start()
        return {"session_id": session_id, "status": "processing", "preview": user_image_data_url}

    # Helpers -----------------------------------------------------------------
    @staticmethod
    def _write_data_url_to_file(data_url: str, dst_path: Path) -> Path:
        """將 data:image/...;base64,xxxxx 轉為實體檔案。"""
        if not data_url or "," not in data_url:
            raise ValueError("無法解析上傳的圖片資料，請重新選擇。")

        header, b64 = data_url.split(",", 1)
        try:
            raw = base64.b64decode(b64)
        except Exception as exc:
            raise ValueError("圖片資料解碼失敗，請改用 JPG 或 PNG 檔案。") from exc

        mime = "image/jpeg"
        if ";" in header and ":" in header:
            try:
                mime = header.split(":", 1)[1].split(";", 1)[0].strip().lower()
            except Exception:
                mime = "image/jpeg"

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if Image is None:
            if mime in ("image/jpeg", "image/jpg"):
                with open(dst_path, "wb") as f:
                    f.write(raw)
                return dst_path
            raise ValueError("伺服器暫時無法處理此圖片格式，請改用 JPG 或 PNG。")

        try:
            with Image.open(BytesIO(raw)) as im:
                im = im.convert("RGB")
                im.save(dst_path, format="JPEG", quality=90)
            return dst_path
        except Exception as exc:
            mime_lower = mime.lower()
            if mime_lower in ("image/jpeg", "image/jpg"):
                with open(dst_path, "wb") as f:
                    f.write(raw)
                return dst_path
            if mime_lower in HEIF_MIME_TYPES:
                if not HEIF_SUPPORTED:
                    raise ValueError(
                        "偵測到 iPhone HEIC/HEIF 照片，目前伺服器尚未啟用 HEIC 轉換，請改用 JPG/PNG，或在 iPhone 的「設定→相機→格式」中選擇「最相容」。"
                    ) from exc
            raise ValueError(f"上傳的圖片格式（{mime}）目前不支援，請改用 JPG 或 PNG。") from exc

    def _simple_overlay(self, user_image_path: str, garment_abs_path: Optional[str], out_name: str) -> Optional[str]:
        """極簡覆疊：將服飾圖 letterbox 到與使用者照相同尺寸，並以 40% 透明覆蓋。
        僅作為示範用，實際換衣需模型支援。
        """
        if Image is None:
            return None
        try:
            if not garment_abs_path or not Path(garment_abs_path).exists():
                return None
            with Image.open(user_image_path).convert("RGBA") as uimg:
                uw, uh = uimg.size
                with Image.open(garment_abs_path).convert("RGBA") as gimg:
                    gw, gh = gimg.size
                    if gw <= 0 or gh <= 0 or uw <= 0 or uh <= 0:
                        return None
                    scale = min(uw / gw, uh / gh)
                    new_w = max(1, int(round(gw * scale)))
                    new_h = max(1, int(round(gh * scale)))
                    g_resized = gimg.resize((new_w, new_h), Image.LANCZOS)
                    canvas = Image.new("RGBA", (uw, uh), (0, 0, 0, 0))
                    off_x = (uw - new_w) // 2
                    off_y = (uh - new_h) // 2
                    canvas.alpha_composite(uimg, (0, 0))
                    # 40% 透明覆蓋
                    alpha = int(255 * 0.4)
                    g_resized.putalpha(alpha)
                    canvas.alpha_composite(g_resized, (off_x, off_y))
                    out_path = self._outputs_dir / out_name
                    canvas.convert("RGB").save(out_path, format="JPEG", quality=90)
                    return str(out_path)
        except Exception:
            return None

    def _save_tryon_record(self, session_id: str, user_path: str = None, garment_path: str = None,
                          result_path: str = None, status: str = "pending", error_msg: str = None):
        """保存或更新試衣記錄到數據庫（使用相對路徑）。"""
        if not get_session:
            return
        
        try:
            # Convert all paths to web-friendly, relative URLs before DB insertion
            user_url = self._to_web_url(user_path)
            garment_url = self._to_web_url(garment_path)
            result_url = self._to_web_url(result_path)

            with get_session() as db:
                record = db.query(TryOnRecord).filter(TryOnRecord.session_id == session_id).first()
                if record:
                    # Update existing record
                    if user_url:
                        record.user_image_path = user_url
                    if garment_url:
                        record.garment_image_path = garment_url
                    if result_url:
                        record.result_image_path = result_url
                    record.status = status
                    if error_msg:
                        record.error_message = error_msg
                else:
                    # Create new record
                    record = TryOnRecord(
                        session_id=session_id,
                        user_image_path=user_url,
                        garment_image_path=garment_url,
                        result_image_path=result_url,
                        status=status,
                        error_message=error_msg,
                    )
                    db.add(record)
                db.commit()
        except Exception as e:
            print(f"[TryOn] failed to save record: {e}")


