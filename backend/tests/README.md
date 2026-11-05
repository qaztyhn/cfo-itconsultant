# Tests

Quy tắc: `docs/09_AI_Coding_Rules.md` mục 11. Đặt tên theo AC: `test_US_<EPIC>_<NN>_AC<k>_<mô_tả>`.

| Thư mục | Nội dung | Owner |
|---|---|---|
| `unit/` | Engine thuần, không DB; bảng test ở `08` mục 6.2; phủ ≥ 90% `app/engine` | Dev 1 |
| `integration/` | API + PostgreSQL thật (Docker): ingestion, giữ chỗ, EXCLUDE, khóa đồng thời (xe/SKU/ngày), đóng kế hoạch, POD nhiều lần, RBAC mọi hàng ma trận `06` mục 3 | Dev 1 + Dev 2 |
| `e2e/` | 16 kịch bản `08` mục 6.3 bằng Playwright trên Docker Compose | Dev 2 + Dev 3 |

Không skip/xóa test để CI xanh.
