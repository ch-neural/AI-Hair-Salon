from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, func
from .base import Base


class CartItem(Base):
    __tablename__ = "cart_item"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(128), nullable=True)
    user_id = Column(String(128), nullable=True)
    product_id = Column(String(36), ForeignKey("product.id"), nullable=False)
    variant = Column(JSON, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    added_at = Column(DateTime, nullable=False, server_default=func.now())


