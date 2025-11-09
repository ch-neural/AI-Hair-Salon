"""
KlingAI Virtual Try-On Service
Based on https://app.klingai.com/global/dev/document-api/apiReference/model/functionalityTry
Authentication uses JWT (JSON Web Token, RFC 7519)
"""
import base64
import json
import logging
import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

try:
    import jwt  # PyJWT library for token generation
except Exception:
    jwt = None  # type: ignore


class KlingAIService:
    """
    KlingAI API 整合服務：
    - 透過 KlingAI API 呼叫換裝功能
    - 若缺少 API key 或遇到例外，提供錯誤回饋
    - 靜態資源與輸出位於 apps/web/static/
    """

    API_BASE_URL = "https://api.klingai.com"
    SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

    def __init__(self, outputs_dir: Optional[str] = None, settings_json_path: Optional[str] = None) -> None:
        self.base_dir = Path.cwd()
        
        # Determine static directory path (needed for resolving garment paths)
        # Check both apps/web/static and app/static
        apps_web_static = self.base_dir / "apps" / "web" / "static"
        app_static = self.base_dir / "app" / "static"
        
        if apps_web_static.exists():
            self.static_dir = apps_web_static
        elif app_static.exists():
            self.static_dir = app_static
        else:
            # Default to apps/web/static
            self.static_dir = apps_web_static
        
        # Always use the passed outputs_dir parameter when available
        # Default to apps/web/static/outputs for consistency with other services
        if outputs_dir:
            self.outputs_dir = Path(outputs_dir)
        else:
            self.outputs_dir = self.static_dir / "outputs"
        
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        print(f"[KlingAIService] Static directory: {self.static_dir}")
        print(f"[KlingAIService] Output directory: {self.outputs_dir}")
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        self.access_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.model: str = "kolors-virtual-try-on-v1"  # Default model
        
        # Settings tracking for hot-reload
        self._settings_path: Optional[str] = settings_json_path
        self._settings_mtime: Optional[float] = None

        self._load_settings(settings_json_path)

    def _load_settings(self, settings_json_path: Optional[str] = None):
        """
        Loads settings from a JSON file and falls back to environment variables.
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
                settings = json.loads(path_to_load.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[KlingAIService] Error loading settings from {path_to_load}: {e}")
                settings = {}

        # Load values, falling back from settings to environment variables
        self.access_key = settings.get("KLINGAI_ACCESS_KEY") or os.getenv("KLINGAI_ACCESS_KEY")
        self.secret_key = settings.get("KLINGAI_SECRET_KEY") or os.getenv("KLINGAI_SECRET_KEY")
        self.model = settings.get("KLINGAI_MODEL") or os.getenv("KLINGAI_MODEL") or "kolors-virtual-try-on-v1"

        if self.access_key and self.secret_key:
            print(f"[KlingAIService] Keys loaded successfully: access_key={self.access_key[:10]}...")
            print(f"[KlingAIService] Using model: {self.model}")
        else:
            if not self.access_key:
                print("[KlingAIService] No access key found in settings or environment")
            if not self.secret_key:
                print("[KlingAIService] No secret key found in settings or environment")

    def _reload_settings_if_changed(self) -> None:
        """Hot-reload settings if file has changed"""
        try:
            if not self._settings_path:
                return
            if not Path(self._settings_path).exists():
                return
            mtime = Path(self._settings_path).stat().st_mtime
            if self._settings_mtime and mtime <= self._settings_mtime:
                return
            
            data = json.loads(Path(self._settings_path).read_text(encoding="utf-8"))
            old_access, old_secret, old_model = self.access_key, self.secret_key, self.model
            self.access_key = data.get("KLINGAI_ACCESS_KEY") or self.access_key
            self.secret_key = data.get("KLINGAI_SECRET_KEY") or self.secret_key
            self.model = data.get("KLINGAI_MODEL") or self.model
            self._settings_mtime = mtime
            
            if (self.access_key != old_access) or (self.secret_key != old_secret) or (self.model != old_model):
                print(f"[KlingAIService] Settings reloaded (model: {self.model})")
        except Exception:
            # swallow errors to avoid breaking requests
            pass

    def _generate_jwt_token(self) -> str:
        """
        Generate JWT token for KlingAI API authentication
        Follows JWT (JSON Web Token, RFC 7519) standard
        """
        if not jwt:
            print("[KlingAIService] Warning: PyJWT library not available")
            return ""
        
        if not self.access_key or not self.secret_key:
            print("[KlingAIService] Warning: Missing access_key or secret_key for JWT generation")
            return ""
        
        current_time = int(time.time())
        
        # JWT Header
        headers = {
            "alg": "HS256",
            "typ": "JWT"
        }
        
        # JWT Payload
        payload = {
            "iss": self.access_key,  # Issuer: access key
            "exp": current_time + 1800,  # Expiration: current time + 30 minutes
            "nbf": current_time - 5  # Not before: current time - 5 seconds
        }
        
        try:
            # Generate JWT token
            token = jwt.encode(payload, self.secret_key, algorithm="HS256", headers=headers)
            print(f"[KlingAIService] JWT token generated successfully (expires in 30min)")
            return token
        except Exception as e:
            print(f"[KlingAIService] Error generating JWT token: {e}")
            return ""

    def _get_headers(self) -> Dict[str, str]:
        """Generate authentication headers for KlingAI API"""
        token = self._generate_jwt_token()
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}" if token else "",
        }
        
        return headers

    def _image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Convert image file to base64 string
        Note: KlingAI requires base64 string WITHOUT data URI prefix
        """
        try:
            if not Path(image_path).exists():
                return None
            
            # Read and optionally convert to JPEG if needed
            if Image:
                with Image.open(image_path) as img:
                    # Convert to RGB if needed
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGB')
                    
                    # Save to BytesIO buffer
                    buffer = BytesIO()
                    img.save(buffer, format='JPEG', quality=95)
                    buffer.seek(0)
                    image_bytes = buffer.read()
            else:
                # Fallback: just read the file
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
            
            # Convert to base64 - NO data URI prefix per KlingAI API docs
            base64_str = base64.b64encode(image_bytes).decode('utf-8')
            return base64_str
        except Exception as e:
            print(f"[KlingAIService] Error converting image to base64: {e}")
            return None

    def generate_virtual_tryon(
        self,
        user_image_path: str,
        garment: Any = None,
        session_id: Optional[str] = None,
        user_note: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """
        Main virtual try-on method compatible with TryOnService interface
        
        Args:
            user_image_path: Path to user's photo
            garment: Garment info dict with 'image_path'
            session_id: Session identifier
            user_note: Additional user preferences (not used by KlingAI)
            
        Returns:
            Dict with status, mode, output_path, and message
        """
        # hot-reload settings when file changes
        self._reload_settings_if_changed()
        
        session_ref = session_id or f"session_{int(time.time())}"
        output_filename = f"gen_{int(time.time()*1000)}.jpg"
        output_path = self.outputs_dir / output_filename
        public_path = f"/static/outputs/{output_filename}"

        if not Path(user_image_path).exists():
            return {"status": "error", "mode": "error", "output_path": None, "message": "User image not found"}

        # Check API credentials
        if not self.access_key or not self.secret_key:
            print(f"[KlingAIService] generate_virtual_tryon: API keys are missing")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "KlingAI API keys not configured"}

        if not requests:
            print(f"[KlingAIService] generate_virtual_tryon: requests library not available")
            return {"status": "error", "mode": "unavailable", "output_path": None, "message": "HTTP library not available"}

        # Extract garment image path
        garment_image_path = None
        print(f"[KlingAIService] Resolving garment path from: {garment}")
        try:
            if isinstance(garment, dict):
                g_rel = garment.get("image_path")
                print(f"[KlingAIService] Garment relative path: {g_rel}")
                if g_rel:
                    # Try to resolve relative path
                    rel_clean = str(g_rel).strip("/")
                    if rel_clean.startswith("static/"):
                        rel_clean = rel_clean[len("static/"):]
                    
                    print(f"[KlingAIService] Cleaned relative path: {rel_clean}")
                    
                    # Try static dir first
                    candidate = self.static_dir / rel_clean
                    print(f"[KlingAIService] Trying: {candidate} (exists: {candidate.exists()})")
                    if candidate.exists():
                        garment_image_path = str(candidate)
                    else:
                        # Try app/static
                        candidate2 = self.base_dir / "app" / "static" / rel_clean
                        print(f"[KlingAIService] Trying: {candidate2} (exists: {candidate2.exists()})")
                        if candidate2.exists():
                            garment_image_path = str(candidate2)
                        else:
                            # Try apps/web/static
                            candidate3 = self.base_dir / "apps" / "web" / "static" / rel_clean
                            print(f"[KlingAIService] Trying: {candidate3} (exists: {candidate3.exists()})")
                            if candidate3.exists():
                                garment_image_path = str(candidate3)
            elif isinstance(garment, list) and len(garment) > 0:
                # Handle list of garments, take first one
                g_rel = (garment[0] or {}).get("image_path")
                if g_rel:
                    rel_clean = str(g_rel).strip("/")
                    if rel_clean.startswith("static/"):
                        rel_clean = rel_clean[len("static/"):]
                    candidate = self.static_dir / rel_clean
                    if candidate.exists():
                        garment_image_path = str(candidate)
        except Exception as e:
            print(f"[KlingAIService] Error resolving garment path: {e}")
            import traceback
            traceback.print_exc()

        print(f"[KlingAIService] Final garment_image_path: {garment_image_path}")
        
        if not garment_image_path or not Path(garment_image_path).exists():
            print(f"[KlingAIService] ❌ Garment image not found!")
            print(f"[KlingAIService]    garment_image_path: {garment_image_path}")
            print(f"[KlingAIService]    Path exists: {Path(garment_image_path).exists() if garment_image_path else 'N/A'}")
            return {"status": "error", "mode": "error", "output_path": None, "message": "Garment image not found"}

        try:
            # Convert images to base64
            print(f"[KlingAIService] Converting images to base64...")
            user_base64 = self._image_to_base64(user_image_path)
            garment_base64 = self._image_to_base64(garment_image_path)
            
            if not user_base64 or not garment_base64:
                return {"status": "error", "mode": "error", "output_path": None, "message": "Failed to process images"}

            # Prepare API request
            # Based on KlingAI API documentation
            payload = {
                "model_name": self.model,
                "human_image": user_base64,
                "cloth_image": garment_base64,
            }
            
            print(f"[KlingAIService] Using model: {self.model}")
            
            headers = self._get_headers()
            
            # Debug: Log headers (mask sensitive data)
            headers_debug = {k: (v[:20] + "..." if len(v) > 20 and k in ["Authorization", "X-Signature"] else v) 
                           for k, v in headers.items()}
            print(f"[KlingAIService] Request headers: {headers_debug}")
            print(f"[KlingAIService] Calling KlingAI API for session={session_ref}")
            
            # Call KlingAI API
            api_url = f"{self.API_BASE_URL}/v1/images/kolors-virtual-try-on"
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            # Check response
            if response.status_code != 200:
                error_msg = f"KlingAI API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                    print(f"[KlingAIService] Full error response: {error_data}")
                except Exception:
                    print(f"[KlingAIService] Response text: {response.text[:200]}")
                print(f"[KlingAIService] API error: {error_msg}")
                return {"status": "error", "mode": "api_error", "output_path": None, "message": error_msg}
            
            # Parse response
            result = response.json()
            print(f"[KlingAIService] API response received")
            print(f"[KlingAIService] Full response: {result}")
            
            # Extract task ID for polling (if async)
            task_id = result.get("data", {}).get("task_id")
            if task_id:
                # KlingAI uses async processing, need to poll for result
                print(f"[KlingAIService] Task created: {task_id}, polling for result...")
                final_result = self._poll_task_result(task_id, timeout=120)
                if not final_result:
                    return {"status": "error", "mode": "timeout", "output_path": None, "message": "Task timeout"}
                result = final_result
            else:
                print(f"[KlingAIService] No task_id found in response, checking for immediate result...")
            
            # Extract image URL or base64
            image_url = None
            image_data = None
            
            data = result.get("data", {})
            if isinstance(data, dict):
                # Check for image URL in direct response
                image_url = data.get("image_url") or data.get("url")
                # Check for base64 data
                image_data = data.get("image") or data.get("image_data")
                
                # Check for result in task_result format (async response)
                if not image_url and not image_data:
                    task_result = data.get("task_result", {})
                    
                    # Try images array format (KlingAI actual response)
                    images = task_result.get("images", [])
                    if images and len(images) > 0:
                        image_url = images[0].get("url")
                        print(f"[KlingAIService] Found image URL in task_result.images: {image_url}")
                    
                    # Try works array format (alternative format)
                    if not image_url:
                        works = task_result.get("works", [])
                        if works and len(works) > 0:
                            resource = works[0].get("resource", {})
                            image_url = resource.get("resource")
                            print(f"[KlingAIService] Found image URL in task_result.works: {image_url}")
            
            if image_url:
                # Download image from URL
                print(f"[KlingAIService] Downloading result from URL: {image_url}")
                img_response = requests.get(image_url, timeout=30)
                print(f"[KlingAIService] Download response: {img_response.status_code}, size: {len(img_response.content)} bytes")
                
                if img_response.status_code == 200:
                    with open(output_path, 'wb') as f:
                        f.write(img_response.content)
                    
                    # Verify file was written
                    import os
                    file_size = os.path.getsize(output_path)
                    print(f"[KlingAIService] Result saved to {output_path}")
                    print(f"[KlingAIService] File size: {file_size} bytes")
                    print(f"[KlingAIService] Public path: {public_path}")
                    
                    return {"status": "ok", "mode": "klingai", "output_path": public_path, "message": None}
                else:
                    print(f"[KlingAIService] Download failed: HTTP {img_response.status_code}")
                    return {"status": "error", "mode": "download_error", "output_path": None, "message": f"Failed to download image: HTTP {img_response.status_code}"}
            elif image_data:
                # Decode base64 image
                print(f"[KlingAIService] Decoding base64 result...")
                # Remove data URL prefix if present
                if "," in image_data:
                    image_data = image_data.split(",", 1)[1]
                image_bytes = base64.b64decode(image_data)
                with open(output_path, 'wb') as f:
                    f.write(image_bytes)
                print(f"[KlingAIService] Result saved to {output_path}")
                return {"status": "ok", "mode": "klingai", "output_path": public_path, "message": None}
            
            print(f"[KlingAIService] No image in response")
            return {"status": "error", "mode": "no_image", "output_path": None, "message": "KlingAI API 未返回圖片"}

        except requests.exceptions.Timeout:
            print(f"[KlingAIService] API timeout")
            return {"status": "error", "mode": "timeout", "output_path": None, "message": "KlingAI API 請求超時"}
        except Exception as exc:
            print(f"[KlingAIService] Exception: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "mode": "error", "output_path": None, "message": f"{type(exc).__name__}: {exc}"}

    def _poll_task_result(self, task_id: str, timeout: int = 120) -> Optional[Dict]:
        """
        Poll for task result if KlingAI uses async processing
        
        Args:
            task_id: Task ID from initial API call
            timeout: Max time to wait in seconds
            
        Returns:
            Final result dict or None if timeout
        """
        if not requests:
            return None
            
        start_time = time.time()
        poll_interval = 2  # Poll every 2 seconds
        
        api_url = f"{self.API_BASE_URL}/v1/images/kolors-virtual-try-on/{task_id}"
        
        poll_count = 0
        while time.time() - start_time < timeout:
            try:
                poll_count += 1
                headers = self._get_headers()
                response = requests.get(api_url, headers=headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"[KlingAIService] Poll #{poll_count}: HTTP {response.status_code}")
                    try:
                        error_data = response.json()
                        print(f"[KlingAIService] Error response: {error_data}")
                    except:
                        print(f"[KlingAIService] Response text: {response.text[:200]}")
                    time.sleep(poll_interval)
                    continue
                
                result = response.json()
                # KlingAI uses "task_status" not "status"
                task_status = result.get("data", {}).get("task_status")
                
                # Log every 5th poll or when status changes
                if poll_count % 5 == 1 or task_status not in ("processing", "pending", "submitted"):
                    print(f"[KlingAIService] Poll #{poll_count} (elapsed {int(time.time() - start_time)}s): task_status={task_status}")
                    if poll_count == 1:
                        print(f"[KlingAIService] Full response: {result}")
                
                if task_status in ("completed", "succeed", "success"):
                    print(f"[KlingAIService] Task {task_id} completed after {poll_count} polls")
                    print(f"[KlingAIService] Final result: {result}")
                    return result
                elif task_status in ("failed", "error"):
                    print(f"[KlingAIService] Task {task_id} failed: {result.get('message')}")
                    print(f"[KlingAIService] Error details: {result}")
                    return None
                
                # Still processing
                time.sleep(poll_interval)
                
            except Exception as e:
                print(f"[KlingAIService] Polling error #{poll_count}: {e}")
                time.sleep(poll_interval)
        
        print(f"[KlingAIService] Task {task_id} timeout after {timeout}s")
        return None

