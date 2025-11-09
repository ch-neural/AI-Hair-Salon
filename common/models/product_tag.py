from sqlalchemy import Column, ForeignKey, String
from .base import Base


class ProductTag(Base):
    __tablename__ = "product_tag"

    product_id = Column(String(36), ForeignKey("product.id"), primary_key=True)
    tag_id = Column(String(36), ForeignKey("tag.id"), primary_key=True)


