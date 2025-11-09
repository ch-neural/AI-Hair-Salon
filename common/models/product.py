from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, func
from .base import Base


class Product(Base):
    __tablename__ = "product"

    id = Column(String(36), primary_key=True)
    sku = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    images = Column(JSON, nullable=True)
    category_id = Column(String(36), ForeignKey("category.id"), nullable=True)
    variants = Column(JSON, nullable=True)
    stock = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


