from typing import Dict, Optional, Tuple
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import and_
from ..db.session import get_session
from ..models.product import Product
from ..models.cart_item import CartItem


class CartService:
    """Cart operations backed by DB."""

    def __init__(self, session_factory=get_session):
        self._session_factory = session_factory

    @staticmethod
    def _identity(session_id: Optional[str], user_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        return session_id or None, user_id or None

    def get_cart(self, *, session_id: Optional[str], user_id: Optional[str]) -> Dict:
        sid, uid = self._identity(session_id, user_id)
        with self._session_factory() as session:
            q = session.query(CartItem)
            if uid:
                q = q.filter(CartItem.user_id == uid)
            else:
                q = q.filter(CartItem.session_id == sid)
            items = [
                {
                    "id": it.id,
                    "product_id": it.product_id,
                    "variant": it.variant or {},
                    "quantity": it.quantity,
                    "unit_price": float(it.unit_price or 0),
                    "currency": it.currency,
                }
                for it in q.all()
            ]
            subtotal = float(sum((Decimal(str(it["unit_price"])) * Decimal(it["quantity"])) for it in items))
            currency = items[0]["currency"] if items else "TWD"
            return {"items": items, "subtotal": subtotal, "currency": currency}

    def add_item(self, *, session_id: Optional[str], user_id: Optional[str], product_id: str, variant: dict, quantity: int) -> Dict:
        if not product_id:
            raise ValueError("product_id required")
        qnty = int(quantity or 1)
        if qnty <= 0:
            raise ValueError("quantity must be > 0")
        sid, uid = self._identity(session_id, user_id)
        with self._session_factory() as session:
            prod = (
                session.query(Product)
                .filter(Product.id == product_id, Product.is_active.is_(True))
                .first()
            )
            if not prod:
                raise ValueError("product not found or inactive")
            if prod.stock is not None and qnty > int(prod.stock):
                raise ValueError("insufficient stock")

            # Try merge with existing same product + variant for this identity
            existing = (
                session.query(CartItem)
                .filter(
                    and_(
                        CartItem.product_id == product_id,
                        (CartItem.user_id == uid) if uid else (CartItem.session_id == sid),
                    )
                )
                .first()
            )
            if existing:
                new_q = existing.quantity + qnty
                if prod.stock is not None and new_q > int(prod.stock):
                    raise ValueError("insufficient stock")
                existing.quantity = new_q
                item_id = existing.id
            else:
                item = CartItem(
                    id=str(uuid4()),
                    session_id=sid,
                    user_id=uid,
                    product_id=product_id,
                    variant=variant or {},
                    quantity=qnty,
                    unit_price=prod.price,
                    currency=prod.currency,
                )
                session.add(item)
                item_id = item.id
            session.flush()
            return {"status": "added", "item_id": item_id}

    def update_item(self, *, item_id: str, variant: Optional[dict] = None, quantity: Optional[int] = None) -> Dict:
        if not item_id:
            raise ValueError("item_id required")
        with self._session_factory() as session:
            it = session.query(CartItem).filter(CartItem.id == item_id).first()
            if not it:
                raise ValueError("item not found")
            if variant is not None:
                it.variant = variant
            if quantity is not None:
                qnty = int(quantity)
                if qnty < 0:
                    raise ValueError("quantity must be >= 0")
                if qnty == 0:
                    session.delete(it)
                    session.flush()
                    return {"status": "updated", "item_id": item_id}
                # stock check
                prod = session.query(Product).filter(Product.id == it.product_id).first()
                if prod and prod.stock is not None and qnty > int(prod.stock):
                    raise ValueError("insufficient stock")
                it.quantity = qnty
            session.flush()
            return {"status": "updated", "item_id": item_id}

    def remove_item(self, *, item_id: str) -> None:
        with self._session_factory() as session:
            it = session.query(CartItem).filter(CartItem.id == item_id).first()
            if it:
                session.delete(it)
                session.flush()
        return None


