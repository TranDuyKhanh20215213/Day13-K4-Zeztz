# Yêu cầu dashboard

Contract có thể kiểm tra bằng máy nằm tại `config/dashboard.yaml`. Hướng dẫn dựng và kiểm tra runtime nằm tại [DASHBOARD_SETUP.md](DASHBOARD_SETUP.md).

Dashboard chính cần đủ 6 nhóm thông tin:

1. Latency P50/P95/P99.
2. Traffic: request count hoặc QPS.
3. Error rate và breakdown theo loại lỗi.
4. Cost theo thời gian.
5. Tổng token input/output.
6. Quality proxy.

Tiêu chuẩn trình bày:

- Khoảng thời gian mặc định: 1 giờ.
- Tự refresh mỗi 15–30 giây nếu công cụ hỗ trợ.
- Có threshold hoặc SLO line.
- Ghi rõ đơn vị.
- Chỉ giữ 6–8 panel quan trọng ở lớp chính.
- Screenshot phải nhìn được tên panel và khoảng thời gian.

Kiểm tra contract trước khi chụp evidence:

```bash
python scripts/validate_dashboard.py
```

## Thiết kế đã chốt

Công cụ sử dụng: **Streamlit** đọc trực tiếp `data/logs.jsonl` (chạy `streamlit run scripts/dashboard_app.py`). `data/logs.jsonl` là nguồn chuẩn của cả 6 panel; Langfuse vẫn là nơi mở trace và prompt version để điều tra sâu, không phải nguồn của dashboard.

Cấu hình chung: time range mặc định **60 phút**, refresh **30 giây**, mọi panel đều vẽ threshold line theo giá trị trong `config/dashboard.yaml`.

| # | Panel | Đơn vị | Nguồn (event.field) | Phép tổng hợp | Threshold / SLO line |
|---|---|---|---|---|---|
| 1 | Latency percentiles | ms | `response_sent.latency_ms` | P50, P95, P99 | P95 ≤ 3000 ms |
| 2 | Request traffic | requests/phút | `request_received` | count, rate_per_minute | ≥ 1 req/phút |
| 3 | Error rate and breakdown | percent | `request_received`, `request_failed`, `error_type` | error_rate_pct, count_by_value | ≤ 2% |
| 4 | Cost over time | USD | `response_sent.cost_usd` | sum theo phút, total | tổng ≤ $2.5 |
| 5 | Input and output tokens | tokens | `response_sent.tokens_in`, `response_sent.tokens_out` | sum theo từng field | ≤ 50000 |
| 6 | Quality proxy | score 0–1 | `response_sent.quality_score` | mean | ≥ 0.75 |

Giá trị baseline đo được với 40 request, không bật incident:

| Panel | Baseline | Trạng thái so với threshold |
|---|---|---|
| Latency | P50 1137 ms · P95 1213 ms · P99 1547 ms | đạt (P95 cách ngưỡng ~2.5x) |
| Traffic | 40 request · 0.67 req/phút | dưới ngưỡng (xem ghi chú bên dưới) |
| Errors | 0% (`error_breakdown` rỗng) | đạt |
| Cost | tổng $0.0837 · trung bình $0.0021/request | đạt |
| Tokens | in 1420 · out 5298 · tổng 6718 | đạt |
| Quality | 0.88 | đạt |

Panel Traffic báo dưới ngưỡng là đúng về mặt tính toán: contract yêu cầu ≥ 1 request/phút
trong khi load test chỉ gửi 40 request rồi dừng, chia cho cửa sổ 60 phút ra 0.67. Đây là
đặc thù của lab chạy theo đợt, không phải dịch vụ chạy liên tục.

Threshold lấy đúng theo `config/dashboard.yaml` và khớp với `config/slo.yaml`; không chỉnh contract để ảnh dashboard đẹp hơn.
