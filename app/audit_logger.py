import json
import os
import time
from pathlib import Path

AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "data/audit.jsonl"))

def log_audit_event(action: str, actor: str, details: dict) -> None:
    """Logs security and administrative audit events to data/audit.jsonl."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event_type": "AUDIT",
        "action": action,
        "actor": actor,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "details": details
    }
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
