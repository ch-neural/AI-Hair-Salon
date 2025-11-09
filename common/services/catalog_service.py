from typing import List, Optional, Dict, Tuple
import time
from sqlalchemy import or_, func, distinct
from ..db.session import get_session
from ..models.product import Product
from ..models.category import Category
from ..models.product_tag import ProductTag
from ..models.tag import Tag
from ..utils.pagination import normalize_paging
from ..utils.dto import to_product_dto


class CatalogService:
    """Catalog querying service (skeleton).

    Responsibilities:
    - List/search products with pagination and optional category filter
    - Get single product detail
    - Emit cache invalidation events on admin updates (implemented later)
    """

    # naive in-process cache: key -> (ts, result)
    _cache: Dict[Tuple, Tuple[float, Dict]] = {}
    _cache_ttl_seconds: int = 60

    def __init__(self, session_factory=get_session):
        self._session_factory = session_factory

    def list_products(
        self,
        *,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict:
        """Return dict: { items: [ProductDTO], page, page_size, total }

        NOTE: Initial skeleton returns empty result set; real implementation
        will query database with filters and pagination.
        """
        p, ps = normalize_paging(page, page_size)
        cache_key = (query or "", category or "", tuple(sorted(tags or [])), int(page), int(page_size))
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] <= self._cache_ttl_seconds:
            return cached[1]

        with self._session_factory() as session:
            q = session.query(Product).filter(Product.is_active.is_(True))
            if query:
                like = f"%{query}%"
                q = q.filter(
                    or_(
                        Product.name.ilike(like),
                        Product.description.ilike(like),
                        Product.sku.ilike(like),
                    )
                )
            if category:
                q = (
                    q.join(Category, Category.id == Product.category_id, isouter=True)
                    .filter(or_(Category.slug == category, Product.category_id == category))
                )
            if tags:
                # Support both tag ids and slugs; apply intersection (product must have all tags)
                tag_list = [t.strip() for t in tags if t and t.strip()]
                if tag_list:
                    q = (
                        q.join(ProductTag, ProductTag.product_id == Product.id)
                        .join(Tag, Tag.id == ProductTag.tag_id)
                        .filter(or_(Tag.id.in_(tag_list), Tag.slug.in_(tag_list)))
                        .group_by(Product.id)
                        .having(func.count(distinct(Tag.id)) >= len(set(tag_list)))
                    )
            total = q.count()
            rows = (
                q.order_by(Product.sort_order.desc(), Product.created_at.desc())
                .offset((p - 1) * ps)
                .limit(ps)
                .all()
            )
            items = [to_product_dto(r) for r in rows]
            result = {"items": items, "page": p, "page_size": ps, "total": total}
            # store in cache
            self._cache[cache_key] = (now, result)
            return result

    def get_product(self, product_id: str) -> dict:
        """Return ProductDTO for given product id."""
        with self._session_factory() as session:
            r = (
                session.query(Product)
                .filter(Product.id == product_id, Product.is_active.is_(True))
                .first()
            )
            return to_product_dto(r) if r else {}

    def invalidate_cache_for_product(self, product_id: Optional[str] = None) -> None:
        """Invalidate query caches. For simplicity, clear all cache or by product if needed."""
        # simple: clear all cached entries
        self._cache.clear()
        return None


