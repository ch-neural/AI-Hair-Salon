from typing import Dict, List


def build_product_bubble(product: Dict) -> Dict:
    title = product.get("name") or "商品"
    desc = (product.get("description") or "").strip()[:60]
    price = product.get("price")
    currency = product.get("currency") or "TWD"
    image_url = (product.get("images") or [None])[0]
    return {
        "type": "bubble",
        "hero": {"type": "image", "url": image_url, "size": "full", "aspectMode": "cover"} if image_url else None,
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "md"},
                {"type": "text", "text": desc, "wrap": True, "size": "sm", "color": "#666666"},
                {"type": "text", "text": f"{currency} {price}", "weight": "bold", "size": "sm"},
            ],
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "button", "style": "primary", "action": {"type": "message", "label": "試穿", "text": f"試穿 {product.get('id')}"}},
                {"type": "button", "style": "secondary", "action": {"type": "uri", "label": "前往商店", "uri": product.get("store_url")}},
            ],
        },
    }


def build_catalog_carousel(products: List[Dict]) -> Dict:
    bubbles = [build_product_bubble(p) for p in products]
    # Remove None hero for schema correctness
    for b in bubbles:
        if b.get("hero") is None:
            b.pop("hero")
    return {"type": "carousel", "contents": bubbles or []}


