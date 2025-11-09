"""Video Record model for storing video generation history."""
from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.sql import func
from .base import Base


class VideoRecord(Base):
    """記錄每次影片生成的詳細信息。"""
    __tablename__ = "video_records"

    task_id = Column(String(64), primary_key=True, nullable=False, doc="影片生成 task ID")
    created_at = Column(DateTime, nullable=False, default=func.now(), doc="創建時間")
    tryon_session_id = Column(String(64), nullable=True, doc="關聯的試衣 session ID")
    source_image_path = Column(String(512), nullable=True, doc="來源圖片路徑（試衣結果）")
    prompt = Column(Text, nullable=True, doc="動作 prompt")
    duration = Column(Integer, nullable=False, default=10, doc="影片時長（秒）")
    video_path = Column(String(512), nullable=True, doc="生成的影片路徑")
    status = Column(String(32), nullable=False, default="pending", doc="狀態：pending/processing/completed/failed/error")
    error_message = Column(Text, nullable=True, doc="錯誤信息")
    
    def to_dict(self):
        """轉換為字典格式供 API 返回。"""
        return {
            "task_id": self.task_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tryon_session_id": self.tryon_session_id,
            "source_image_path": self.source_image_path,
            "prompt": self.prompt,
            "duration": self.duration,
            "video_path": self.video_path,
            "status": self.status,
            "error_message": self.error_message,
        }

