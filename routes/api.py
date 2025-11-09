"""提供使用者與管理端使用的 API 路由（換髮型系統）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request, session


api_bp = Blueprint("live_demo_api", __name__, url_prefix="/api")


def _components() -> Dict[str, Any]:
    return current_app.extensions["live_demo_components"]


def _config():
    return current_app.config["LIVE_DEMO_CONFIG"]


def _ensure_admin() -> bool:
    return bool(session.get("live_demo_admin"))


@api_bp.get("/garments")
def list_garments():
    repo = _components()["garment_repo"]
    data = [g.to_dict() for g in repo.list_garments()]
    for item in data:
        item["image_url"] = "/" + item["image_path"].replace("\\", "/")
    return jsonify({"garments": data})


@api_bp.post("/upload-user-photo")
def upload_user_photo():
    if "photo" not in request.files:
        return jsonify({"error": "找不到上傳的圖片，請重新拍攝或選擇檔案。"}), 400

    photo_service = _components()["photo_service"]
    try:
        abs_path, rel_path = photo_service.save_user_photo(request.files["photo"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    session["user_photo_path"] = abs_path
    return jsonify(
        {
            "status": "ok",
            "photo_url": "/" + rel_path.replace("\\", "/"),
        }
    )


@api_bp.post("/reset-user-photo")
def reset_user_photo():
    session.pop("user_photo_path", None)
    session.pop("last_tryon_session", None)
    return jsonify({"status": "ok"})


@api_bp.post("/try-on")
def start_try_on():
    payload = request.get_json(silent=True) or {}
    garment_id = str(payload.get("garment_id", "")).strip()
    note = str(payload.get("note", "")).strip()

    user_photo_path = session.get("user_photo_path")
    if not user_photo_path:
        return jsonify({"error": "請先拍攝或選擇個人照片。"}), 400

    repo = _components()["garment_repo"]
    garment = repo.get_garment(garment_id)
    if garment is None:
        return jsonify({"error": "找不到選擇的髮型，請重新載入。"}), 404

    photo_service = _components()["photo_service"]
    photo_validator = _components()["photo_validator"]
    provider = _components()["tryon_provider"]
    history_repo = _components()["history_repo"]

    try:
        user_data_url = photo_service.encode_as_data_url(Path(user_photo_path))
        garment_path = Path(_config().demo_root) / garment.image_path
        garment_data_url = photo_service.encode_as_data_url(garment_path)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    # 驗證照片是否為半身正面照
    validation_result = photo_validator.validate_photo(user_data_url)
    if not validation_result.get("is_valid", False):
        error_message = validation_result.get("message", "照片不符合要求，請使用正面半身照。")
        # 記錄驗證失敗的記錄
        history_repo.add_record(
            user_photo_path=user_photo_path,
            garment_photo_path=str(garment_path),
            status="failed",
            error_message=f"照片驗證失敗：{error_message}",
            garment_name=garment.name,
            garment_id=garment_id,
        )
        return jsonify({"error": error_message}), 400

    result = provider.start_session_with_analysis(
        user_image_path=Path(user_photo_path),
        user_image_data_url=user_data_url,
        garment=garment,
        garment_image_path=garment_path,
        garment_image_data_url=garment_data_url,
        user_note=note or None,
    )

    if result.get("status") == "error":
        # 記錄失敗的換髮型
        history_repo.add_record(
            user_photo_path=user_photo_path,
            garment_photo_path=str(garment_path),
            status="failed",
            error_message=result.get("message", "換髮型服務目前無法使用。"),
            garment_name=garment.name,
            garment_id=garment_id,
        )
        return jsonify({"error": result.get("message", "換髮型服務目前無法使用。")}), 500

    session["last_tryon_session"] = result.get("session_id")
    # 儲存記錄ID到session，稍後更新結果
    session_id = result.get("session_id")
    record = history_repo.add_record(
        user_photo_path=user_photo_path,
        garment_photo_path=str(garment_path),
        status="processing",
        garment_name=garment.name,
        garment_id=garment_id,
    )
    session[f"record_id_{session_id}"] = record.record_id
    
    return jsonify(result)


@api_bp.get("/try-on/<session_id>")
def poll_try_on(session_id: str):
    provider = _components()["tryon_provider"]
    history_repo = _components()["history_repo"]
    photo_service = _components()["photo_service"]
    
    status = provider.check_session(session_id)
    
    # 更新歷史記錄
    record_id = session.get(f"record_id_{session_id}")
    if record_id:
        if status.get("status") == "ok":
            output = status.get("output")
            if output:
                status["result_url"] = output
                
                # 生成前後對比圖片
                user_photo_path = session.get("user_photo_path")
                if user_photo_path:
                    try:
                        # 獲取輸出目錄
                        output_dir = _config().tryon_output_dir
                        before_path = Path(user_photo_path)
                        
                        # 處理 output 路徑（去掉前導斜杠）
                        output_clean = output.lstrip("/")
                        after_path = Path(_config().demo_root) / output_clean
                        
                        # 生成 before_url
                        try:
                            before_rel_path = Path(user_photo_path).relative_to(Path(_config().demo_root))
                            status["before_url"] = "/" + str(before_rel_path).replace("\\", "/")
                        except ValueError:
                            # 如果 user_photo_path 不在 demo_root 下，使用絕對路徑
                            status["before_url"] = "/" + str(Path(user_photo_path).relative_to(Path(user_photo_path).anchor))
                        
                        # 生成對比圖片
                        _, comparison_rel_path = photo_service.create_comparison_image(
                            before_path=before_path,
                            after_path=after_path,
                            output_dir=output_dir,
                        )
                        
                        # 添加對比圖片 URL 到返回結果
                        status["comparison_url"] = "/" + comparison_rel_path.replace("\\", "/")
                    except Exception as exc:
                        # 如果生成對比圖片失敗，不影響主流程
                        print(f"生成對比圖片失敗: {exc}")
                        import traceback
                        traceback.print_exc()
                
                # 更新記錄為成功
                history_repo.update_record(
                    record_id=record_id,
                    result_photo_path=output,
                    status="success",
                )
        elif status.get("status") == "error":
            # 更新記錄為失敗
            history_repo.update_record(
                record_id=record_id,
                status="failed",
                error_message=status.get("message", "換髮型失敗"),
            )
    
    if status.get("status") == "error":
        return jsonify(status), 500
    return jsonify(status)


@api_bp.post("/admin/garments")
def create_garment():
    if not _ensure_admin():
        return jsonify({"error": "需要管理者登入才能操作此功能。"}), 401
    if "image" not in request.files:
        return jsonify({"error": "請上傳髮型圖片。"}), 400

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip() or "未分類"
    description = request.form.get("description", "").strip()
    if not name:
        return jsonify({"error": "請輸入髮型名稱。"}), 400

    photo_service = _components()["photo_service"]
    repo = _components()["garment_repo"]
    try:
        _, rel_path = photo_service.save_garment_image(request.files["image"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    garment = repo.add_garment(
        name=name,
        category=category,
        description=description,
        image_path=rel_path,
    )
    data = garment.to_dict()
    data["image_url"] = "/" + rel_path.replace("\\", "/")
    return jsonify({"status": "ok", "garment": data})


@api_bp.put("/admin/garments/<garment_id>")
def update_garment(garment_id: str):
    if not _ensure_admin():
        return jsonify({"error": "需要管理者登入才能操作此功能。"}), 401

    payload = request.get_json(silent=True) or {}
    repo = _components()["garment_repo"]
    garment = repo.update_garment(
        garment_id,
        name=payload.get("name"),
        category=payload.get("category"),
        description=payload.get("description"),
    )
    if garment is None:
        return jsonify({"error": "找不到指定的髮型項目。"}), 404
    data = garment.to_dict()
    data["image_url"] = "/" + data["image_path"].replace("\\", "/")
    return jsonify({"status": "ok", "garment": data})


@api_bp.delete("/admin/garments/<garment_id>")
def remove_garment(garment_id: str):
    if not _ensure_admin():
        return jsonify({"error": "需要管理者登入才能操作此功能。"}), 401

    repo = _components()["garment_repo"]
    removed = repo.delete_garment(garment_id)
    if not removed:
        return jsonify({"error": "找不到指定的髮型項目。"}), 404
    return jsonify({"status": "ok"})


# --- Video Generation API ---

@api_bp.get("/video/enabled")
def check_video_enabled():
    """檢查影片生成功能是否可用"""
    video_service = _components()["video_service"]
    return jsonify({"enabled": video_service.is_enabled()})


@api_bp.post("/video/generate")
def generate_video():
    """開始影片生成"""
    payload = request.get_json(silent=True) or {}
    image_path = payload.get("image_path")
    prompt = payload.get("prompt", "身體旋轉一圈")
    duration = payload.get("duration", 5)
    
    if not image_path:
        return jsonify({"error": "請提供換髮型結果圖片路徑"}), 400
    
    # Convert relative path to absolute path
    config = _config()
    if image_path.startswith("/"):
        # URL path format like /static/outputs/xxx.jpg
        rel_path = image_path.lstrip("/")
        if rel_path.startswith("static/"):
            abs_path = config.demo_root / rel_path
        else:
            abs_path = config.demo_root / "static" / rel_path
    else:
        abs_path = Path(image_path)
    
    if not abs_path.exists():
        return jsonify({"error": "找不到換髮型結果圖片"}), 404
    
    video_service = _components()["video_service"]
    result = video_service.generate_video(
        image_path=str(abs_path),
        prompt=prompt,
        duration=duration
    )
    
    if result.get("status") == "error":
        return jsonify({"error": result.get("message", "影片生成失敗")}), 500
    
    return jsonify(result)


@api_bp.get("/video/<task_id>")
def poll_video(task_id: str):
    """輪詢影片生成狀態"""
    video_service = _components()["video_service"]
    history_repo = _components()["history_repo"]
    
    result = video_service.poll_video_task(task_id)
    
    # 如果影片生成成功，嘗試更新最近的換髮型記錄
    if result.get("status") == "completed" and result.get("video_url"):
        session_id = session.get("last_tryon_session")
        if session_id:
            record_id = session.get(f"record_id_{session_id}")
            if record_id:
                history_repo.update_record(
                    record_id=record_id,
                    video_path=result.get("video_url"),
                )
    
    return jsonify(result)


# --- Try-On History API ---

@api_bp.get("/admin/history")
def list_history():
    """列出換髮型記錄"""
    if not _ensure_admin():
        return jsonify({"error": "需要管理者登入才能操作此功能。"}), 401
    
    history_repo = _components()["history_repo"]
    config = _config()
    
    # 分頁參數
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    offset = (page - 1) * per_page
    
    records = history_repo.list_records(limit=per_page, offset=offset)
    total = history_repo.count_records()
    
    # 轉換路徑為URL
    records_data = []
    for record in records:
        record_dict = record.to_dict()
        
        # 轉換路徑為相對URL
        if record_dict.get("user_photo_path"):
            user_path = Path(record_dict["user_photo_path"])
            if user_path.is_absolute():
                try:
                    rel_path = user_path.relative_to(config.demo_root)
                    record_dict["user_photo_url"] = "/" + str(rel_path).replace("\\", "/")
                except ValueError:
                    record_dict["user_photo_url"] = None
        
        if record_dict.get("garment_photo_path"):
            garment_path = Path(record_dict["garment_photo_path"])
            if garment_path.is_absolute():
                try:
                    rel_path = garment_path.relative_to(config.demo_root)
                    record_dict["garment_photo_url"] = "/" + str(rel_path).replace("\\", "/")
                except ValueError:
                    record_dict["garment_photo_url"] = None
        
        if record_dict.get("result_photo_path"):
            result_path = record_dict["result_photo_path"]
            if result_path.startswith("/"):
                record_dict["result_photo_url"] = result_path
            else:
                result_path_obj = Path(result_path)
                if result_path_obj.is_absolute():
                    try:
                        rel_path = result_path_obj.relative_to(config.demo_root)
                        record_dict["result_photo_url"] = "/" + str(rel_path).replace("\\", "/")
                    except ValueError:
                        record_dict["result_photo_url"] = None
                else:
                    record_dict["result_photo_url"] = "/" + result_path
        
        if record_dict.get("video_path"):
            video_path = record_dict["video_path"]
            if video_path.startswith("/"):
                record_dict["video_url"] = video_path
            else:
                record_dict["video_url"] = "/" + video_path
        
        records_data.append(record_dict)
    
    return jsonify({
        "status": "ok",
        "records": records_data,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
    })


@api_bp.delete("/admin/history/<record_id>")
def delete_history_record(record_id: str):
    """刪除換髮型記錄"""
    if not _ensure_admin():
        return jsonify({"error": "需要管理者登入才能操作此功能。"}), 401
    
    history_repo = _components()["history_repo"]
    deleted = history_repo.delete_record(record_id)
    
    if not deleted:
        return jsonify({"error": "找不到指定的記錄。"}), 404
    
    return jsonify({"status": "ok", "message": "記錄已刪除"})

