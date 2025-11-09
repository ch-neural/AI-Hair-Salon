"""Trial-on preference model for storing reusable style notes"""
from sqlalchemy import Column, String, Text, DateTime, Boolean
from common.models.base import Base
from datetime import datetime


class TryOnPreference(Base):
    """試衣偏好設定模型 - 儲存可重複使用的試衣風格偏好"""
    __tablename__ = "tryon_preferences"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String(100), nullable=False)  # 偏好名稱，例如："正式商務風"
    note = Column(Text, nullable=False)  # 詳細的試衣偏好說明
    is_active = Column(Boolean, default=True, nullable=False)  # 是否啟用
    display_order = Column(String, nullable=True)  # 顯示順序（可選）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "note": self.note,
            "is_active": self.is_active,
            "display_order": self.display_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

