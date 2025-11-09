import os
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Dict, List, Optional


@dataclass
class AppConfig:
    database_url: str
    secret_key: str
    log_level: str
    store_base_url: str
    currency: str

    def get_store_url(self, product_id: str) -> str:
        base = self.store_base_url.rstrip("/")
        return f"{base}/product/{product_id}"


ALLOWED_HOT_KEYS = {"CURRENCY"}
SENSITIVE_KEYS = {"LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET", "SECRET_KEY", "PAYPAL_CLIENT_SECRET"}


def validate_currency(value: Optional[str]) -> str:
    v = (value or "TWD").strip().upper()
    if len(v) != 3:
        raise ValueError("Invalid currency code: expected ISO4217 length 3")
    return v


def _load_settings_file() -> dict:
    try:
        path = Path(__file__).resolve().parents[1] / "data" / "settings.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def load_env() -> AppConfig:
    # 設定以 data/settings.json 為主，.env 為後備
    s = _load_settings_file()
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
    secret_key = os.getenv("SECRET_KEY", "dev_secret")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    store_base_url = (s.get("STORE_BASE_URL") or os.getenv("STORE_BASE_URL") or "http://127.0.0.1:5000").rstrip("/")
    currency = validate_currency(s.get("CURRENCY") or os.getenv("CURRENCY"))
    return AppConfig(
        database_url=database_url,
        secret_key=secret_key,
        log_level=log_level,
        store_base_url=store_base_url,
        currency=currency,
    )


def refresh_non_sensitive(overrides: Dict[str, str], current: AppConfig) -> AppConfig:
    updates = {k: v for k, v in (overrides or {}).items() if k in ALLOWED_HOT_KEYS}
    currency = validate_currency(updates.get("CURRENCY", current.currency))
    return AppConfig(
        database_url=current.database_url,
        secret_key=current.secret_key,
        log_level=current.log_level,
        store_base_url=current.store_base_url,
        currency=currency,
    )


def requires_restart(changed_keys: List[str]) -> bool:
    if not changed_keys:
        return False
    return any(k in SENSITIVE_KEYS for k in changed_keys)


