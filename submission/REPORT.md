# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm:
- Repository URL:
- Commit SHA cuối:
- Thành viên và vai trò:

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: **Baseline (Checkpoint 0): 30/100**
  - Total log records analyzed: 21
  - Records with missing required fields: 20
  - Records with missing enrichment (context): 20
  - Unique correlation IDs found: 0
  - Potential PII leaks detected: 0
  - Scorecard: [FAILED] Missing required fields, [FAILED] Correlation ID propagation, [FAILED] Log enrichment, [PASSED] PII scrubbing
- Điểm `validate_logs.py`: **Sau Checkpoint 1: 100/100**
  - Total log records analyzed: 20
  - Records with missing required fields: 0
  - Records with missing enrichment (context): 0
  - Unique correlation IDs found: 10
  - Potential PII leaks detected: 0
  - Scorecard: [PASSED] Basic JSON schema, [PASSED] Correlation ID propagation, [PASSED] Log enrichment, [PASSED] PII scrubbing
- Tổng số traces: **14** trên Langfuse Cloud (region JP), tất cả đều có
  `user_id` (đã hash), `session_id`, tags `[lab, feature, model]` và metadata
  `prompt_name` / `prompt_label` / `prompt_version` / `prompt_source=langfuse`
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard: `submission/evidence/dashboard.html`

## 3. Logging và tracing

- Evidence correlation ID:
- Evidence PII redaction:
- Evidence trace waterfall:
- Giải thích một span đáng chú ý:

## 4. Prompt versioning

Thực hiện bằng `python scripts/setup_prompts.py` (tự động hoá đúng 6 bước trong
`docs/PROMPT_VERSIONING.md`). Xem trạng thái label bất kỳ lúc nào bằng
`python scripts/setup_prompts.py --status`.

- Prompt name: `day13-chat` (Langfuse Cloud region JP)
- Version/label baseline: **v1** — labels `baseline` + `production`
- Version/label candidate: **v2** — label `candidate` (đổi format: Tóm tắt + tối đa 3 gạch đầu dòng)
- Trace ID của mỗi version:

| Bước | Label dùng | Prompt version | Trace ID |
|---|---|---|---|
| Chạy với baseline | `baseline` | v1 | `5918fcab27fef672b99164264fbb8217` |
| Chạy với candidate | `candidate` | v2 | `e115ff2e810e493fc72c6566d90871b7` |
| Sau khi promote production → v2 | `production` | v2 | `0146d93b4f72de8877562a192212d664` |
| Sau khi rollback production → v1 | `production` | v1 | `9270c6d9217df55c7c3ca101f81e3e1f` |

  Hai trace đầu dùng **cùng một input** (`"Chính sách hoàn tiền áp dụng trong bao lâu?"`)
  nên khác biệt duy nhất giữa chúng là prompt version.

- Bằng chứng đổi label hoặc rollback — trạng thái label in ra trước/sau mỗi thao tác:

```text
BƯỚC 5 (promote):  trước: baseline→v1 · candidate→v2 · production→v1
                   sau  : baseline→v1 · candidate→v2 · production→v2
BƯỚC 6 (rollback): trước: baseline→v1 · candidate→v2 · production→v2
                   sau  : baseline→v1 · candidate→v2 · production→v1
```

  Hai trace `0146d93b...` (v2) và `9270c6d9...` (v1) chứng minh rollback có hiệu lực thật:
  cùng label `production` nhưng resolve ra hai version khác nhau trước và sau khi rollback.

- Tất cả trace đều có `prompt_source=langfuse` (không phải `local-fallback`), nghĩa là app
  lấy được managed prompt thật chứ không dùng template local.

## 5. Dashboard, SLO và alerts

- Kết quả `validate_dashboard.py`: **HỢP LỆ: 6/6 panel có trong dashboard contract.**
- Công cụ dashboard: script tự viết `scripts/build_dashboard.py` sinh HTML tĩnh từ
  `data/logs.jsonl` (đúng nguồn chuẩn trong `docs/DASHBOARD_SETUP.md`), không thêm
  dependency ngoài `requirements.txt`. Time range 60 phút, refresh 30s, mỗi panel in
  rõ đơn vị và threshold/SLO line.
- Evidence dashboard:
  - `submission/evidence/dashboard-baseline.png` — ảnh chụp trạng thái baseline,
    Latency P95 = 1213 ms, viền xanh ĐẠT.
  - `submission/evidence/dashboard-incident.png` — ảnh chụp khi bật incident
    `rag_slow`, Latency P95 = 3730 ms, viền đỏ VƯỢT NGƯỠNG.
  - `submission/evidence/dashboard.html` và `dashboard-incident-rag_slow.html` —
    file HTML gốc của hai ảnh trên.

  Tái tạo bất kỳ lúc nào bằng `python scripts/build_dashboard.py` (thêm `--open` để
  mở trình duyệt chụp ảnh màn hình).

- Evidence trace và prompt:
  - `submission/evidence/prompt-versions.png` — danh sách 2 version của `day13-chat`:
    v1 gắn `production` + `baseline`, v2 gắn `latest` + `candidate`.
  - `submission/evidence/traces-list.png` — danh sách trace trên Langfuse (Total 32
    observations, gồm cả `run` và `prompt-check-*`).
  - `submission/evidence/trace-waterfall-2.png` — waterfall của trace
    `prompt-check-candidate` (`e115ff2e810e493fc72c6566d90871b7`): span `run` 0.15s,
    $0.002427, metadata `prompt_source=langfuse`, `prompt_version=2`,
    `prompt_label=candidate`, kèm Session ID và User ID đã hash.
  - `submission/evidence/trace-waterfall-1.png` — ảnh danh sách trace lọc theo
    `prompt-check-*`, cho thấy đủ baseline/candidate/production.

### Giá trị đo được

Số liệu đúng với hai ảnh evidence đã nộp (mỗi cột là một lần chạy 40 request):

| Panel | Baseline | Khi bật `rag_slow` | Threshold |
|---|---|---|---|
| Latency P50 | 1137 ms | 1253 ms | — |
| Latency P95 | **1213 ms — ĐẠT** | **3730 ms — VƯỢT** | ≤ 3000 ms |
| Latency P99 | 1547 ms | 4088 ms | — |
| Traffic | 0.67 req/phút | 0.67 req/phút | ≥ 1 req/phút |
| Error rate | 0% — ĐẠT | 0% — ĐẠT | ≤ 2% |
| Cost | $0.0837 — ĐẠT | $0.0782 — ĐẠT | ≤ $2.5 |
| Tokens | 6718 — ĐẠT | 6269 — ĐẠT | ≤ 50000 |
| Quality | 0.88 — ĐẠT | 0.88 — ĐẠT | ≥ 0.75 |

Khác biệt quyết định nằm ở Latency: P95 tăng **1213 → 3730 ms** (gấp ~3x) và vượt
threshold 3000 ms, đúng điều kiện kích hoạt alert `high_latency_p95`. Các panel còn
lại gần như không đổi — cho thấy `rag_slow` chỉ ảnh hưởng độ trễ chứ không gây lỗi
hay đội chi phí, đúng bản chất của sự cố này.

Panel Traffic báo VƯỢT NGƯỠNG là đúng về mặt tính toán chứ không phải lỗi: contract
yêu cầu ≥ 1 request/phút, trong khi load test chỉ gửi 10–20 request rồi dừng nên chia
cho cửa sổ 60 phút ra 0.33. Đây là đặc thù của lab chạy theo đợt, không phải dịch vụ
chạy liên tục.

Kiểm tra runtime theo `DASHBOARD_SETUP.md`: bật `rag_slow` → chạy lại cùng input và
concurrency → P95 tăng từ 1213 ms lên 3730 ms và panel Latency đổi sang
VƯỢT NGƯỠNG đúng hướng → tắt incident → `/health` xác nhận cả ba flag về `false`.

### SLO đã chọn và lý do

Ghi trong `config/slo.yaml` kèm `note` cho từng SLI:

- `latency_p95_ms` = 3000 ms, target 99.5% — cách baseline (1213 ms) khoảng 2.5x nên
  không kêu vì nhiễu, nhưng incident `rag_slow` (3730 ms) thì vượt ngay.
- `error_rate_pct` = 2%, target 99.0% — baseline 0%, giữ error budget cho lỗi thoáng qua.
- `daily_cost_usd` = $2.5 — chi phí thực ≈ $0.002/request, tương đương ~1250 request/ngày.
- `quality_score_avg` = 0.75 — baseline 0.88, ngưỡng nằm dưới một khoảng an toàn.

### Alert rules và runbook

`config/alert_rules.yaml` có 3 alert, đều `type: symptom-based`, mỗi alert trỏ tới một
mục runbook trong `docs/alerts.md`:

| Alert | Severity | Điều kiện | Owner |
|---|---|---|---|
| `high_latency_p95` | warning | `latency_p95 > 3000ms` trong 5 phút | on-call-engineer |
| `elevated_error_rate` | critical | `error_rate_pct > 2` trong 3 phút | on-call-engineer |
| `cost_budget_exceeded` | warning | `daily_cost_usd > 2.5` | team-lead |

`docs/alerts.md` điền đủ cho cả 3 alert: tên, severity, SLI/SLO liên quan, điều kiện và
thời gian duy trì, ảnh hưởng tới người dùng, **ba bước kiểm tra đầu tiên**, mitigation
tạm thời và owner.

Ngưỡng `elevated_error_rate` đặt là 2% (không phải 5% như ví dụ trong tài liệu) để khớp
đúng objective của `error_rate_pct` trong `config/slo.yaml` — alert kêu đúng lúc bắt đầu
tiêu hao error budget.

### Câu hỏi phản biện — vì sao alert nên dựa trên triệu chứng?

Cách triển khai thay đổi liên tục, còn triệu chứng người dùng thì không. Alert gắn vào
tên hàm hay component nội bộ sẽ hỏng theo hai chiều: khi refactor đổi tên, alert im lặng
dù người dùng vẫn chờ lâu hoặc gặp lỗi; ngược lại một component chậm nhưng đã được cache
hoặc retry che đi sẽ tạo cảnh báo giả, khiến on-call mất phản xạ với alert thật. Alert
theo triệu chứng (`latency_p95`, `error_rate_pct`, `daily_cost_usd`) bắt được mọi nguyên
nhân dẫn tới cùng một hậu quả, kể cả nguyên nhân chưa từng gặp. Việc định vị nguyên nhân
cụ thể thuộc về trace và log — chính là ba bước kiểm tra đầu tiên trong runbook.

## 6. Điều tra challenge

- Challenge ID:
- Triệu chứng từ metrics:
- Trace ID liên quan:
- Log line/correlation ID liên quan:
- Root cause:
- Fix action:
- Preventive measure:

## 7. Đóng góp cá nhân

Với mỗi thành viên, ghi rõ nhiệm vụ và link commit/PR tương ứng.

| Thành viên | Phần việc | Commit/PR | Điều đã học |
|---|---|---|---|
| | | | |
