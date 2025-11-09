from sqlalchemy import Boolean, Column, Integer, String
from .base import Base


class ProductInfoField(Base):
    __tablename__ = "product_info_field"

    id = Column(String(36), primary_key=True)
    label = Column(String(255), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


