# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: Day 13 K4 Observability - Phạm Nguyễn Khánh Minh
- Repository URL: `https://github.com/pham-ng/Day13-K4-Observability-2A202602040-PhamNguyenKhanhMinh.git`
- Commit SHA cuối: `5ba64725aaf0b5b4d51c28772973373d98d0f149`
- Thành viên và vai trò: Phạm Nguyễn Khánh Minh (Nhóm trưởng & Phát triển Observability toàn trình)

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: 100/100 (Baseline CP0: 30/100 -> CP1: 100/100)
- Tổng số traces: 59+ traces trên Langfuse Cloud
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard: `submission/evidence/dashboard_runtime.png`

## 3. Logging và tracing

- Evidence correlation ID: `submission/evidence/trace_list.png`
- Evidence PII redaction: `submission/evidence/pii_redaction.png`
- Evidence trace waterfall: `submission/evidence/trace_waterfall.png`
- Giải thích một span đáng chú ý: Span `generate` đo thời gian gọi LLM (OpenAI `gpt-4o-mini`). Nó theo dõi thời gian thực thi (latency ~4.4s-7.2s), số lượng token tiêu thụ (`tokens_in`, `tokens_out`), và chi phí tính theo USD cho từng câu hỏi RAG.

## 4. Prompt versioning

- Prompt name: `day13-chat`
- Version/label baseline: Version 1 (label: `production`, `baseline`)
- Version/label candidate: Version 2 (label: `candidate`)
- Trace ID của mỗi version:
  - Version 1 (label production): `848503965b224114f43160bb1bc4a20e`
  - Version 2 (label candidate): `req-4ef17eb7`
- Bằng chứng đổi label hoặc rollback: `submission/evidence/prompt_rollback.png`

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: HỢP LỆ: 6/6 panel
- Evidence dashboard: `submission/evidence/dashboard_runtime.png`
- SLO đã chọn và lý do: Availability >= 98% và Latency P95 <= 3000ms nhằm đảm bảo hệ thống RAG phản hồi nhanh, duy trì trải nghiệm người dùng không bị gián đoạn.
- Alert rules và runbook: `config/alert_rules.yaml` & `docs/alerts.md`

## 6. Điều tra challenge

- Challenge ID: `day13-k4-observability-v1`
- Triệu chứng từ metrics: P95 Latency của feature `monitoring` tăng đột biến vượt xa ngưỡng 2000ms (thực tế ghi nhận latency P95 lên đến 6821ms - 38524ms), làm vi phạm cảnh báo SLO P95 <= 3000ms.
- Trace ID liên quan: `req-0ae31a8f` (Session: `k4-challenge-s05`, User: `k4-u05`)
- Log line/correlation ID liên quan: Correlation ID `req-0ae31a8f` | Dòng log thô từ `data/logs.jsonl`:
  ```json
  {
    "service": "api",
    "latency_ms": 7849,
    "tokens_in": 52,
    "tokens_out": 71,
    "cost_usd": 0.001221,
    "quality_score": 0.9,
    "payload": {
      "answer_preview": "To prove a slow span is the root cause of performance issues..."
    },
    "event": "response_sent",
    "feature": "monitoring",
    "model": "gpt-4o-mini",
    "correlation_id": "req-0ae31a8f",
    "session_id": "k4-challenge-s05",
    "user_id_hash": "0c04335fe098",
    "env": "dev",
    "ts": "2026-08-11T10:12:09.016216Z"
  }
  ```
- Root cause: Incident `rag_slow` bị kích hoạt làm bước truy vấn tri thức RAG `retrieve()` trong `app/mock_rag.py` bị hoãn (delay cưỡng bức) 2.5 giây thực tế cho các request thuộc feature `monitoring`.
- Fix action: Tắt sự cố bằng `python scripts/inject_incident.py --disable`, tối ưu hóa truy vấn vector DB index và bổ sung cơ chế timeout/cache cho hàm `retrieve()`.
- Preventive measure: Thiết lập Alert rule giám sát P95 Latency riêng cho sub-span `retrieve` (ngưỡng > 2000ms trong 3 phút), tích hợp circuit breaker và connection pooling để ngăn chặn hiện tượng treo cổ chai RAG.

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| Phạm Nguyễn Khánh Minh | Hoàn thiện Correlation ID Middleware, PII Redaction, Langfuse Tracing, Managed Prompt Versioning, Dashboard 6 Panel, Alert Rules/Runbooks và Điều tra Challenge Incident | Main branch | Học cách xây dựng hệ thống Observability toàn trình cho AI API (Metrics, Traces, Structured Logs), quản lý Prompt Managed & Rollback, và kỹ năng quy vết nguyên nhân gốc rễ (Root Cause Analysis) qua Trace ID & Correlation ID. |
