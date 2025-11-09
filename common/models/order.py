from sqlalchemy import Column, DateTime, JSON, Numeric, String, func
from .base import Base


class Order(Base):
    __tablename__ = "order"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(128), nullable=True)
    user_id = Column(String(128), nullable=True)
    items = Column(JSON, nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    tax = Column(Numeric(12, 2), nullable=False)
    total = Column(Numeric(12, 2), nullable=False)
    status = Column(String(32), nullable=False)
    payment_status = Column(String(32), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    paid_at = Column(DateTime, nullable=True)
    external_payment_id = Column(String(128), nullable=True)


