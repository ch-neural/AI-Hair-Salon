"""
KlingAI Video Generation Service
Based on https://app.klingai.com/global/dev/document-api/apiReference/model/imageToVideo
Authentication uses JWT (JSON Web Token, RFC 7519)
"""
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

try:
    import jwt  # PyJWT library for token generation
except Exception:
    jwt = None  # type: ignore


class KlingAIVideoService:
    """
    KlingAI Video API 整合服務：
    - 透過 KlingAI API 將圖片轉換為 10 秒動態影片
    - 支持自定義動作 prompt
    - 靜態資源與輸出位於 apps/web/static/
    """

    API_BASE_URL = "https://api.klingai.com"
    SUPPORTED_VIDEO_MODELS = {
        "kling-v1": "Kling 第一代",
        "kling-v1-5": "Kling v1.5 改進版",
        "kling-v1-6": "Kling v1.6 最新版",
        "kling-v2-master": "Kling 第二代 Master",
        "kling-v2-1": "Kling v2.1",
        "kling-v2-1-master": "Kling v2.1 Master",
        "kling-v2-5-turbo": "Kling v2.5 Turbo 快速版",
    }

    def __init__(self, outputs_dir: Optional[str] = None, settings_json_path: Optional[str] = None) -> None:
        self.base_dir = Path.cwd()
        
        # Determine static directory path
        apps_web_static = self.base_dir / "apps" / "web" / "static"
        app_static = self.base_dir / "app" / "static"
        
        if apps_web_static.exists():
            self.static_dir = apps_web_static
        elif app_static.exists():
            self.static_dir = app_static
        else:
            self.static_dir = apps_web_static
        
        # Always use the passed outputs_dir parameter when available
        if outputs_dir:
            self.outputs_dir = Path(outputs_dir)
        else:
            self.outputs_dir = self.static_dir / "outputs"
        
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        print(f"[KlingAIVideoService] Static directory: {self.static_dir}")
        print(f"[KlingAIVideoService] Output directory: {self.outputs_dir}")
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        self.access_key: Optional[str] = None
        self.secret_key: Optional[str] = None
        self.model: str = "kling-v1"  # Default model
        self.mode: str = "std"  # Default mode: std or pro
        self.duration: int = 5  # Default duration in seconds
        
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
                print(f"[KlingAIVideoService] Error loading settings from {path_to_load}: {e}")
                settings = {}

        # Load values, falling back from settings to environment variables
        self.access_key = settings.get("KLINGAI_VIDEO_ACCESS_KEY") or os.getenv("KLINGAI_VIDEO_ACCESS_KEY")
        self.secret_key = settings.get("KLINGAI_VIDEO_SECRET_KEY") or os.getenv("KLINGAI_VIDEO_SECRET_KEY")
        self.model = settings.get("KLINGAI_VIDEO_MODEL") or os.getenv("KLINGAI_VIDEO_MODEL") or "kling-v1"
        self.mode = settings.get("KLINGAI_VIDEO_MODE") or os.getenv("KLINGAI_VIDEO_MODE") or "std"
        self.duration = int(settings.get("KLINGAI_VIDEO_DURATION") or os.getenv("KLINGAI_VIDEO_DURATION") or "5")

        if self.access_key and self.secret_key:
            print(f"[KlingAIVideoService] Keys loaded successfully: access_key={self.access_key[:10]}...")
            print(f"[KlingAIVideoService] Using model: {self.model}, mode: {self.mode}, duration: {self.duration}s")
        else:
            if not self.access_key:
                print("[KlingAIVideoService] No access key found in settings or environment")
            if not self.secret_key:
                print("[KlingAIVideoService] No secret key found in settings or environment")

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
            old_access, old_secret, old_model, old_mode, old_duration = self.access_key, self.secret_key, self.model, self.mode, self.duration
            self.access_key = data.get("KLINGAI_VIDEO_ACCESS_KEY") or self.access_key
            self.secret_key = data.get("KLINGAI_VIDEO_SECRET_KEY") or self.secret_key
            self.model = data.get("KLINGAI_VIDEO_MODEL") or self.model
            self.mode = data.get("KLINGAI_VIDEO_MODE") or self.mode
            self.duration = int(data.get("KLINGAI_VIDEO_DURATION") or self.duration)
            self._settings_mtime = mtime
            
            if (self.access_key != old_access) or (self.secret_key != old_secret) or (self.model != old_model) or (self.mode != old_mode) or (self.duration != old_duration):
                print(f"[KlingAIVideoService] Settings reloaded (model: {self.model}, mode: {self.mode}, duration: {self.duration}s)")
        except Exception:
            # swallow errors to avoid breaking requests
            pass

    def _generate_jwt_token(self) -> str:
        """
        Generate JWT token for KlingAI API authentication
        Follows JWT (JSON Web Token, RFC 7519) standard
        """
        if not jwt:
            print("[KlingAIVideoService] Warning: PyJWT library not available")
            return ""
        
        if not self.access_key or not self.secret_key:
            print("[KlingAIVideoService] Warning: Missing access_key or secret_key for JWT generation")
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
            print(f"[KlingAIVideoService] JWT token generated successfully (expires in 30min)")
            return token
        except Exception as e:
            print(f"[KlingAIVideoService] Error generating JWT token: {e}")
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
        
        IMPORTANT: KlingAI requires base64 string WITHOUT data URI prefix
        Reference: https://app.klingai.com/global/dev/document-api/apiReference/model/imageToVideo
        
        Correct format: iVBORw0KGgoAAAANSUhEUgAAAAUA...
        Incorrect format: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA...
        """
        try:
            if not Path(image_path).exists():
                return None
            
            # Read image file
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            
            # Convert to base64 - NO data URI prefix per KlingAI API docs
            base64_str = base64.b64encode(image_bytes).decode('utf-8')
            
            # Ensure no prefix was accidentally added
            if base64_str.startswith('data:'):
                # Remove prefix if present
                if ',' in base64_str:
                    base64_str = base64_str.split(',', 1)[1]
            
            return base64_str
        except Exception as e:
            print(f"[KlingAIVideoService] Error converting image to base64: {e}")
            return None

    def generate_video(
        self,
        image_path: str,
        prompt: str = "身體旋轉一圈",
        duration: int = 10,
        session_id: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """
        Generate video from image using KlingAI API
        
        Args:
            image_path: Path to source image (usually the try-on result)
            prompt: Motion prompt describing the desired animation
            duration: Video duration in seconds (5 or 10, default 10)
            session_id: Session identifier for tracking
            
        Returns:
            Dict with status, task_id, output_path, and message
        """
        # hot-reload settings when file changes
        self._reload_settings_if_changed()
        
        session_ref = session_id or f"video_{int(time.time())}"
        
        # Check API credentials
        if not self.access_key or not self.secret_key:
            print(f"[KlingAIVideoService] generate_video: API keys are missing")
            return {"status": "error", "task_id": None, "output_path": None, "message": "KlingAI Video API keys not configured"}

        if not requests:
            print(f"[KlingAIVideoService] generate_video: requests library not available")
            return {"status": "error", "task_id": None, "output_path": None, "message": "HTTP library not available"}

        # Validate image path
        if not Path(image_path).exists():
            print(f"[KlingAIVideoService] Image not found: {image_path}")
            return {"status": "error", "task_id": None, "output_path": None, "message": "Source image not found"}

        try:
            # Convert image to base64
            print(f"[KlingAIVideoService] Converting image to base64...")
            image_base64 = self._image_to_base64(image_path)
            
            if not image_base64:
                return {"status": "error", "task_id": None, "output_path": None, "message": "Failed to process image"}

            # Prepare API request
            # Based on KlingAI Image-to-Video API documentation
            # Reference: https://app.klingai.com/global/dev/document-api/apiReference/model/imageToVideo
            payload = {
                "model_name": self.model,
                "image": image_base64,  # Pure Base64 string, NO data: prefix
                "prompt": prompt,
                "duration": str(duration),  # "5" or "10"
            }
            
            # Note: Some models (like turbo variants) may not support the 'mode' parameter
            # The support range varies by model version - only add if model supports it
            # Turbo models typically have fixed performance mode
            if "turbo" not in self.model.lower():
                payload["mode"] = self.mode  # "std" or "pro"
                print(f"[KlingAIVideoService] Mode: {self.mode}")
            else:
                print(f"[KlingAIVideoService] Mode: (not applicable for turbo model)")
            
            print(f"[KlingAIVideoService] Using model: {self.model}")
            print(f"[KlingAIVideoService] Prompt: {prompt}")
            print(f"[KlingAIVideoService] Duration: {duration}s")
            print(f"[KlingAIVideoService] Image Base64 length: {len(image_base64)} chars")
            
            headers = self._get_headers()
            
            # Debug: Log headers (mask sensitive data)
            headers_debug = {k: (v[:20] + "..." if len(v) > 20 and k in ["Authorization"] else v) 
                           for k, v in headers.items()}
            print(f"[KlingAIVideoService] Request headers: {headers_debug}")
            print(f"[KlingAIVideoService] Calling KlingAI Video API for session={session_ref}")
            
            # Call KlingAI API
            api_url = f"{self.API_BASE_URL}/v1/videos/image2video"
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            # Check response
            if response.status_code != 200:
                error_msg = f"KlingAI Video API error: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                    print(f"[KlingAIVideoService] Full error response: {error_data}")
                except Exception:
                    print(f"[KlingAIVideoService] Response text: {response.text[:200]}")
                print(f"[KlingAIVideoService] API error: {error_msg}")
                return {"status": "error", "task_id": None, "output_path": None, "message": error_msg}
            
            # Parse response
            result = response.json()
            print(f"[KlingAIVideoService] API response received")
            print(f"[KlingAIVideoService] Full response: {result}")
            
            # Extract task ID for polling (KlingAI uses async processing)
            task_id = result.get("data", {}).get("task_id")
            if not task_id:
                print(f"[KlingAIVideoService] No task_id found in response")
                return {"status": "error", "task_id": None, "output_path": None, "message": "No task ID returned from API"}
            
            print(f"[KlingAIVideoService] Video generation task created: {task_id}")
            
            # Return task info for client-side polling
            return {
                "status": "processing",
                "task_id": task_id,
                "output_path": None,
                "message": "Video generation started"
            }

        except requests.exceptions.Timeout:
            print(f"[KlingAIVideoService] API timeout")
            return {"status": "error", "task_id": None, "output_path": None, "message": "KlingAI Video API 請求超時"}
        except Exception as exc:
            print(f"[KlingAIVideoService] Exception: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "task_id": None, "output_path": None, "message": f"{type(exc).__name__}: {exc}"}

    def poll_video_task(self, task_id: str) -> Dict[str, Optional[str]]:
        """
        Poll for video generation task status
        
        Args:
            task_id: Task ID from initial API call
            
        Returns:
            Dict with status, output_path, and message
        """
        if not requests:
            return {"status": "error", "output_path": None, "message": "HTTP library not available"}
        
        if not self.access_key or not self.secret_key:
            return {"status": "error", "output_path": None, "message": "API keys not configured"}
        
        try:
            headers = self._get_headers()
            api_url = f"{self.API_BASE_URL}/v1/videos/image2video/{task_id}"
            
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"[KlingAIVideoService] Poll error: HTTP {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"[KlingAIVideoService] Error response: {error_data}")
                    return {"status": "error", "output_path": None, "message": error_data.get("message", "Polling failed")}
                except:
                    print(f"[KlingAIVideoService] Response text: {response.text[:200]}")
                    return {"status": "error", "output_path": None, "message": f"HTTP {response.status_code}"}
            
            result = response.json()
            data = result.get("data", {})
            task_status = data.get("task_status")
            
            print(f"[KlingAIVideoService] Poll task {task_id}: status={task_status}")
            
            if task_status in ("succeed", "success"):
                # Extract video URL
                task_result = data.get("task_result", {})
                videos = task_result.get("videos", [])
                
                if videos and len(videos) > 0:
                    video_url = videos[0].get("url")
                    
                    if video_url:
                        # Download video
                        print(f"[KlingAIVideoService] Downloading video from: {video_url}")
                        output_filename = f"video_{int(time.time()*1000)}.mp4"
                        output_path = self.outputs_dir / output_filename
                        public_path = f"/static/outputs/{output_filename}"
                        
                        video_response = requests.get(video_url, timeout=120)
                        
                        if video_response.status_code == 200:
                            with open(output_path, 'wb') as f:
                                f.write(video_response.content)
                            
                            file_size = output_path.stat().st_size
                            print(f"[KlingAIVideoService] Video saved to {output_path}")
                            print(f"[KlingAIVideoService] File size: {file_size} bytes")
                            
                            return {
                                "status": "completed",
                                "output_path": public_path,
                                "message": None
                            }
                        else:
                            print(f"[KlingAIVideoService] Download failed: HTTP {video_response.status_code}")
                            return {"status": "error", "output_path": None, "message": f"Failed to download video: HTTP {video_response.status_code}"}
                
                return {"status": "error", "output_path": None, "message": "No video URL in response"}
            
            elif task_status in ("failed", "error"):
                error_msg = data.get("task_status_msg") or "Video generation failed"
                print(f"[KlingAIVideoService] Task {task_id} failed: {error_msg}")
                return {"status": "failed", "output_path": None, "message": error_msg}
            
            elif task_status in ("processing", "submitted", "pending"):
                return {"status": "processing", "output_path": None, "message": "Video is being generated..."}
            
            else:
                return {"status": "unknown", "output_path": None, "message": f"Unknown status: {task_status}"}
                
        except Exception as e:
            print(f"[KlingAIVideoService] Polling error: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "output_path": None, "message": str(e)}

