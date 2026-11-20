# T12 · Xác minh tài xế (DEC-R3-07)

## Chạy lại cho T27

Dùng một project E0-04 disposable với `APP_ENV=test`, `DEMO_DISPOSABLE=1`
và `DEMO_D7_FIXTURE_DIR=`. Chạy trước mốc tồn kho ngày 01/12/2026 theo
[runbook E0-04](E0_04_DEMO.md). Lệnh dưới publish fixture `t26-r3-v1`,
nạp hai feed qua HTTP và dừng trước khi Sales Sync.

```sh
python tools/e0_04_prepare.py --stop-before-sync
```

Nếu cần chạy riêng bước publish và nạp lại ở đồng hồ lập kế hoạch **01/12**,
từ thư mục gốc chạy:

```sh
docker compose -p cfo-demo-e004 exec -T -e APP_ENV=test -e DEMO_DISPOSABLE=1 source-se \
  python -m app.seed_t26 --driver-feed
docker compose -p cfo-demo-e004 exec -T cfo-api \
  python -m app.jobs.ingest --market SE --entity driver-availability
docker compose -p cfo-demo-e004 exec -T cfo-api \
  python -m app.jobs.ingest --market SE --entity driver-eligibility
```

Fixture tổng hợp cấp 16 khung (4 tài xế × 4 ngày, 01–04/12 theo Stockholm)
và 4 quyền lái theo xe. Hai lượt nạp giữ nguyên các khóa `(source, source_ref)`.
Đối chiếu `stg.sync_run` theo `entity` và `stg.sync_reject` theo `run_id`.
T12 dùng ngân sách ngày đã được Fleet xác minh và tính phút lái đi/về của các
chuyến đã cam kết. Khi recheck, phần đã giữ cho chính chuyến chỉ tính một lần.

Để chạy bước 8, dùng Source ref `SE-2026-000249` ở Sales Sync & Check,
lấy `order_id`/mã CFO từ kết quả, rồi duyệt qua E1 WMS mô phỏng. Sau đó
chuyển đồng hồ CFO và browser sang giờ xuất xe của plan đã duyệt trên ngày
**02/12, Europe/Stockholm**, ghi các mốc kho và cho tài xế được gán bấm
Dispatch. Bằng chứng gồm HTTP status, ID và trạng thái từ PostgreSQL.
Xem [quy trình T27](T27_INTEGRATED_E004.md).

## Phạm vi fixture T26

`python tools/e0_04_prepare.py --t26 --seed-report t26-seed.json` dùng cùng
hai feed cho bộ dữ liệu báo cáo. Trong lượt kiểm, bộ này cho Planning thành
công. Approve qua E1 dừng ở `RISK_DEPENDENCY_UNAVAILABLE` tại bước nạp lại
tồn kho WMS khi đã có đơn lịch sử đang hoạt động. Dùng project E0-04 ở trên
để chạy bước 8 của T27.

## Bằng chứng PostgreSQL 16 · 20/11/2026

- Checkout replay `2c47ffe4e48e9709aff5534a0f5342a440ed1a3c`
  có cùng Git tree `61bee1919e22c9d97859dd72d568ff2f7b05f0c7` với
  [commit code trên GitHub](https://github.com/qaztyhn/cfo-itconsultant/commit/2edec0fd96426c6dfe4a44d098aa462f952c5bef).
- Source `SE-2026-000249` → CFO `SE-2026-000001`. Database disposable trả
  `order_id=1`, `plan_id=1`, `trip_id=1`. Lấy lại ID khi seed môi trường khác.
- Kho STO, ngày plan **02/12/2026**, xuất xe lúc **06:41 +01:00** (Stockholm).
  Khung T12 **06:00–17:00**, dự kiến **38/540 phút lái**; cả hai feed mang
  nguồn `synthetic_demo`. Replay hai lượt nhận 16 khung và 4 quyền lái mỗi lượt.
- Sync, Planning, Approve, `START_PREP`, `GOODS_READY`, `LOADED` và
  `DISPATCHED` đều HTTP **200**. PostgreSQL có đơn `DISPATCHED`, plan
  `approved`, trip `on_road`, milestone `DISPATCHED` ID **4** và WMS
  intent `refreshed` với nguồn tồn kho `wms_synthetic`.
- GPS của chính chuyến trả HTTP **202** và ghi đúng một điểm trên DB demo
  có thông báo quyền riêng tư tổng hợp. Lượt replay dùng HTTP, với
  `DEMO_D7_FIXTURE_DIR` tắt từ lúc seed. Trong
  [lượt T27 trước đó](https://github.com/qaztyhn/cfo-itconsultant/pull/233),
  cùng Source ref bị HTTP **409** vì D7 `EVIDENCE_MISSING` ngày 02/12.
