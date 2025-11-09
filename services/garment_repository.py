"""管理觸控換髮型系統髮型資料的儲存模組。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4


@dataclass
class Garment:
    """代表單一髮型項目的資料結構。"""

    garment_id: str
    name: str
    category: str
    description: str
    image_path: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "garment_id": self.garment_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "image_path": self.image_path,
        }


class GarmentRepository:
    """提供檔案型儲存的髮型資料存取介面。"""

    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file

    def list_garments(self) -> List[Garment]:
        """讀取全部髮型資料。"""

        raw = self._load()
        return [Garment(**item) for item in raw]

    def get_garment(self, garment_id: str) -> Optional[Garment]:
        """依識別碼取得髮型資料。"""

        for item in self.list_garments():
            if item.garment_id == garment_id:
                return item
        return None

    def add_garment(
        self,
        *,
        name: str,
        category: str,
        description: str,
        image_path: str,
    ) -> Garment:
        """新增髮型資料。"""

        garment = Garment(
            garment_id=f"garment_{uuid4().hex}",
            name=name,
            category=category,
            description=description,
            image_path=image_path,
        )
        data = self._load()
        data.append(garment.to_dict())
        self._write(data)
        return garment

    def update_garment(
        self,
        garment_id: str,
        *,
        name: Optional[str] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> Optional[Garment]:
        """更新髮型資料，回傳更新後結果。"""

        data = self._load()
        updated = None
        for entry in data:
            if entry.get("garment_id") == garment_id:
                if name is not None:
                    entry["name"] = name
                if category is not None:
                    entry["category"] = category
                if description is not None:
                    entry["description"] = description
                if image_path is not None:
                    entry["image_path"] = image_path
                updated = Garment(**entry)
                break
        if updated is None:
            return None
        self._write(data)
        return updated

    def delete_garment(self, garment_id: str) -> bool:
        """刪除指定髮型資料。"""

        data = self._load()
        remaining = [item for item in data if item.get("garment_id") != garment_id]
        if len(remaining) == len(data):
            return False
        self._write(remaining)
        return True

    def _load(self) -> List[Dict[str, str]]:
        if not self._data_file.exists():
            return []
        text = self._data_file.read_text(encoding="utf-8")
        if not text.strip():
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("髮型資料庫格式錯誤，請檢查 garments.json。") from exc
        if not isinstance(payload, list):
            raise ValueError("髮型資料庫內容異常，預期為陣列格式。")
        normalized: List[Dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "garment_id": str(item.get("garment_id", f"garment_{uuid4().hex}")),
                    "name": str(item.get("name", "未命名髮型")),
                    "category": str(item.get("category", "未分類")),
                    "description": str(item.get("description", "")),
                    "image_path": str(item.get("image_path", "")),
                }
            )
        return normalized

    def _write(self, data: List[Dict[str, str]]) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        self._data_file.write_text(content + "\n", encoding="utf-8")

