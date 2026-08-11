# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: high_latency_p95
- Severity: warning
- SLI/SLO liên quan: latency_p95_ms (SLO: P95 <= 3000ms trong 99.5% thời gian)
- Điều kiện và thời gian duy trì: `latency_p95 > 3000ms` duy trì trong 5 phút
- Ảnh hưởng tới người dùng: Người dùng cảm thấy phản hồi chatbot bị chậm rõ rệt (UI giật lag/chờ lâu).
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra Dashboard Panel `Latency` để xác định xu hướng P95/P99 bắt đầu tăng từ thời điểm nào.
  2. Mở Langfuse UI, tìm các trace chậm trong khoảng thời gian đó, kiểm tra xem span nào tốn thời gian nhất (`run` vs `retrieve` vs `generate`).
  3. Tra cứu log trong `data/logs.jsonl` theo `correlation_id` của trace bị chậm để tìm nguyên nhân (ví dụ: `rag_slow` timeout hay LLM response chậm).
- Mitigation tạm thời: Tắt tính năng RAG hoặc tăng timeout, hoặc giảm tải hệ thống.
- Owner: on-call-engineer

## Alert 2

- Tên: elevated_error_rate
- Severity: critical
- SLI/SLO liên quan: error_rate_pct (SLO: error_rate <= 2% trong 99.0% thời gian)
- Điều kiện và thời gian duy trì: `error_rate_pct > 5%` duy trì trong 3 phút
- Ảnh hưởng tới người dùng: Người dùng nhận được câu trả lời lỗi 500 (HTTP 500 Internal Server Error) liên tục.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra Dashboard Panel `Errors` xem `error_rate_pct` hiện tại và `error_breakdown` theo `error_type` (ví dụ `RuntimeError`, `Vector store timeout`).
  2. Mở Langfuse UI lọc các trace có status/error_type thất bại để xem vị trí quăng exception.
  3. So khớp `correlation_id` trong log event `request_failed` để đọc đầy đủ stack trace và payload detail.
- Mitigation tạm thời: Chuyển hướng traffic sang fallback LLM/RAG node hoặc bật circuit breaker.
- Owner: on-call-engineer

## Alert 3

- Tên: cost_budget_exceeded
- Severity: warning
- SLI/SLO liên quan: daily_cost_usd (SLO: cost <= $2.5/ngày)
- Điều kiện và thời gian duy trì: `daily_cost_usd > $2.5`
- Ảnh hưởng tới người dùng: Không ảnh hưởng trực tiếp tới UI nhưng làm vượt ngân sách hoạt động của hệ thống AI.
- Ba bước kiểm tra đầu tiên:
  1. Kiểm tra Dashboard Panel `Cost` và `Tokens` để xác định loại token nào bị tăng đột biến (`tokens_in` hay `tokens_out`).
  2. Kiểm tra log `response_sent` để tìm các request có `cost_usd` hoặc `tokens_out` bất thường.
  3. Kiểm tra xem có hiện tượng loop prompt, prompt quá dài hoặc tấn công prompt injection không.
- Mitigation tạm thời: Áp dụng max_tokens cap cho LLM generation hoặc giới hạn số lượng request per user.
- Owner: team-lead
