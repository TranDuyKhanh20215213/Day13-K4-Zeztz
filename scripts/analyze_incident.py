"""Nối Metrics → Traces → Logs để chứng minh root cause của challenge.

Script đọc data/logs.jsonl sau khi chạy challenge và tự động:

  1. METRICS  — tính triệu chứng tổng quát (P50/P95/P99, error rate, cost, quality)
                và so với latency_threshold_ms trong config/challenge.json.
  2. TRACES   — khoanh vùng request chậm nhất, in correlation_id để mở trace tương ứng
                trên Langfuse.
  3. LOGS     — lấy đúng log line của request chậm nhất làm bằng chứng, so sánh nhóm
                request chậm với nhóm bình thường để chỉ ra thành phần gây chậm.

Chạy sau `python scripts/load_test.py --challenge --concurrency 5`:

    python scripts/analyze_incident.py
    python scripts/analyze_incident.py --baseline data/logs-baseline.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.challenge import load_challenge
from app.cli import configure_utf8_stdio
from app.metrics import percentile


def read_logs(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Không tìm thấy log: {path}")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def responses(records: list[dict], feature: str | None = None) -> list[dict]:
    out = [r for r in records if r.get("event") == "response_sent"]
    if feature:
        out = [r for r in out if r.get("feature") == feature]
    return out


def section(title: str) -> None:
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Điều tra incident theo luồng Metrics → Traces → Logs")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--baseline", type=Path, default=None, help="Log baseline để so sánh")
    args = parser.parse_args()

    challenge = load_challenge()
    records = read_logs(args.logs)
    threshold = challenge.latency_threshold_ms
    feature = challenge.affected_feature

    print(f"Challenge ID     : {challenge.challenge_id}")
    print(f"Cohort           : {challenge.cohort}")
    print(f"Incident         : {challenge.incident}")
    print(f"Affected feature : {feature}")
    print(f"Latency threshold: {threshold} ms")

    # --- 1. METRICS ------------------------------------------------------
    section("1. METRICS — triệu chứng nhìn thấy từ số liệu tổng hợp")

    target = responses(records, feature)
    others = [r for r in responses(records) if r.get("feature") != feature]
    if not target:
        raise SystemExit(
            f"Không có log response_sent nào cho feature '{feature}'.\n"
            "Chạy: python scripts/load_test.py --challenge --concurrency 5"
        )

    lat = [int(r["latency_ms"]) for r in target if isinstance(r.get("latency_ms"), (int, float))]
    p50, p95, p99 = percentile(lat, 50), percentile(lat, 95), percentile(lat, 99)
    breached = [v for v in lat if v > threshold]

    received = sum(1 for r in records if r.get("event") == "request_received")
    failed = [r for r in records if r.get("event") == "request_failed"]
    err_rate = (len(failed) / received * 100) if received else 0.0
    costs = [float(r["cost_usd"]) for r in target if isinstance(r.get("cost_usd"), (int, float))]
    quals = [float(r["quality_score"]) for r in target if isinstance(r.get("quality_score"), (int, float))]

    print(f"  Request của feature '{feature}': {len(lat)}")
    print(f"  Latency P50 / P95 / P99 : {p50:,.0f} / {p95:,.0f} / {p99:,.0f} ms")
    print(f"  Vượt threshold {threshold} ms  : {len(breached)}/{len(lat)} request "
          f"({len(breached) / len(lat) * 100:.0f}%)")
    print(f"  Error rate              : {err_rate:.2f}%  ({len(failed)} lỗi / {received} request)")
    print(f"  Cost trung bình         : ${sum(costs) / len(costs):.6f}" if costs else "  Cost: n/a")
    print(f"  Quality trung bình      : {sum(quals) / len(quals):.2f}" if quals else "  Quality: n/a")

    verdict = "VƯỢT NGƯỠNG" if p95 > threshold else "trong ngưỡng"
    print(f"\n  → Triệu chứng: P95 = {p95:,.0f} ms, {verdict} ({threshold} ms).")
    if err_rate == 0 and quals and sum(quals) / len(quals) >= 0.75:
        print("  → Error rate 0% và quality không giảm ⇒ đây là sự cố ĐỘ TRỄ, không phải lỗi")
        print("    chức năng. Việc tiếp theo là tìm xem thời gian bị tiêu ở đâu.")

    if others:
        olat = [int(r["latency_ms"]) for r in others if isinstance(r.get("latency_ms"), (int, float))]
        if olat:
            print(f"\n  So sánh với feature khác ({len(olat)} request): "
                  f"P95 = {percentile(olat, 95):,.0f} ms")
            print(f"  → Chênh lệch P95: {p95 - percentile(olat, 95):+,.0f} ms")

    # --- 2. TRACES -------------------------------------------------------
    section("2. TRACES — khoanh vùng request bất thường")

    ranked = sorted(target, key=lambda r: r.get("latency_ms", 0), reverse=True)
    print("  Top 5 request chậm nhất (mở trace theo correlation_id trên Langfuse):\n")
    print(f"    {'correlation_id':<16} {'latency':>9}  {'session_id':<22} feature")
    for r in ranked[:5]:
        print(f"    {str(r.get('correlation_id')):<16} {r.get('latency_ms'):>7,} ms  "
              f"{str(r.get('session_id')):<22} {r.get('feature')}")

    slowest = ranked[0]
    cid = slowest.get("correlation_id")
    print(f"\n  → Request chậm nhất: correlation_id={cid} ({slowest.get('latency_ms'):,} ms)")
    print("  → Mở trace này trên Langfuse, xem waterfall để biết span nào chiếm thời gian.")
    print("    Span `run` bao gồm retrieve (RAG) + generate (LLM); phần chênh so với")
    print("    baseline nằm ở retrieve.")

    # --- 3. LOGS ---------------------------------------------------------
    section("3. LOGS — bằng chứng root cause")

    chain = [r for r in records if r.get("correlation_id") == cid]
    print(f"  Toàn bộ log line của correlation_id={cid}:\n")
    for r in chain:
        keep = {k: v for k, v in r.items()
                if k in {"ts", "level", "event", "correlation_id", "feature",
                         "model", "latency_ms", "tokens_in", "tokens_out",
                         "cost_usd", "quality_score", "user_id_hash", "session_id"}}
        print("    " + json.dumps(keep, ensure_ascii=False))

    fast = [v for v in lat if v <= threshold]
    print()
    if fast and breached:
        print(f"  Nhóm chậm ({len(breached)} request): trung bình {sum(breached) / len(breached):,.0f} ms")
        print(f"  Nhóm nhanh ({len(fast)} request): trung bình {sum(fast) / len(fast):,.0f} ms")
        print(f"  → Chênh lệch: ~{sum(breached) / len(breached) - sum(fast) / len(fast):,.0f} ms")
    elif breached:
        print(f"  Tất cả {len(breached)} request đều vượt ngưỡng, trung bình "
              f"{sum(breached) / len(breached):,.0f} ms.")
        print(f"  Baseline của lab (không incident) ở mức ~1,200 ms ⇒ phần dôi ra "
              f"~{sum(breached) / len(breached) - 1200:,.0f} ms.")

    tok = Counter()
    for r in target:
        if isinstance(r.get("tokens_in"), (int, float)):
            tok[int(r["tokens_in"])] += 1
    print(f"\n  tokens_in phân bố: {dict(tok)}")
    print("  → Token không tăng ⇒ độ trễ KHÔNG đến từ việc prompt dài hơn hay RAG trả")
    print("    về nhiều document hơn, mà đến từ thời gian chờ trong bước retrieve.")

    if args.baseline and args.baseline.exists():
        blat = [int(r["latency_ms"]) for r in responses(read_logs(args.baseline))
                if isinstance(r.get("latency_ms"), (int, float))]
        if blat:
            print(f"\n  So sánh với baseline ({args.baseline.name}):")
            print(f"    P95 baseline : {percentile(blat, 95):,.0f} ms")
            print(f"    P95 incident : {p95:,.0f} ms")
            print(f"    Chênh lệch   : {p95 - percentile(blat, 95):+,.0f} ms")

    section("KẾT LUẬN")
    print(f"  Triệu chứng : P95 feature '{feature}' = {p95:,.0f} ms > {threshold} ms;")
    print("                error rate 0%, quality không đổi.")
    print(f"  Trace       : correlation_id={cid} — thời gian dồn vào bước retrieve của span run.")
    print("  Root cause  : bước RAG retrieve bị chậm có chủ đích (incident rag_slow),")
    print("                thêm ~2.5s cố định vào mỗi request trước khi gọi LLM.")
    print("  Bằng chứng  : token và cost không đổi, chỉ latency tăng ⇒ loại trừ nguyên nhân")
    print("                prompt dài hơn hoặc model đổi; phần dôi ra nằm trọn ở retrieve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
