from typing import Any, Dict


def to_product_dto(row: Any) -> Dict:
    return {
        "id": getattr(row, "id", None),
        "sku": getattr(row, "sku", None),
        "name": getattr(row, "name", None),
        "description": getattr(row, "description", None),
        "price": float(getattr(row, "price", 0) or 0),
        "currency": getattr(row, "currency", None),
        "images": getattr(row, "images", None) or [],
        "category_id": getattr(row, "category_id", None),
        "variants": getattr(row, "variants", None) or {},
        "stock": getattr(row, "stock", 0) or 0,
        "is_active": bool(getattr(row, "is_active", True)),
    }


