# CFO — Central Fulfilment Orchestration (MVP)

Lớp điều phối giao hàng đặt trên POS/WMS/ERP sẵn có: nhận đơn, kiểm tồn kho theo thời gian, công suất kho
và xe, đề xuất **3 phương án**, **dispatcher duyệt**, theo dõi thực thi, ETA, GPS (chỉ dispatcher) và báo trễ
(dispatcher gửi). Pilot Thụy Điển, dữ liệu giả lập. **Hệ thống đề xuất, con người quyết định.**

> Trạng thái: **khung dự án** — mọi file có docstring mô tả việc cần làm, hàm nghiệp vụ còn `NotImplementedError`/`TODO`.

## Tài liệu (nguồn sự thật, v1.2)
`docs/01`…`09` — thứ tự ưu tiên khi mâu thuẫn ở `docs/09_AI_Coding_Rules.md` mục 2.
Phân công nhóm: `docs/10_Team_Assignment.md`.

## Cấu trúc
```
backend/        FastAPI + SQLAlchemy 2 + Alembic; app/engine là hàm thuần
source_system/  Hệ thống nguồn giả lập (POS/WMS/ERP/fleet) + POS UI
frontend/       React + Vite + TS strict + Tailwind; driver PWA
tools/          gps_simulator.py, add_market.py, seed_all.sh
docs/           01..10
```

## Chạy local
```bash
cp .env.example .env  # điền bí mật, SEED_DEMO_PASSWORD, INTERNAL_TICK_KEY; không commit .env
docker compose up -d --build    # chỉ stack cơ bản, không bật cfo-worker
make migrate
make seed                       # generator demo có thể exit 2 (partial/blocked), không tính E2E PASS
# CHỈ SAU KHI migrate/seed dữ liệu market đã hoàn tất:
docker compose --profile demo-worker up -d --build cfo-worker
# web http://localhost:5173 · API http://localhost:8000/docs · Mailpit :8025 · POS :8100
```

`cfo-worker` ở Compose profile `demo-worker`, nên `docker compose up -d` mặc định
không chạy worker. APScheduler đọc danh sách market **một lần lúc khởi động**;
nếu bật trước seed sẽ thiếu `notify_outbox:SE`. Với demo Swedish sạch, hãy dùng
quy trình có guard `bash tools/demo_setup.sh` trong [DEMO_SETUP](docs/DEMO_SETUP.md),
rồi bật worker bằng lệnh `--profile demo-worker` trên **sau khi script hoàn tất**.
Không coi exit 2 của seed generator là kết quả thành công hoặc bật worker trước
khi dữ liệu market sẵn sàng. Không dùng worker với dữ liệu thật/production.

## Kiểm tra
```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app/engine && lint-imports
```
