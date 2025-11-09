"""試衣記錄儲存庫。"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class TryOnRecord:
    """試衣記錄資料模型。"""

    record_id: str
    timestamp: str
    user_photo_path: str
    garment_photo_path: str
    result_photo_path: Optional[str]
    video_path: Optional[str]
    status: str  # "success" or "failed"
    error_message: Optional[str] = None
    garment_name: Optional[str] = None
    garment_id: Optional[str] = None

    def to_dict(self) -> dict:
        """轉換為字典格式。"""
        return asdict(self)


class TryOnHistoryRepository:
    """管理試衣記錄的儲存與查詢。"""

    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """確保資料檔案存在。"""
        if not self._data_file.exists():
            self._data_file.parent.mkdir(parents=True, exist_ok=True)
            self._data_file.write_text("[]", encoding="utf-8")

    def add_record(
        self,
        user_photo_path: str,
        garment_photo_path: str,
        result_photo_path: Optional[str] = None,
        video_path: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        garment_name: Optional[str] = None,
        garment_id: Optional[str] = None,
    ) -> TryOnRecord:
        """新增試衣記錄。"""
        import uuid

        record_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        record = TryOnRecord(
            record_id=record_id,
            timestamp=timestamp,
            user_photo_path=user_photo_path,
            garment_photo_path=garment_photo_path,
            result_photo_path=result_photo_path,
            video_path=video_path,
            status=status,
            error_message=error_message,
            garment_name=garment_name,
            garment_id=garment_id,
        )

        records = self._load_records()
        records.append(record.to_dict())
        self._save_records(records)

        return record

    def update_record(
        self,
        record_id: str,
        result_photo_path: Optional[str] = None,
        video_path: Optional[str] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[TryOnRecord]:
        """更新試衣記錄。"""
        records = self._load_records()

        for i, record in enumerate(records):
            if record.get("record_id") == record_id:
                if result_photo_path is not None:
                    record["result_photo_path"] = result_photo_path
                if video_path is not None:
                    record["video_path"] = video_path
                if status is not None:
                    record["status"] = status
                if error_message is not None:
                    record["error_message"] = error_message

                records[i] = record
                self._save_records(records)
                return TryOnRecord(**record)

        return None

    def get_record(self, record_id: str) -> Optional[TryOnRecord]:
        """根據ID取得試衣記錄。"""
        records = self._load_records()
        for record in records:
            if record.get("record_id") == record_id:
                return TryOnRecord(**record)
        return None

    def list_records(
        self, limit: Optional[int] = None, offset: int = 0
    ) -> List[TryOnRecord]:
        """列出試衣記錄（按時間倒序）。"""
        records = self._load_records()
        # 按時間戳倒序排列
        records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if limit is not None:
            records = records[offset : offset + limit]
        else:
            records = records[offset:]

        return [TryOnRecord(**r) for r in records]

    def count_records(self) -> int:
        """計算總記錄數。"""
        records = self._load_records()
        return len(records)

    def delete_record(self, record_id: str) -> bool:
        """刪除試衣記錄。"""
        records = self._load_records()
        original_count = len(records)
        records = [r for r in records if r.get("record_id") != record_id]

        if len(records) < original_count:
            self._save_records(records)
            return True
        return False

    def _load_records(self) -> List[dict]:
        """從檔案載入記錄。"""
        try:
            data = json.loads(self._data_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"[TryOnHistoryRepository] 載入記錄失敗: {e}")
        return []

    def _save_records(self, records: List[dict]) -> None:
        """儲存記錄到檔案。"""
        try:
            self._data_file.write_text(
                json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            print(f"[TryOnHistoryRepository] 儲存記錄失敗: {e}")

