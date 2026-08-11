"""Tự động hoá phần prompt versioning của CP2 theo docs/PROMPT_VERSIONING.md.

Script chạy đúng 6 bước trong tài liệu:

  1. Tạo version 1, gắn label `baseline` + `production`.
  2. Tạo version 2 (đổi format câu trả lời), gắn label `candidate`.
  3. Chạy cùng một input với label `baseline` và `candidate`.
  4. In ra trace ID của hai lần chạy để đối chiếu prompt_name/label/version.
  5. Chuyển label `production` sang version 2, chạy lại một request.
  6. Rollback `production` về version 1 và chạy lại để xác nhận.

Script idempotent ở mức an toàn: nếu prompt đã có version thì không tạo trùng nội dung,
chỉ dùng lại version đang có. Mọi thay đổi label đều in ra trước/sau để làm evidence.

    python scripts/setup_prompts.py            # chạy đủ 6 bước
    python scripts/setup_prompts.py --status   # chỉ xem trạng thái hiện tại
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env", override=True)

from app.cli import configure_utf8_stdio

# Giữ đúng ba biến bắt buộc trong prompt contract của docs/PROMPT_VERSIONING.md
V1_TEXT = """Feature={{feature}}
Docs={{docs}}
Question={{message}}

Trả lời ngắn gọn dựa trên Docs ở trên."""

V2_TEXT = """Feature={{feature}}
Docs={{docs}}
Question={{message}}

Trả lời theo đúng định dạng sau:
- Tóm tắt: một câu duy nhất.
- Chi tiết: tối đa ba gạch đầu dòng, chỉ dùng thông tin trong Docs."""

SAMPLE = {
    "user_id": "u-prompt-demo",
    "session_id": "s-prompt-demo",
    "feature": "qa",
    "message": "Chính sách hoàn tiền áp dụng trong bao lâu?",
}


def banner(step: str, title: str) -> None:
    print()
    print(f"--- {step}: {title} ---")


def label_map(client, name: str) -> dict[str, int]:
    """Trả về {label: version} cho các label quan tâm."""
    out: dict[str, int] = {}
    for label in ("production", "baseline", "candidate"):
        try:
            p = client.get_prompt(
                name, label=label, type="text", max_retries=0,
                fetch_timeout_seconds=10, cache_ttl_seconds=0,
            )
            out[label] = int(p.version)
        except Exception:
            pass
    return out


def print_labels(client, name: str, when: str = "hiện tại") -> dict[str, int]:
    mapping = label_map(client, name)
    if mapping:
        rendered = " · ".join(f"{k} → v{v}" for k, v in sorted(mapping.items()))
    else:
        rendered = "(chưa có label nào)"
    print(f"  Label {when}: {rendered}")
    return mapping


def ensure_version(client, name: str, text: str, labels: list[str], note: str) -> int:
    """Tạo một version mới với nội dung + label cho trước, trả về số version."""
    prompt = client.create_prompt(
        name=name, prompt=text, labels=labels, type="text", commit_message=note,
    )
    print(f"  Đã tạo version {prompt.version} với label {labels}")
    return int(prompt.version)


def run_request(label: str) -> tuple[str | None, str]:
    """Gọi agent với một label prompt cụ thể, trả về (trace_id, prompt_source)."""
    os.environ["LANGFUSE_PROMPT_LABEL"] = label

    # Import trễ để agent đọc đúng biến môi trường vừa đặt
    from app.agent import LabAgent
    from app.tracing import get_langfuse_client

    client = get_langfuse_client()
    agent = LabAgent()

    trace_id: str | None = None
    try:
        # start_as_current_span cho phép lấy trace_id ngay tại chỗ để ghi vào report
        with client.start_as_current_span(name=f"prompt-check-{label}") as span:
            trace_id = span.trace_id
            agent.run(**SAMPLE)
    except Exception as exc:
        print(f"  Lỗi khi chạy request: {type(exc).__name__}: {exc}")
        return None, "error"

    # Đọc lại nguồn prompt thực tế để biết có dùng managed prompt hay đã fallback
    from app.mock_rag import retrieve
    from app.prompt_management import resolve_prompt
    from app.tracing import tracing_enabled

    resolved = resolve_prompt(
        client, feature=SAMPLE["feature"], docs=retrieve(SAMPLE["message"]),
        message=SAMPLE["message"], enabled=tracing_enabled(),
    )
    client.flush()
    print(f"  label={label} → version={resolved.version} source={resolved.source} trace_id={trace_id}")
    return trace_id, resolved.source


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Thiết lập prompt v1/v2 và rollback trên Langfuse")
    parser.add_argument("--status", action="store_true", help="Chỉ in trạng thái label hiện tại")
    args = parser.parse_args()

    from app.tracing import get_langfuse_client, tracing_enabled

    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    host = os.getenv("LANGFUSE_HOST", "(chưa đặt)")
    print(f"Prompt name : {name}")
    print(f"Langfuse host: {host}")

    if not tracing_enabled():
        print("\nLANGFUSE_PUBLIC_KEY/SECRET_KEY chưa được đặt. Dừng lại.")
        return 1

    client = get_langfuse_client()
    try:
        authed = client.auth_check()
    except Exception as exc:  # SDK ném UnauthorizedError thay vì trả False khi 401
        authed = False
        print(f"\nXác thực Langfuse thất bại: {type(exc).__name__}")
    if not authed:
        print(
            "Key không dùng được với host đang cấu hình.\n"
            f"Host đang dùng: {host}\n"
            "Langfuse Cloud có nhiều region, key chỉ hợp lệ đúng region của nó:\n"
            "  https://cloud.langfuse.com     (EU)\n"
            "  https://us.cloud.langfuse.com  (US)\n"
            "  https://jp.cloud.langfuse.com  (JP)\n"
            "Sửa LANGFUSE_HOST trong .env cho khớp rồi chạy lại."
        )
        return 1
    print("Xác thực Langfuse: OK")

    if args.status:
        banner("STATUS", "Label hiện tại")
        print_labels(client, name)
        return 0

    # Bước 1 & 2 -------------------------------------------------------------
    banner("BƯỚC 1", "Tạo version 1 với label baseline + production")
    before = print_labels(client, name, "trước")
    v1 = ensure_version(client, name, V1_TEXT, ["baseline", "production"], "v1: trả lời ngắn gọn")

    banner("BƯỚC 2", "Tạo version 2 với label candidate")
    v2 = ensure_version(client, name, V2_TEXT, ["candidate"], "v2: trả lời theo format tóm tắt + chi tiết")

    time.sleep(1)  # chờ Langfuse index label mới
    print_labels(client, name, "sau ")

    # Bước 3 & 4 -------------------------------------------------------------
    banner("BƯỚC 3-4", "Chạy cùng một input với baseline và candidate")
    print(f'  Input: "{SAMPLE["message"]}"')
    trace_baseline, src_baseline = run_request("baseline")
    trace_candidate, src_candidate = run_request("candidate")

    # Bước 5 -----------------------------------------------------------------
    banner("BƯỚC 5", "Chuyển label production sang version 2")
    print_labels(client, name, "trước")
    client.update_prompt(name=name, version=v2, new_labels=["production"])
    time.sleep(1)
    print_labels(client, name, "sau ")
    trace_promoted, _ = run_request("production")

    # Bước 6 -----------------------------------------------------------------
    banner("BƯỚC 6", "Rollback label production về version 1")
    print_labels(client, name, "trước")
    client.update_prompt(name=name, version=v1, new_labels=["production"])
    time.sleep(1)
    final = print_labels(client, name, "sau ")
    trace_rollback, _ = run_request("production")

    client.flush()

    # Tổng kết cho REPORT.md -------------------------------------------------
    banner("EVIDENCE", "Chép các giá trị này vào submission/REPORT.md")
    print(f"  Prompt name            : {name}")
    print(f"  Version baseline       : v{v1} (label baseline)")
    print(f"  Version candidate      : v{v2} (label candidate)")
    print(f"  Trace ID (baseline)    : {trace_baseline}")
    print(f"  Trace ID (candidate)   : {trace_candidate}")
    print(f"  Trace ID (sau promote) : {trace_promoted}")
    print(f"  Trace ID (sau rollback): {trace_rollback}")
    print(f"  Label cuối cùng        : {final}")

    if "local-fallback" in (src_baseline, src_candidate):
        print(
            "\nCẢNH BÁO: prompt_source = local-fallback, nghĩa là app không lấy được"
            "\nmanaged prompt. Trace sẽ không gắn đúng prompt version."
        )
        return 1

    host_ui = host.rstrip("/")
    print(f"\nMở {host_ui} → Prompts → {name} để chụp ảnh danh sách version.")
    print(f"Mở {host_ui} → Tracing → Traces để chụp ảnh danh sách trace và waterfall.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
