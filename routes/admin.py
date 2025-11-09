"""管理後台路由（換髮型系統）。"""

from __future__ import annotations

import json
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


admin_bp = Blueprint("live_demo_admin", __name__, url_prefix="/admin")


def _components() -> dict:
    return current_app.extensions["live_demo_components"]


def _config():
    return current_app.config["LIVE_DEMO_CONFIG"]


def _is_authenticated() -> bool:
    return bool(session.get("live_demo_admin"))


def _require_login():
    if _is_authenticated():
        return None
    return redirect(url_for("live_demo_admin.login_form"))


@admin_bp.before_request
def guard_private_routes():
    if request.endpoint and request.endpoint.startswith("live_demo_admin."):
        public = {
            "live_demo_admin.login_form",
            "live_demo_admin.login_submit",
        }
        if request.endpoint not in public:
            redirect_response = _require_login()
            if redirect_response is not None:
                return redirect_response
    return None


@admin_bp.get("/login")
def login_form():
    return render_template("admin/login.html")


@admin_bp.post("/login")
def login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    cfg = _config()
    if username == cfg.admin_username and password == cfg.admin_password:
        session["live_demo_admin"] = True
        return redirect(url_for("live_demo_admin.dashboard"))
    return render_template(
        "admin/login.html",
        error_message="帳號或密碼錯誤，請重新輸入。",
    ), 401


@admin_bp.get("/logout")
def logout():
    session.pop("live_demo_admin", None)
    return redirect(url_for("live_demo_admin.login_form"))


@admin_bp.get("/")
def dashboard():
    garments = [g.to_dict() for g in _components()["garment_repo"].list_garments()]
    return render_template("admin/dashboard.html", garments=garments)


@admin_bp.get("/settings")
def settings_page():
    """顯示設定頁面"""
    return render_template("admin/settings.html")


@admin_bp.get("/history")
def history_page():
    """顯示試衣記錄頁面"""
    return render_template("admin/history.html")


@admin_bp.get("/settings/data")
def get_settings():
    """取得當前設定"""
    config = _config()
    settings_file = config.data_dir / "settings.json"
    
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            return jsonify({"status": "ok", "settings": settings})
        except Exception as e:
            return jsonify({"status": "error", "message": f"讀取設定檔失敗: {str(e)}"}), 500
    else:
        # 返回預設設定
        default_settings = {
            "GEMINI_API_KEY": "",
            "GEMINI_MODEL": "gemini-2.5-flash-image",
            "GEMINI_LLM": "gemini-2.5-flash",
            "GEMINI_SAFETY_SETTINGS": "BLOCK_ONLY_HIGH",
            "KLINGAI_VIDEO_ACCESS_KEY": "",
            "KLINGAI_VIDEO_SECRET_KEY": "",
            "KLINGAI_VIDEO_MODEL": "kling-v2-5-turbo",
            "KLINGAI_VIDEO_MODE": "std",
            "KLINGAI_VIDEO_DURATION": "5",
            "VENDOR_TRYON": "Gemini"
        }
        return jsonify({"status": "ok", "settings": default_settings})


@admin_bp.post("/settings/data")
def update_settings():
    """更新設定"""
    try:
        config = _config()
        settings_file = config.data_dir / "settings.json"
        
        payload = request.get_json(silent=True) or {}
        settings = payload.get("settings", {})
        
        if not settings:
            return jsonify({"status": "error", "message": "未提供設定資料"}), 400
        
        # 驗證必要欄位
        valid_keys = {
            "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_LLM", "GEMINI_SAFETY_SETTINGS",
            "KLINGAI_VIDEO_ACCESS_KEY", "KLINGAI_VIDEO_SECRET_KEY",
            "KLINGAI_VIDEO_MODEL", "KLINGAI_VIDEO_MODE", "KLINGAI_VIDEO_DURATION",
            "VENDOR_TRYON"
        }
        
        # 過濾只保留有效的設定
        filtered_settings = {k: v for k, v in settings.items() if k in valid_keys}
        
        # 寫入檔案
        settings_file.write_text(
            json.dumps(filtered_settings, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        return jsonify({
            "status": "ok",
            "message": "設定已儲存成功",
            "settings": filtered_settings
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"儲存設定失敗: {str(e)}"}), 500


@admin_bp.post("/change-password")
def change_password():
    """修改管理員密碼"""
    try:
        payload = request.get_json(silent=True) or {}
        current_password = payload.get("current_password", "").strip()
        new_password = payload.get("new_password", "").strip()
        confirm_password = payload.get("confirm_password", "").strip()
        
        if not current_password or not new_password or not confirm_password:
            return jsonify({"status": "error", "message": "請填寫所有欄位"}), 400
        
        config = _config()
        
        # 驗證當前密碼
        if current_password != config.admin_password:
            return jsonify({"status": "error", "message": "當前密碼錯誤"}), 401
        
        # 驗證新密碼
        if new_password != confirm_password:
            return jsonify({"status": "error", "message": "新密碼與確認密碼不一致"}), 400
        
        if len(new_password) < 6:
            return jsonify({"status": "error", "message": "新密碼長度至少需要6個字元"}), 400
        
        # 儲存到 admin.json
        admin_file = config.admin_credentials_file
        admin_data = {
            "username": config.admin_username,
            "password": new_password
        }
        
        admin_file.write_text(
            json.dumps(admin_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        # 更新當前 config 中的密碼
        config.admin_password = new_password
        
        return jsonify({
            "status": "ok",
            "message": "密碼已成功修改"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"修改密碼失敗: {str(e)}"}), 500

