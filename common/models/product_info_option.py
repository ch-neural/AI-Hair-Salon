from sqlalchemy import Boolean, Column, Integer, String
from .base import Base


class ProductInfoOption(Base):
    __tablename__ = "product_info_option"

    id = Column(String(36), primary_key=True)
    field_id = Column(String(36), nullable=False)
    value = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


