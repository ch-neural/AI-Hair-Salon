"""
商品選項模型
用於定義商品的可選屬性（例如：顏色、尺寸、材質）
"""
from sqlalchemy import Column, String, Integer, ForeignKey, Boolean, Text, func, DateTime
from sqlalchemy.orm import relationship
from .base import Base


class ProductOption(Base):
    """商品選項（例如：顏色、尺寸、材質）"""
    __tablename__ = "product_option"

    id = Column(String(36), primary_key=True)
    product_id = Column(String(36), ForeignKey("product.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(128), nullable=False)  # 選項名稱（例如：顏色）
    sort_order = Column(Integer, nullable=False, default=0)  # 顯示順序
    is_required = Column(Boolean, nullable=False, default=False)  # 是否必選
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # 關聯選項值
    values = relationship("ProductOptionValue", back_populates="option", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "name": self.name,
            "sort_order": self.sort_order,
            "is_required": self.is_required,
            "values": [v.to_dict() for v in sorted(self.values, key=lambda x: x.sort_order)]
        }


class ProductOptionValue(Base):
    """商品選項值（例如：紅色、藍色）"""
    __tablename__ = "product_option_value"

    id = Column(String(36), primary_key=True)
    option_id = Column(String(36), ForeignKey("product_option.id", ondelete="CASCADE"), nullable=False)
    value = Column(String(255), nullable=False)  # 選項值（例如：紅色）
    additional_price = Column(Integer, nullable=False, default=0)  # 額外價格（分）
    sort_order = Column(Integer, nullable=False, default=0)  # 顯示順序
    is_available = Column(Boolean, nullable=False, default=True)  # 是否可用
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    # 關聯選項
    option = relationship("ProductOption", back_populates="values")

    def to_dict(self):
        return {
            "id": self.id,
            "option_id": self.option_id,
            "value": self.value,
            "additional_price": self.additional_price,
            "sort_order": self.sort_order,
            "is_available": self.is_available
        }

