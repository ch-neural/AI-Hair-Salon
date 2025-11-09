from typing import Dict, Optional
from uuid import uuid4
from decimal import Decimal
from ..db.session import get_session
from ..models.cart_item import CartItem
from ..models.order import Order
from .logging import log_event


class OrderService:
    """Order creation and retrieval backed by DB."""

    def __init__(self, session_factory=get_session):
        self._session_factory = session_factory

    def create_order(self, *, session_id: Optional[str], user_id: Optional[str], request_id: Optional[str] = None) -> Dict:
        """Create order from current cart (idempotency by request_id)."""
        with self._session_factory() as session:
            # idempotency: if request_id provided and existing order found, return it
            if request_id:
                existing = (
                    session.query(Order)
                    .filter(Order.external_payment_id == request_id)
                    .first()
                )
                if existing:
                    return {"order_id": existing.id, "status": existing.status}
            q = session.query(CartItem)
            if user_id:
                q = q.filter(CartItem.user_id == user_id)
            else:
                q = q.filter(CartItem.session_id == session_id)
            items = q.all()
            subtotal = Decimal("0")
            currency = "TWD"
            snapshot = []
            for it in items:
                currency = it.currency or currency
                line = Decimal(str(it.unit_price or 0)) * Decimal(it.quantity)
                subtotal += line
                snapshot.append(
                    {
                        "product_id": it.product_id,
                        "variant": it.variant or {},
                        "quantity": it.quantity,
                        "unit_price": float(it.unit_price or 0),
                        "currency": it.currency,
                    }
                )
            oid = str(uuid4())
            order = Order(
                id=oid,
                session_id=session_id,
                user_id=user_id,
                items=snapshot,
                subtotal=subtotal,
                currency=currency,
                tax=Decimal("0"),
                total=subtotal,
                status="pending",
                payment_status="unpaid",
                external_payment_id=request_id,
            )
            session.add(order)
            # Clear cart after order creation
            for it in items:
                session.delete(it)
            # Ensure subsequent reads in same session observe changes
            session.flush()
            log_event("info", "order.created", order_id=oid, items=len(items), subtotal=float(subtotal))
            return {"order_id": oid, "status": "pending"}

    def get_order(self, order_id: str) -> Dict:
        if not order_id:
            return {}
        with self._session_factory() as session:
            o = session.query(Order).filter(Order.id == order_id).first()
            if not o:
                return {}
            return {"order_id": o.id, "status": o.status, "subtotal": float(o.subtotal or 0), "total": float(o.total or 0)}


