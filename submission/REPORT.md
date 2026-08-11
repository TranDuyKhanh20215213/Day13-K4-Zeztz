# Báo cáo Day 13 Observability

## 1. Thông tin nhóm

- Tên nhóm: Zeztz
- Repository URL: https://github.com/TranDuyKhanh20215213/Day13-K4-Zeztz
- Commit SHA cuối: `9dda847` *(commit ngay trước commit cập nhật dòng này; lấy SHA mới nhất bằng `git rev-parse HEAD`)*
- Thành viên và vai trò:

| Vai trò | Họ tên | MSSV | Phạm vi phụ trách |
|---|---|---|---|
| A — Logging & Middleware | Nguyễn Hùng Phát | 2A202601094 | CP1: middleware, correlation ID, gắn metadata vào log |
| B — Security & Compliance | Trần Duy Khánh | 2A202601696 | CP1: bật processor che PII, cấu hình regex, nâng cấp che PII toàn cục |
| C — Metrics & Alerting | Lê Nhật Hoàng | 2A202601128 | CP2: tích hợp Langfuse, đo `error_rate_pct`, viết SLO, alert rules và runbook |
| D — QA & Incident Analyst | Phạm Nguyễn Khánh Minh | 2A202602040 | Chạy load test sinh dữ liệu, thiết kế Dashboard Spec, chủ trì điều tra Challenge (CP3), viết `REPORT.md` |

## 2. Kết quả kỹ thuật

- Điểm `validate_logs.py`: **Baseline (Checkpoint 0): 30/100**
  - Total log records analyzed: 21
  - Records with missing required fields: 20
  - Records with missing enrichment (context): 20
  - Unique correlation IDs found: 0
  - Potential PII leaks detected: 0
  - Scorecard: [FAILED] Missing required fields, [FAILED] Correlation ID propagation, [FAILED] Log enrichment, [PASSED] PII scrubbing
- Điểm `validate_logs.py`: **Sau Checkpoint 1: 100/100**
  (ảnh: `submission/evidence/validate-logs-100.png`)
  - Total log records analyzed: 91
  - Records with missing required fields: 0
  - Records with missing enrichment (context): 0
  - Unique correlation IDs found: 42
  - Potential PII leaks detected: 0
  - Scorecard: [PASSED] Basic JSON schema, [PASSED] Correlation ID propagation, [PASSED] Log enrichment, [PASSED] PII scrubbing
- Tổng số traces: **14** trên Langfuse Cloud (region JP), tất cả đều có
  `user_id` (đã hash), `session_id`, tags `[lab, feature, model]` và metadata
  `prompt_name` / `prompt_label` / `prompt_version` / `prompt_source=langfuse`
- Số PII leak còn lại: 0
- Link/đường dẫn dashboard: `submission/evidence/dashboard.html`

## 3. Logging và tracing

### Evidence correlation ID

Mỗi request nhận một correlation ID ở middleware ([`app/middleware.py`](../app/middleware.py)),
bind vào `structlog.contextvars` nên mọi log line phát sinh trong request đó đều mang
cùng ID mà không phải truyền tay qua từng hàm. ID cũng trả về client qua header
`x-request-id`.

Hai log line của cùng một request (`req-508f481a`, lấy từ
`data/logs-challenge-incident.jsonl`) — nối được từ lúc nhận tới lúc trả lời:

```json
{"event": "request_received", "correlation_id": "req-508f481a", "user_id_hash": "0c04335fe098",
 "feature": "monitoring", "session_id": "k4-challenge-s05", "model": "claude-sonnet-4-5",
 "env": "dev", "service": "api", "level": "info", "ts": "2026-08-11T10:25:49.422430Z"}
{"event": "response_sent", "correlation_id": "req-508f481a", "latency_ms": 2651,
 "tokens_in": 45, "tokens_out": 81, "cost_usd": 0.00135, "quality_score": 0.8,
 "user_id_hash": "0c04335fe098", "feature": "monitoring", "session_id": "k4-challenge-s05",
 "model": "claude-sonnet-4-5", "level": "info", "ts": "2026-08-11T10:25:52.082973Z"}
```

Kết quả `validate_logs.py`: **42 unique correlation ID / 91 log record**, 0 record thiếu
trường bắt buộc, 0 record thiếu metadata enrichment.

Evidence: `submission/evidence/logs-correlation-id.png` — ảnh chụp 4 log line cuối, thấy
rõ `req-0953f0f7` và `req-71170b4a` mỗi ID xuất hiện ở **cả** `request_received` và
`response_sent` của cùng request.

### Evidence PII redaction

Processor `scrub_event` trong [`app/logging_config.py`](../app/logging_config.py) quét
**đệ quy** toàn bộ `event_dict` (kể cả payload lồng nhau, list, tuple) chứ không chỉ
một vài field cố định, nên không còn phụ thuộc vào việc nhớ liệt kê đúng field khi thêm
log mới. Giới hạn của cách này: nó vẫn dựa trên regex, nên chỉ che được các dạng PII đã
được định nghĩa (email, số điện thoại VN, số thẻ) — dạng PII mới cần bổ sung pattern.

Hai log line thật, input có PII nhưng log đã che:

```json
{"event": "request_received", "correlation_id": "req-7997ea07", "feature": "qa",
 "payload": {"message_preview": "What is your refund policy? My email is [REDACTED_EMAIL]"},
 "user_id_hash": "2055254ee30a", "session_id": "s01", "env": "dev",
 "model": "claude-sonnet-4-5", "level": "info", "ts": "2026-08-11T10:50:43.516923Z"}
{"event": "request_received", "correlation_id": "req-85113fd4", "feature": "qa",
 "payload": {"message_preview": "Here is my phone [REDACTED_PHONE_VN], what should be logged?"},
 "user_id_hash": "64f6ec689229", "session_id": "s05", "env": "dev",
 "model": "claude-sonnet-4-5", "level": "info", "ts": "2026-08-11T10:50:44.883501Z"}
```

Hai dòng này có thật trong `data/logs.jsonl` đã nộp và trùng với ảnh
`logs-pii-redacted.png`, tra lại được bằng:
`Select-String -Path data\logs.jsonl -Pattern 'req-7997ea07'`

Ngoài ra `user_id` không bao giờ vào log ở dạng gốc — luôn là `user_id_hash`
(ví dụ `2055254ee30a`). `validate_logs.py` báo **0 PII leak**.

Evidence:
- `submission/evidence/logs-pii-redacted.png` và `logs-pii-redacted-2.png` — lọc
  `data/logs.jsonl` theo `REDACTED`, thấy đủ ba loại: `[REDACTED_EMAIL]`,
  `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]`.
- `submission/evidence/validate-logs-100.png` — kết quả cuối của `validate_logs.py`:
  91 log record, 42 correlation ID, **0 PII leak**, 4/4 PASSED, **100/100**.

Input gốc trong `data/sample_queries.jsonl` có PII thật (`student@vinuni.edu.vn`,
`0987654321`, `4111 1111 1111 1111`); sau khi qua processor, log chỉ còn placeholder.

### Evidence trace waterfall

`submission/evidence/trace-waterfall-2.png` — trace `e115ff2e810e493fc72c6566d90871b7`,
waterfall hiển thị span cha `prompt-check-candidate` chứa span `run` (0.15s, $0.002427),
panel Metadata bên phải hiện `prompt_source=langfuse`, `prompt_version=2`,
`prompt_label=candidate`, `prompt_name=day13-chat`, kèm Session ID và User ID đã hash.

### Giải thích một span đáng chú ý

Span đáng chú ý nhất là `run` của trace **`f8de5335b0ef4ad48652dfed8dc9b380`**
(session `k4-challenge-s05`, lúc điều tra challenge): **2.66 giây**, trong khi cùng
session đó ở lần chạy baseline chỉ **0.15 giây** — chậm gấp ~17 lần.

Điều làm span này có giá trị chẩn đoán không nằm ở việc nó chậm, mà ở **những gì không
đổi**: `tokens_in` = 45 (y hệt baseline), `tokens_out` = 81, `cost_usd` = $0.00135. Nếu
nguyên nhân là RAG trả về nhiều document hơn thì prompt phải dài ra và `tokens_in` phải
tăng; nếu nguyên nhân là LLM sinh câu trả lời dài hơn thì `tokens_out` và cost phải tăng.
Cả ba đều đứng yên, nên thời gian dôi ra không nằm ở khối lượng công việc mà ở một
khoảng **chờ** — và khoảng chờ đó xảy ra trước khi prompt được gửi đi, tức trong bước
`retrieve`. Chi tiết ở mục 6.

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
yêu cầu ≥ 1 request/phút, trong khi load test chỉ gửi 40 request rồi dừng nên chia
cho cửa sổ 60 phút ra 0.67. Đây là đặc thù của lab chạy theo đợt, không phải dịch vụ
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
- `latency_p95_ms_monitoring` = 2000 ms — **bổ sung sau CP3**. Feature `monitoring` có
  baseline riêng ~150 ms, nhanh hơn nhiều mặt bằng chung, nên phải có ngưỡng riêng thay vì
  dùng chung 3000 ms. Giá trị lấy theo `latency_threshold_ms` trong `config/challenge.json`.

### Alert rules và runbook

`config/alert_rules.yaml` có 4 alert, đều `type: symptom-based`, mỗi alert trỏ tới một
mục runbook trong `docs/alerts.md`:

| Alert | Severity | Điều kiện | Owner |
|---|---|---|---|
| `high_latency_p95` | warning | `latency_p95 > 3000ms` trong 5 phút | on-call-engineer |
| `elevated_error_rate` | critical | `error_rate_pct > 2` trong 3 phút | on-call-engineer |
| `cost_budget_exceeded` | warning | `daily_cost_usd > 2.5` | team-lead |
| `high_latency_p95_monitoring` | warning | `latency_p95` của feature `monitoring` > 2000ms trong 5 phút | on-call-engineer |

Ba alert đầu viết ở CP2. Alert thứ tư **bổ sung sau CP3**, vì challenge phơi ra rằng
ngưỡng chung 3000 ms bỏ lọt sự cố của feature vốn nhanh — chi tiết ở mục 6.

`docs/alerts.md` điền đủ cho cả 4 alert: tên, severity, SLI/SLO liên quan, điều kiện và
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

- **Challenge ID:** `day13-k4-observability-v1` (cohort K4, incident `rag_slow`,
  affected feature `monitoring`, `latency_threshold_ms` = 2000)

Quy trình chạy đúng theo README: chạy input chính thức **trước** khi bật incident để
lấy baseline, rồi bật incident và chạy lại **cùng 5 query đó** — nên khác biệt duy nhất
giữa hai lần là bản thân sự cố.

```bash
python scripts/load_test.py --challenge --concurrency 5   # baseline
python scripts/inject_incident.py                          # bật rag_slow
python scripts/load_test.py --challenge --concurrency 5   # incident
python scripts/analyze_incident.py \
    --logs data/logs-challenge-incident.jsonl \
    --baseline data/logs-challenge-baseline.jsonl
python scripts/inject_incident.py --disable
```

### Bước 1 — Triệu chứng từ metrics

| Chỉ số (feature `monitoring`) | Baseline | Khi có incident | Ngưỡng |
|---|---|---|---|
| Latency P50 | 150 ms | **2651 ms** | — |
| Latency P95 | 150 ms | **2651 ms** | 2000 ms |
| Request vượt ngưỡng | 0/5 | **5/5 (100%)** | — |
| Error rate | 0% | 0% | ≤ 2% |
| Cost trung bình | $0.0021 | $0.0021 | — |
| Quality | 0.84 | 0.84 | ≥ 0.75 |

P95 tăng **+2501 ms** và vượt threshold 2000 ms, trong khi **error rate vẫn 0%, cost và
quality không đổi**. Kết luận đầu tiên: đây là sự cố **độ trễ thuần tuý**, không phải lỗi
chức năng và không phải hồi quy chi phí. Điều đó thu hẹp phạm vi điều tra về "thời gian bị
tiêu ở đâu" thay vì "cái gì hỏng".

### Bước 2 — Dùng trace khoanh vùng span bất thường

Vì chạy cùng 5 query ở cả hai lần, Langfuse có **hai trace cho mỗi session** — so sánh
trực tiếp được:

| Session | Trace baseline | Latency | Trace incident | Latency |
|---|---|---|---|---|
| `k4-challenge-s05` | `ee33562437760f945296589e9d1037b4` | 0.15s | **`f8de5335b0ef4ad48652dfed8dc9b380`** | **2.66s** |
| `k4-challenge-s04` | `a38a133e45eef0f96e5499f7078df2d4` | 0.15s | `17bd1e7e5b781893293f734007a45baa` | 2.65s |
| `k4-challenge-s03` | `ef5f4fa8658db3d99680780e2f2dd7be` | 0.15s | `ea9a143923b04a488eccce4820f4946d` | 2.65s |
| `k4-challenge-s02` | `1a3fd7f4ece63f930209df1c330c6a15` | 0.15s | `9edc2862bd3f90e0bcb4a7ffac030f0f` | 2.65s |
| `k4-challenge-s01` | `373f95b3d2c1db7c60c948b18da44446` | 0.15s | `bbdaffae5728ffec860e4829ebdb63c0` | 2.65s |

Trace chậm nhất: **`f8de5335b0ef4ad48652dfed8dc9b380`**

Điểm mấu chốt: **cả 5 trace đều chậm đúng ~2.5s**, không phải phân tán ngẫu nhiên. Độ trễ
cố định như vậy loại trừ nguyên nhân tranh chấp tài nguyên hay nghẽn mạng (những thứ này
gây dao động), và chỉ tới một khoảng chờ cố định nằm trong đường xử lý. Trong span `run`,
thời gian dồn vào bước `retrieve` (RAG) chứ không phải `generate` (LLM) — vì `generate`
vẫn sinh ra đúng lượng token như baseline.

### Bước 3 — Dùng log chứng minh root cause

Log line của request chậm nhất (`correlation_id=req-508f481a`, session `k4-challenge-s05`):

```json
{"event": "request_received", "correlation_id": "req-508f481a", "user_id_hash": "0c04335fe098",
 "feature": "monitoring", "session_id": "k4-challenge-s05", "model": "claude-sonnet-4-5",
 "level": "info", "ts": "2026-08-11T10:25:49.422430Z"}
{"event": "response_sent", "correlation_id": "req-508f481a", "latency_ms": 2651,
 "tokens_in": 45, "tokens_out": 81, "cost_usd": 0.00135, "quality_score": 0.8,
 "user_id_hash": "0c04335fe098", "feature": "monitoring", "session_id": "k4-challenge-s05",
 "model": "claude-sonnet-4-5", "level": "info", "ts": "2026-08-11T10:25:52.082973Z"}
```

Hai bằng chứng loại trừ trong chính log này:

1. **`tokens_in` = 45**, phân bố toàn bộ 10 request là `{44, 45, 46}` — không đổi so với
   baseline. Nếu RAG trả về nhiều document hơn thì prompt phải dài ra và `tokens_in` phải
   tăng. Nó không tăng ⇒ độ trễ **không** đến từ khối lượng dữ liệu.
2. **`cost_usd` và `tokens_out` không đổi** ⇒ LLM làm đúng lượng việc như cũ ⇒ độ trễ
   **không** nằm ở bước sinh câu trả lời.

Hai khoảng `ts` cách nhau 2.66s trong khi phần sinh token không đổi ⇒ thời gian bị tiêu
**trước** khi gọi LLM, tức ở bước retrieve.

- **Root cause:** bước RAG `retrieve()` bị chèn một khoảng chờ cố định ~2.5 giây
  (`time.sleep(2.5)` trong [`app/mock_rag.py`](../app/mock_rag.py) khi cờ incident
  `rag_slow` bật). Mỗi request đều phải chờ hết khoảng này trước khi prompt được gửi sang
  LLM, nên toàn bộ độ trễ dôi ra là hằng số chứ không tỉ lệ với kích thước dữ liệu.
  Con số đo được (+2501 ms) khớp với khoảng chờ này.

- **Fix action:** tắt cờ incident (`python scripts/inject_incident.py --disable`), xác nhận
  `/health` trả `rag_slow: false`. Trong hệ thống thật, việc tương đương là gỡ khoảng chờ
  nhân tạo / sửa truy vấn vector store bị chậm, và đặt **timeout cho bước retrieve** để một
  dependency chậm không kéo dài toàn bộ request. Sau khi tắt, P95 trở lại ~150 ms.

- **Preventive measure:**
  1. **Tách span cho từng thành phần** — gắn `@observe(as_type="span")` lên `retrieve` và
     `generate` (phần mở rộng trong tài liệu lab) để waterfall chỉ thẳng ra span nào chậm,
     không phải suy luận gián tiếp từ token như lần này.
  2. **Thêm SLO theo từng feature** — đây là lỗ hổng thật mà challenge này phơi ra:
     alert `high_latency_p95` hiện đặt ngưỡng 3000 ms (dựa trên baseline toàn hệ thống
     ~1200 ms), trong khi sự cố lần này chỉ đẩy P95 lên **2651 ms** — tức là
     **alert KHÔNG kêu** dù feature `monitoring` đã vượt threshold riêng 2000 ms của nó
     và người dùng của feature đó chờ chậm gấp 17 lần bình thường. Một ngưỡng chung cho
     mọi feature sẽ luôn bỏ lọt sự cố của feature vốn nhanh hơn mặt bằng.

     **Đã khắc phục ngay trong repo** (không chỉ ghi nhận): thêm SLI
     `latency_p95_ms_monitoring` (objective 2000 ms) vào
     [`config/slo.yaml`](../config/slo.yaml), alert `high_latency_p95_monitoring` vào
     [`config/alert_rules.yaml`](../config/alert_rules.yaml) và runbook Alert 4 tương
     ứng trong [`docs/alerts.md`](../docs/alerts.md). Với cấu hình mới, đúng sự cố này
     sẽ được phát hiện thay vì im lặng.
  3. **Timeout + fallback ở bước retrieve** — nếu vector store không trả lời trong N ms thì
     trả về kết quả rỗng và để LLM dùng fallback, đổi một câu trả lời kém hơn lấy việc giữ
     được độ trễ.
  4. **Theo dõi tỉ lệ latency/token** — lần này token không đổi mà latency tăng gấp 17 lần;
     một biểu đồ "ms mỗi token" sẽ phát hiện bất thường kiểu này ngay cả khi độ trễ tuyệt
     đối còn dưới ngưỡng.

- **Evidence:** `data/logs-challenge-baseline.jsonl` và `data/logs-challenge-incident.jsonl`
  (log thô hai lần chạy), cùng output của `scripts/analyze_incident.py` — script tự nối
  Metrics → Traces → Logs và in ra kết luận ở trên.

## 7. Đóng góp cá nhân

| Thành viên | MSSV | Phần việc | Commit | Điều đã học |
|---|---|---|---|---|
| Nguyễn Hùng Phát (A) | 2A202601094 | Logging & Middleware — CP1: `CorrelationIdMiddleware`, bind correlation ID vào `structlog.contextvars`, gắn metadata (`user_id_hash`, `session_id`, `feature`, `model`, `env`) vào log | `7e9dfee`, `1b35d5a` | Bind context ở middleware giúp mọi log line trong một request tự mang correlation ID, không phải truyền tay qua từng hàm — đó là điều kiện để nối được log với trace về sau |
| Trần Duy Khánh (B) | 2A202601696 | Security & Compliance — CP1: bật processor che PII, cấu hình regex cho email/số điện thoại VN/số thẻ, nâng `scrub_event` thành quét đệ quy toàn bộ event | `7980dc8`, `aff4f19` | Che PII theo danh sách field cố định luôn có kẽ hở; quét đệ quy cả payload lồng nhau mới đảm bảo không lọt. Hash `user_id` thay vì ghi thẳng để vẫn nhóm được request theo người dùng mà không lưu danh tính |
| Lê Nhật Hoàng (C) | 2A202601128 | Metrics & Alerting — CP2: tích hợp Langfuse (traces + prompt v1/v2 + rollback), viết SLO, 4 alert rules và runbook; `scripts/setup_prompts.py`, `scripts/build_dashboard.py` | `239ae95`, `098211b` | Alert phải dựa trên triệu chứng người dùng chứ không phải tên hàm nội bộ. Ngưỡng cũng phải chọn từ số đo thật: đặt quá sát baseline thì kêu vì nhiễu, quá xa thì bỏ lọt sự cố — đúng lỗi mà CP3 phơi ra |
| Phạm Nguyễn Khánh Minh (D) | 2A202602040 | QA & Incident Analyst — chạy load test sinh dữ liệu, thiết kế Dashboard Spec, chủ trì điều tra Challenge CP3, viết `REPORT.md`; `scripts/analyze_incident.py` | `a1759f9` | Chứng minh root cause không chỉ là chỉ ra cái gì thay đổi, mà cả cái gì **không** thay đổi: token và cost đứng yên trong khi latency tăng 17x giúp loại trừ hai giả thuyết (RAG trả nhiều document hơn, LLM sinh câu trả lời dài hơn) và thu hẹp về bước retrieve |

*Ghi chú:* commit `b95464c` và `4013676` là scaffold ban đầu của repo lab.

## 8. Ghi chú kỹ thuật thêm — LLM provider

Ngoài phạm vi bắt buộc của lab, app hỗ trợ chạy bằng **LLM thật của OpenAI** bên cạnh
LLM giả có sẵn. Chọn provider bằng biến môi trường:

```dotenv
LLM_PROVIDER=fake     # mặc định: chạy offline, miễn phí, kết quả tái lập
LLM_PROVIDER=openai   # gọi API thật
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

- [`app/openai_llm.py`](../app/openai_llm.py) — lớp `OpenAILLM` giữ đúng giao diện của
  `FakeLLM` nên [`app/agent.py`](../app/agent.py) không cần biết đang chạy provider nào.
  Token lấy từ `usage` thật trong response, không ước lượng.
- Cost tính theo đơn giá của từng model (`price_for`), không hardcode một mức giá.
- Cờ incident `cost_spike` vẫn tác động được khi dùng OpenAI: nhân `max_tokens` lên 4 để
  câu trả lời dài ra **thật**, thay vì nhân số token một cách giả tạo.
- Lỗi gọi API không làm sập request — trả về câu trả lời fallback và ghi
  `finish_reason=error:<Loại lỗi>` vào metadata của generation để log/trace vẫn truy được.

**Vì sao mặc định vẫn là `fake`:** đo thực tế cho thấy `gpt-4o-mini` mất **4371 ms** cho
một request, trong khi `FakeLLM` chỉ **150 ms** và ổn định. Bài lab dùng độ trễ ổn định đó
làm nền để đo tác động của incident `rag_slow` (+2.5s); nếu nền dao động 0.5–4s theo tải
mạng thì không còn phân biệt được "chậm do sự cố" hay "chậm do provider", và kết quả điều
tra CP3 sẽ không tái lập được khi chấm. Vì vậy `fake` là mặc định cho tests và bài chấm,
`openai` bật khi cần demo câu trả lời thật.

Đối chiếu chi phí thực đo cho cùng một câu hỏi:

| Provider | Model | Latency | tokens in/out | Cost |
|---|---|---|---|---|
| fake | claude-sonnet-4-5 (mô phỏng) | 150 ms | 45 / 81 | $0.001350 |
| openai | gpt-4o-mini | 4371 ms | 76 / 50 | $0.000041 |
