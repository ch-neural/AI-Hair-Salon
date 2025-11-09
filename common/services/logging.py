import json
import sys
from datetime import datetime


def log_event(level: str, event: str, **fields) -> None:
    payload = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level.lower(),
        "event": event,
    }
    payload.update(fields or {})
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # best-effort logging
        pass


