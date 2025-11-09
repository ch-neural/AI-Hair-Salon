from sqlalchemy import Boolean, Column, String
from .base import Base


class Tag(Base):
    __tablename__ = "tag"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)


