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
cp .env.example .env   # điền bí mật và SEED_DEMO_PASSWORD; không commit .env
docker compose up -d && make migrate seed
# web http://localhost:5173 · API http://localhost:8000/docs · Mailpit :8025 · POS :8100
```

## Kiểm tra
```bash
cd backend && pip install -e ".[dev]" && pytest && ruff check . && mypy app/engine && lint-imports
```
