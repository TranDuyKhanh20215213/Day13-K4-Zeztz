"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

Sinh ra một file HTML tĩnh, tự chứa (không cần thư viện ngoài, không cần mạng) để
chụp evidence cho CP2. Nguồn dữ liệu là data/logs.jsonl đúng như DASHBOARD_SETUP.md
quy định; threshold và đơn vị đọc trực tiếp từ config/dashboard.yaml nên ảnh dashboard
luôn khớp với contract đã validate.

    python scripts/build_dashboard.py
    python scripts/build_dashboard.py --open
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

DEFAULT_LOGS = REPO_ROOT / "data" / "logs.jsonl"
DEFAULT_CONFIG = REPO_ROOT / "config" / "dashboard.yaml"
DEFAULT_OUT = REPO_ROOT / "submission" / "evidence" / "dashboard.html"


def load_records(path: Path, window_minutes: int) -> tuple[list[dict], datetime | None, datetime | None]:
    """Đọc log JSONL và giữ lại các bản ghi nằm trong cửa sổ thời gian."""
    if not path.exists():
        raise SystemExit(f"Không tìm thấy log: {path}. Chạy scripts/load_test.py trước.")

    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    def parsed_ts(record: dict) -> datetime | None:
        raw = record.get("ts")
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    stamped = [(parsed_ts(r), r) for r in records]
    times = [t for t, _ in stamped if t is not None]
    if not times:
        return records, None, None

    newest = max(times)
    cutoff = newest - timedelta(minutes=window_minutes)
    in_window = [r for t, r in stamped if t is not None and t >= cutoff]
    kept = [t for t in times if t >= cutoff]
    return in_window, (min(kept) if kept else None), newest


def _nums(records: list[dict], event: str, field: str) -> list[float]:
    out: list[float] = []
    for r in records:
        if r.get("event") != event:
            continue
        val = r.get(field)
        if isinstance(val, (int, float)):
            out.append(float(val))
    return out


def compute_panels(records: list[dict], window_minutes: int) -> dict[str, dict]:
    """Tính đúng 6 panel theo mapping trong DASHBOARD_SETUP.md."""
    latencies = [int(v) for v in _nums(records, "response_sent", "latency_ms")]
    costs = _nums(records, "response_sent", "cost_usd")
    tokens_in = _nums(records, "response_sent", "tokens_in")
    tokens_out = _nums(records, "response_sent", "tokens_out")
    quality = _nums(records, "response_sent", "quality_score")

    received = sum(1 for r in records if r.get("event") == "request_received")
    failed = [r for r in records if r.get("event") == "request_failed"]
    error_rate = (len(failed) / received * 100) if received else 0.0
    breakdown = Counter(r.get("error_type") or "unknown" for r in failed)

    # Cost theo phút cho sparkline
    per_minute: dict[str, float] = defaultdict(float)
    for r in records:
        if r.get("event") != "response_sent":
            continue
        raw, val = r.get("ts"), r.get("cost_usd")
        if isinstance(raw, str) and isinstance(val, (int, float)):
            per_minute[raw[:16]] += float(val)
    cost_series = [v for _, v in sorted(per_minute.items())]

    return {
        "latency": {
            "values": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "p99": percentile(latencies, 99),
            },
            "primary": percentile(latencies, 95),
            "series": [float(v) for v in latencies],
            "sample": len(latencies),
        },
        "traffic": {
            "values": {
                "count": received,
                "rate_per_minute": round(received / window_minutes, 2) if window_minutes else 0.0,
            },
            "primary": round(received / window_minutes, 2) if window_minutes else 0.0,
            "series": [],
            "sample": received,
        },
        "errors": {
            "values": {
                "error_rate_pct": round(error_rate, 2),
                "failed": len(failed),
                "received": received,
            },
            "primary": round(error_rate, 2),
            "breakdown": dict(breakdown),
            "series": [],
            "sample": received,
        },
        "cost": {
            "values": {
                "total": round(sum(costs), 6),
                "avg_per_request": round(sum(costs) / len(costs), 6) if costs else 0.0,
            },
            "primary": round(sum(costs), 6),
            "series": cost_series,
            "sample": len(costs),
        },
        "tokens": {
            "values": {
                "tokens_in": int(sum(tokens_in)),
                "tokens_out": int(sum(tokens_out)),
                "total": int(sum(tokens_in) + sum(tokens_out)),
            },
            "primary": int(sum(tokens_in) + sum(tokens_out)),
            "series": [],
            "sample": len(tokens_in),
        },
        "quality": {
            "values": {"mean": round(sum(quality) / len(quality), 4) if quality else 0.0},
            "primary": round(sum(quality) / len(quality), 4) if quality else 0.0,
            "series": quality,
            "sample": len(quality),
        },
    }


def threshold_state(primary: float, operator: str, value: float) -> tuple[bool, str]:
    ok = primary <= value if operator == "lte" else primary >= value
    symbol = "≤" if operator == "lte" else "≥"
    return ok, symbol


def _sparkline(series: list[float], ok: bool) -> str:
    """Vẽ sparkline bằng SVG inline, không cần thư viện chart."""
    if len(series) < 2:
        return ""
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0
    width, height = 260, 40
    step = width / (len(series) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - ((v - lo) / span) * (height - 6) - 3:.1f}"
        for i, v in enumerate(series)
    )
    stroke = "var(--ok)" if ok else "var(--bad)"
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="xu hướng {len(series)} điểm">'
        f'<polyline points="{points}" fill="none" stroke="{stroke}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def render_html(cfg: dict, panels: dict, meta: dict) -> str:
    dash = cfg["dashboard"]
    order = ["latency", "traffic", "errors", "cost", "tokens", "quality"]
    by_id = {p["id"]: p for p in dash["panels"]}

    cards = []
    for pid in order:
        spec, data = by_id[pid], panels[pid]
        th = spec["threshold"]
        ok, symbol = threshold_state(data["primary"], th["operator"], th["value"])
        badge = "ĐẠT" if ok else "VƯỢT NGƯỠNG"

        rows = "".join(
            f'<div class="row"><span>{html.escape(str(k))}</span>'
            f'<strong>{html.escape(f"{v:,.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}")}</strong></div>'
            for k, v in data["values"].items()
        )
        if pid == "errors" and data.get("breakdown"):
            rows += "".join(
                f'<div class="row sub"><span>{html.escape(str(k))}</span><strong>{v}</strong></div>'
                for k, v in data["breakdown"].items()
            )
        elif pid == "errors":
            rows += '<div class="row sub"><span>không có lỗi</span><strong>0</strong></div>'

        cards.append(f"""
      <section class="card {'ok' if ok else 'bad'}">
        <header>
          <h2>{html.escape(spec['title'])}</h2>
          <span class="badge">{badge}</span>
        </header>
        <p class="unit">đơn vị: {html.escape(str(spec['unit']))} · n={data['sample']}</p>
        <div class="rows">{rows}</div>
        {_sparkline(data['series'], ok)}
        <p class="threshold">Threshold / SLO line: {html.escape(th['aggregation'])} {symbol} {th['value']:,} {html.escape(str(spec['unit']))}</p>
      </section>""")

    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(dash['title'])}</title>
<style>
  :root {{
    --bg:#f6f7f9; --fg:#14171c; --muted:#5b6472; --card:#fff;
    --line:#dfe3e8; --ok:#1a7f4b; --bad:#c0392b;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#14171c; --fg:#e8eaed; --muted:#9aa3b0; --card:#1c2028;
             --line:#2c323c; --ok:#4ade80; --bad:#f87171; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:24px; background:var(--bg); color:var(--fg);
         font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .meta {{ color:var(--muted); font-size:13px; margin:0 0 20px; }}
  .meta code {{ background:var(--card); padding:1px 5px; border-radius:4px; }}
  .grid {{ display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); }}
  .card {{ background:var(--card); border:1px solid var(--line);
           border-left:4px solid var(--ok); border-radius:10px; padding:14px 16px; }}
  .card.bad {{ border-left-color:var(--bad); }}
  header {{ display:flex; align-items:center; justify-content:space-between; gap:8px; }}
  h2 {{ font-size:15px; margin:0; }}
  .badge {{ font-size:11px; font-weight:700; letter-spacing:.4px;
            color:var(--ok); border:1px solid var(--ok);
            padding:2px 7px; border-radius:99px; white-space:nowrap; }}
  .card.bad .badge {{ color:var(--bad); border-color:var(--bad); }}
  .unit {{ color:var(--muted); font-size:12px; margin:3px 0 10px; }}
  .rows {{ display:flex; flex-direction:column; gap:4px; }}
  .row {{ display:flex; justify-content:space-between; gap:12px;
          font-variant-numeric:tabular-nums; }}
  .row.sub {{ color:var(--muted); font-size:13px; padding-left:10px; }}
  .spark {{ width:100%; height:40px; margin-top:10px; display:block; }}
  .threshold {{ color:var(--muted); font-size:12px; margin:10px 0 0;
                padding-top:9px; border-top:1px dashed var(--line); }}
</style>
</head>
<body>
  <h1>{html.escape(dash['title'])}</h1>
  <p class="meta">
    Time range: <strong>{dash['time_range_minutes']} phút</strong> ·
    Refresh: {dash['refresh_seconds']}s ·
    Nguồn: <code>data/logs.jsonl</code> ·
    Cửa sổ dữ liệu: {html.escape(meta['window'])} ·
    {meta['records']} log records · Sinh lúc {html.escape(meta['generated'])}
  </p>
  <div class="grid">{''.join(cards)}</div>
</body>
</html>
"""


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Dựng dashboard HTML từ data/logs.jsonl")
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOGS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--open", action="store_true", help="Mở dashboard trong trình duyệt")
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    window = cfg["dashboard"]["time_range_minutes"]

    records, first, last = load_records(args.logs, window)
    if not records:
        raise SystemExit("Log rỗng trong cửa sổ thời gian. Chạy scripts/load_test.py trước.")

    panels = compute_panels(records, window)
    meta = {
        "records": len(records),
        "window": (
            f"{first:%H:%M:%S} → {last:%H:%M:%S} UTC" if first and last else "không xác định"
        ),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(cfg, panels, meta), encoding="utf-8")

    print(f"Dashboard: {args.out}")
    print(f"Log records trong cửa sổ {window} phút: {len(records)}")
    print()
    by_id = {p["id"]: p for p in cfg["dashboard"]["panels"]}
    for pid in ["latency", "traffic", "errors", "cost", "tokens", "quality"]:
        th = by_id[pid]["threshold"]
        ok, symbol = threshold_state(panels[pid]["primary"], th["operator"], th["value"])
        state = "ĐẠT " if ok else "VƯỢT"
        print(
            f"  [{state}] {by_id[pid]['title']:28} "
            f"{panels[pid]['primary']:>10,.2f} {by_id[pid]['unit']:<18} "
            f"(threshold {symbol} {th['value']:,})"
        )

    if args.open:
        webbrowser.open(args.out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
