"""使用者前台介面路由（換髮型系統）。"""

from __future__ import annotations

from flask import Blueprint, current_app, render_template, session


user_bp = Blueprint("live_demo_user", __name__)


def _get_demo_components() -> dict:
    return current_app.extensions["live_demo_components"]


@user_bp.get("/")
def kiosk_home():
    components = _get_demo_components()
    garments = [g.to_dict() for g in components["garment_repo"].list_garments()]
    categories = sorted({g["category"] for g in garments}) if garments else []
    session.setdefault("user_photo_path", None)
    return render_template(
        "user/index.html",
        garments=garments,
        categories=categories,
    )

