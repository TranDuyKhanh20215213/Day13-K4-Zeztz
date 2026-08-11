# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

Nguồn cấu hình: [`config/alert_rules.yaml`](../config/alert_rules.yaml). SLO tham chiếu: [`config/slo.yaml`](../config/slo.yaml).

Baseline đo được (10 request, không có incident): P95 ≈ 1087 ms, error rate 0%, cost ≈ $0.02, quality ≈ 0.88.

## Alert 1

- Tên: `high_latency_p95`
- Severity: warning
- SLI/SLO liên quan: `latency_p95_ms` — objective 3000 ms, target 99.5%
- Điều kiện và thời gian duy trì: `latency_p95 > 3000ms` duy trì liên tục 5 phút. Baseline ≈ 1087 ms nên ngưỡng này cách baseline ~2.8x, đủ để bỏ qua nhiễu ngắn hạn nhưng vẫn bắt được suy giảm thật.
- Ảnh hưởng tới người dùng: người dùng chờ quá 3 giây mỗi câu trả lời; ở mức nặng client có thể timeout và người dùng gửi lại request, làm tải tăng thêm.
- Ba bước kiểm tra đầu tiên:
  1. Mở `/metrics`, so sánh `latency_p50` với `latency_p95`. Nếu P50 vẫn bình thường mà chỉ P95 tăng thì vấn đề nằm ở một nhóm request đuôi, không phải toàn hệ thống.
  2. Mở Langfuse, lọc trace theo thời điểm alert và sắp xếp theo duration giảm dần. Xem waterfall của trace chậm nhất để biết span nào chiếm thời gian — `retrieve` (RAG) hay `generate` (LLM).
  3. Lấy `correlation_id` của trace chậm đó, tìm trong `data/logs.jsonl` để đọc `latency_ms`, `feature` và `model` của chính request đó, xác nhận nguyên nhân bằng log thay vì suy đoán.
- Mitigation tạm thời: giảm số document RAG trả về hoặc hạ `max_tokens` để rút ngắn thời gian sinh; nếu chỉ một `feature` bị ảnh hưởng thì tạm chuyển feature đó sang prompt ngắn hơn. Sau khi xử lý, kiểm tra `/health` xem có incident flag nào đang bật (`rag_slow`, `tool_fail`, `cost_spike`).
- Owner: on-call-engineer

## Alert 2

- Tên: `elevated_error_rate`
- Severity: critical
- SLI/SLO liên quan: `error_rate_pct` — objective 2%, target 99.0%
- Điều kiện và thời gian duy trì: `error_rate_pct > 2` duy trì liên tục 3 phút. Ngưỡng đặt đúng bằng objective của SLO nên alert kêu ngay khi bắt đầu tiêu hao error budget. Cửa sổ 3 phút ngắn hơn Alert 1 vì lỗi ảnh hưởng người dùng nặng hơn độ trễ.
- Ảnh hưởng tới người dùng: request thất bại, người dùng nhận HTTP 500 và không có câu trả lời nào.
- Ba bước kiểm tra đầu tiên:
  1. Mở `/metrics` và đọc `error_breakdown` để biết lỗi tập trung ở `error_type` nào — một loại lỗi chiếm đa số thường chỉ thẳng tới nguyên nhân.
  2. Lọc `data/logs.jsonl` theo `event == "request_failed"`, nhóm theo `feature` và `model` để xác định phạm vi: toàn hệ thống hay chỉ một feature.
  3. Lấy `correlation_id` của một request lỗi đại diện, mở trace tương ứng trên Langfuse và đọc `payload.detail` trong log để lấy thông báo lỗi gốc.
  4. Kiểm tra `/health` xem incident `tool_fail` có đang bật không.
- Mitigation tạm thời: nếu lỗi chỉ ở một feature thì tạm tắt feature đó; nếu do prompt mới thì rollback label `production` về version trước theo [PROMPT_VERSIONING.md](PROMPT_VERSIONING.md); nếu do dependency ngoài thì bật đường fallback local.
- Owner: on-call-engineer

## Alert 3

- Tên: `cost_budget_exceeded`
- Severity: warning
- SLI/SLO liên quan: `daily_cost_usd` — objective $2.5/ngày
- Điều kiện và thời gian duy trì: `daily_cost_usd > 2.5` tính trên cửa sổ 1 ngày, không cần thời gian duy trì vì đây là giá trị cộng dồn và không tự giảm.
- Ảnh hưởng tới người dùng: không ảnh hưởng trực tiếp tới chất lượng trả lời, nhưng vượt ngân sách có thể dẫn tới bị rate limit hoặc phải cắt dịch vụ vào cuối kỳ — đó mới là lúc người dùng chịu ảnh hưởng.
- Ba bước kiểm tra đầu tiên:
  1. So sánh `total_cost_usd` với `traffic` trên `/metrics`. Nếu cả hai cùng tăng thì là tăng trưởng lưu lượng bình thường; nếu `avg_cost_usd` mỗi request tăng thì là hồi quy về chi phí.
  2. Kiểm tra `tokens_in_total` và `tokens_out_total`. Token input tăng bất thường thường do RAG trả về quá nhiều document; token output tăng thường do prompt mới yêu cầu câu trả lời dài hơn.
  3. Đối chiếu thời điểm chi phí tăng với lần đổi `prompt_version`/`prompt_label` gần nhất trong metadata của trace, và kiểm tra incident `cost_spike` trên `/health`.
- Mitigation tạm thời: rollback prompt về version có chi phí thấp hơn, giảm số document RAG, hoặc đặt trần `max_tokens`. Nếu do lưu lượng tăng thật thì nâng ngân sách có chủ đích thay vì tắt alert.
- Owner: team-lead

## Vì sao alert dựa trên triệu chứng

Ba alert trên đều đo thứ người dùng cảm nhận được — chờ lâu, gặp lỗi, dịch vụ có nguy cơ bị cắt — chứ không đo tên hàm hay thành phần nội bộ (ví dụ `retrieve() chậm` hay `FakeLLM lỗi`).

Lý do: cách triển khai thay đổi liên tục, còn triệu chứng thì không. Nếu alert gắn với một tên hàm, khi refactor đổi tên hàm thì alert im lặng dù người dùng vẫn khổ; ngược lại alert có thể kêu inh ỏi khi một component chậm nhưng cache hoặc retry đã che hết, tạo cảnh báo giả và làm on-call mất phản xạ. Alert theo triệu chứng bắt đúng mọi nguyên nhân dẫn tới cùng một hậu quả, kể cả nguyên nhân chưa từng gặp — phần định vị nguyên nhân cụ thể là việc của trace và log trong ba bước kiểm tra ở trên.
