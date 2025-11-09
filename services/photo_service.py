"""處理圖片儲存與轉換的服務模組。"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Tuple
from uuid import uuid4

from werkzeug.datastructures import FileStorage

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - 若 Pillow 缺失則覆用原始檔案
    Image = None  # type: ignore


class PhotoService:
    """提供觸控試衣系統的圖片寫入與讀取工具。"""

    def __init__(self, user_photo_dir: Path, garment_dir: Path) -> None:
        self._user_photo_dir = user_photo_dir
        self._garment_dir = garment_dir
        self._user_photo_dir.mkdir(parents=True, exist_ok=True)
        self._garment_dir.mkdir(parents=True, exist_ok=True)

    def save_user_photo(self, uploaded: FileStorage) -> Tuple[str, str]:
        """儲存使用者上傳照片，回傳 (檔案路徑, 相對路徑)。"""

        self._validate_upload(uploaded)
        filename = self._safe_filename(uploaded.filename, prefix="user")
        return self._save_image(uploaded, self._user_photo_dir / filename)

    def save_garment_image(self, uploaded: FileStorage) -> Tuple[str, str]:
        """儲存服飾圖片，回傳 (檔案路徑, 相對路徑)。"""

        self._validate_upload(uploaded)
        filename = self._safe_filename(uploaded.filename, prefix="garment")
        return self._save_image(uploaded, self._garment_dir / filename)

    def encode_as_data_url(self, file_path: Path) -> str:
        """將檔案轉換為 data URL 格式。"""

        if not file_path.exists():
            raise FileNotFoundError("指定的圖片不存在，請重新上傳。")
        mimetype = "image/jpeg"
        raw = file_path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mimetype};base64,{b64}"

    def create_comparison_image(
        self, before_path: Path, after_path: Path, output_dir: Path
    ) -> Tuple[str, str]:
        """生成前後對比圖片，回傳 (檔案路徑, 相對路徑)。"""

        if Image is None:
            raise RuntimeError("需要安裝 Pillow 才能生成對比圖片。")

        if not before_path.exists():
            raise FileNotFoundError("找不到試髮前的照片。")
        if not after_path.exists():
            raise FileNotFoundError("找不到試髮後的照片。")

        # 打開兩張圖片
        with Image.open(before_path) as before_img, Image.open(after_path) as after_img:
            # 轉換為 RGB
            before_rgb = before_img.convert("RGB")
            after_rgb = after_img.convert("RGB")

            # 統一高度，保持寬高比
            target_height = 800
            before_aspect = before_rgb.width / before_rgb.height
            after_aspect = after_rgb.width / after_rgb.height

            before_width = int(target_height * before_aspect)
            after_width = int(target_height * after_aspect)

            before_resized = before_rgb.resize((before_width, target_height), Image.LANCZOS)
            after_resized = after_rgb.resize((after_width, target_height), Image.LANCZOS)

            # 創建合併圖片（水平拼接，中間加 20px 間隔）
            gap = 20
            total_width = before_width + gap + after_width
            comparison = Image.new("RGB", (total_width, target_height), (255, 255, 255))

            # 貼上圖片
            comparison.paste(before_resized, (0, 0))
            comparison.paste(after_resized, (before_width + gap, 0))

            # 添加文字標籤
            try:
                from PIL import ImageDraw, ImageFont
                
                draw = ImageDraw.Draw(comparison)
                # 嘗試使用系統字體，如果失敗則跳過文字
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 40)
                except:
                    font = ImageFont.load_default()
                
                # 在圖片頂部添加標籤
                draw.text((before_width // 2, 30), "試髮前", fill=(255, 255, 255), 
                         font=font, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
                draw.text((before_width + gap + after_width // 2, 30), "試髮後", 
                         fill=(255, 255, 255), font=font, anchor="mm", 
                         stroke_width=2, stroke_fill=(0, 0, 0))
            except Exception:
                # 如果添加文字失敗，跳過
                pass

            # 保存對比圖片
            output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"comparison_{uuid4().hex[:12]}.jpg"
            output_path = output_dir / filename
            comparison.save(output_path, format="JPEG", quality=90)

            relative_path = output_path.relative_to(output_path.parents[2])
            return str(output_path), str(relative_path)

    def _validate_upload(self, uploaded: FileStorage) -> None:
        if uploaded is None or uploaded.filename is None or not uploaded.filename.strip():
            raise ValueError("請選擇要上傳的圖片檔案。")

    def _safe_filename(self, original: str, prefix: str) -> str:
        ext = ".jpg"
        name = original.rsplit(".", 1)
        if len(name) == 2:
            ext_candidate = name[1].lower()
            if ext_candidate in {"jpg", "jpeg", "png", "heic", "heif", "webp"}:
                ext = ".jpg"
        suffix = Path(original).stem.lower()[:16]
        unique = uuid4().hex[:8]
        return f"{prefix}_{suffix}_{unique}{ext}"

    def _save_image(self, uploaded: FileStorage, target_path: Path) -> Tuple[str, str]:
        binary = uploaded.read()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        if not binary:
            raise ValueError("圖片內容為空，請重新拍攝或選擇檔案。")

        if Image is None:
            target_path.write_bytes(binary)
        else:
            with Image.open(BytesIO(binary)) as image:
                rgb = image.convert("RGB")
                rgb.save(target_path, format="JPEG", quality=92)

        relative_path = target_path.relative_to(target_path.parents[2])
        return str(target_path), str(relative_path)

