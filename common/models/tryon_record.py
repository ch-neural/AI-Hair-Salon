"""TryOn Record model for storing virtual try-on history."""
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from .base import Base


class TryOnRecord(Base):
    """記錄每次虛擬試衣的詳細信息。"""
    __tablename__ = "tryon_records"

    session_id = Column(String(64), primary_key=True, nullable=False, doc="試衣 session ID")
    created_at = Column(DateTime, nullable=False, default=func.now(), doc="創建時間")
    user_image_path = Column(String(512), nullable=True, doc="用戶上傳的人像圖片路徑")
    garment_image_path = Column(String(512), nullable=True, doc="服飾圖片路徑")
    result_image_path = Column(String(512), nullable=True, doc="合成結果圖片路徑")
    status = Column(String(32), nullable=False, default="pending", doc="狀態：pending/processing/ok/error")
    error_message = Column(Text, nullable=True, doc="錯誤信息")
    
    def to_dict(self):
        """轉換為字典格式供 API 返回。"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user_image_path": self.user_image_path,
            "garment_image_path": self.garment_image_path,
            "result_image_path": self.result_image_path,
            "status": self.status,
            "error_message": self.error_message,
        }

