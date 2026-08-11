import json
import os
import sys
from pathlib import Path

LOGS_PATH = Path(os.getenv("LOGS_PATH", "data/logs.jsonl"))

def detect_anomalies():
    """Custom Automation Script: Detects PII leaks and Latency SLO violations from data/logs.jsonl."""
    if not LOGS_PATH.exists():
        print(f"Log file {LOGS_PATH} not found.")
        sys.exit(1)

    total_logs = 0
    pii_leaks = 0
    slo_latency_violations = 0
    errors_found = 0
    max_latency = 0
    total_cost = 0.0

    with open(LOGS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue

            total_logs += 1
            latency = record.get("latency_ms", 0)
            cost = record.get("cost_usd", 0.0)
            total_cost += cost

            if latency > max_latency:
                max_latency = latency

            # Check SLO Latency violation (> 3000ms)
            if latency > 3000:
                slo_latency_violations += 1

            # Check error events
            if record.get("event") == "request_failed" or record.get("level") == "error":
                errors_found += 1

            # Check PII leaks in raw text
            text_payload = json.dumps(record, ensure_ascii=False)
            if "09" in text_payload or "03" in text_payload or "@" in text_payload:
                import re
                if re.search(r"\b(03|05|07|08|09)\d{8}\b", text_payload) or re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text_payload):
                    pii_leaks += 1

    print("==================================================")
    print("🤖 CUSTOM AUTOMATION: LOG ANOMALY DETECTION REPORT")
    print("==================================================")
    print(f"Total Logs Analyzed     : {total_logs}")
    print(f"PII Leaks Detected      : {pii_leaks} {'✅ (Clean)' if pii_leaks == 0 else '🚨 (Violation)'}")
    print(f"SLO Latency Violations  : {slo_latency_violations} (> 3000ms)")
    print(f"Errors Recorded         : {errors_found}")
    print(f"Max Latency Recorded    : {max_latency} ms")
    print(f"Total Accumulated Cost  : ${total_cost:.6f} USD")
    print("==================================================")
    return {
        "total_logs": total_logs,
        "pii_leaks": pii_leaks,
        "slo_latency_violations": slo_latency_violations,
        "errors": errors_found,
        "max_latency": max_latency,
        "total_cost": total_cost,
    }

if __name__ == "__main__":
    detect_anomalies()
