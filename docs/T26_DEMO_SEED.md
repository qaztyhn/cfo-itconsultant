# T26 · Seed demo Round 3

Version `t26-r3-v1` · Market SE · `Europe/Stockholm` ·
`APP_NOW=2026-12-01T10:05:00+01:00` cho Sales, Source và lần duyệt đầu.
Dữ liệu hoàn toàn tổng hợp, chỉ dùng project disposable `cfo-demo-t26`.
Xem [fixture có version](../source_system/seed/se/t26.json) và
[task board T26/T27](TASK_BOARD_R3_E2E_DEMO.md#t26--seed-demo-r3--dev-2--m--cần-t09-t12-t15).

## Khởi tạo, kiểm tra và reset

Chuẩn bị Docker Compose, Python 3.12, `python-dotenv`, `sqlalchemy` và file
`.env` riêng theo [DEMO_SETUP.md](DEMO_SETUP.md). Đặt `APP_ENV=test`,
`DEMO_DISPOSABLE=1`, `SOURCE_SCHEMA=src_se`, `SOURCE_DB_NAME=source_se`;
Compose dùng PostgreSQL nội bộ với hai DB `cfo` và `source_se`. Phải chạy
trước ngày 01/12/2026 lúc **10:00 Stockholm**, là mốc stock `as_of`; scope
tồn kho phải có hiệu lực trước mốc này. Dùng cổng localhost khác nếu có demo
đang chạy. Tắt worker khi seed. Dùng cấu hình E1 WMS mô phỏng của T27 khi
chạy tới Approve.

```sh
python tools/e0_04_prepare.py --t26 --seed-report t26-seed.json
python tools/t26_verify.py t26-seed.json > t26-step-12b.json

# Tùy chọn cho QA: Sync + Check thật qua HTTP; reset trước khi trình bày.
python tools/t26_verify.py t26-seed.json --exercise-main > t26-acceptance.json

# Xóa riêng containers/volume của demo T26, rồi dựng lại từ đầu.
APP_ENV=test DEMO_DISPOSABLE=1 COMPOSE_PROJECT_NAME=cfo-demo-t26 \
  bash tools/demo_reset.sh --confirm-disposable-data-loss
python tools/e0_04_prepare.py --t26 --seed-report t26-seed-repeat.json
diff -u t26-seed.json t26-seed-repeat.json
```

Mỗi lượt bắt đầu với 6 Source refs đã submit, 6 đơn lịch sử CFO, 2 kho hoạt
động, 10 cửa hàng hoạt động, 8 dòng công suất ngày, 16 khung khả dụng tài xế,
4 cặp quyền lái theo xe, 3 Dispatcher trong vòng luân phiên và 12 dòng tồn kho hiệu lực. Bản ghi kho/cửa
hàng từ seed chuẩn ngoài phạm vi T26 được giữ ở trạng thái inactive.
Lệnh setup đọc giá trị scope, dữ liệu và route qua các cơ chế E0-04.
T26 kiểm tra Source ref và chuẩn bị tuyến fallback trước lần bấm Sync.
T26 gửi cả báo cáo kiểm tra read-only và thao tác `--exercise-main` qua API CFO thật.

## Kịch bản và mã dùng theo vai trò

| Ca | Mã và thao tác |
| --- | --- |
| Luồng chính | Sales `sales@cfo.demo`, **Sync & Check** → nhập Source `SE-2026-000249` → Sync → Check → một phương án đề xuất STO ngày **02/12**. Lấy `order_id` từ Sync rồi gọi `GET /api/v1/orders/{id}` hoặc tra `ops.customer_order` theo ID để lấy **mã CFO**. Hai lượt nghiệm thu trả `order_id=7`, mã CFO `SE-2026-000007`. Dùng mã tra được tại Mailpit, Kho và CS. |
| Kho và Driver đơn chính | Kho STO chọn **02/12**. T27 chuyển đồng hồ CFO và browser sang giờ xuất xe thật trong plan trước khi chạy các mốc kho/driver. T12 nạp khung ngày 02/12 và quyền lái từ Source. Xem [bàn giao Dispatch](T12_DRIVER_VERIFICATION.md). |
| Sales rank 2 (Malmö 000123) | Sync Source `SE-2026-000123`, giao **04/12** tại điểm giữa GBG/STO. Kỳ vọng rank 2 xuất hiện và Sales chọn bằng lý do đúng hợp đồng. Chạy lại bước 3 sau khi T12/T19 nối xong. |
| Thiếu hàng (Malmö 000137) | Sync Source `SE-2026-000137`, yêu cầu **02/12**. GBG có 42 bao keo, STO có 0, yêu cầu 160; lô xác nhận `IN-SE-88213` về **STO 03/12**, 200 bao. Kỳ vọng `NO_FEASIBLE_DATE` cho ngày yêu cầu. Lượt thật: GBG `STOCK_SHORT`, STO `DATE_AFTER_DEADLINE`, CFO `NO_FEASIBLE_DATE`. Tính lại ngày sớm nhất sau T10/T12. |
| Trạng thái đang giao (Malmö 000129) | CFO `SE-2026-900129`, STO, ST-001, `DISPATCHED`. Dùng cho bước 12b. Muốn chứng minh cập nhật vị trí hoặc ETA, chạy bằng chuyến thực của T27 sau T12–T17. |
| Phân quyền (Malmö 000131) | CFO `SE-2026-900131`, STO, ST-001, `APPROVED`. Dùng cho drill-down của owner ST-001 và STO. |
| Hai xe | Sync Source `SE-2026-000160`, giao **03/12**, GBG. 20 x 40 bao xi măng và 15 x 40 đơn vị gạch, tổng 26.000 kg / 44 m³. Kho GBG chuẩn bị `GBG-26-01` / `DEMO-DRIVER-4` (16 t, CE) và `GBG-18-01` / `DEMO-DRIVER-7` (10 t, C); khung 06:00–17:00, tối đa 540 phút lái/ngày, quyền tổng hợp theo từng xe. Sau T12/T15 và E1 WMS giả lập, Approve phải tạo đúng hai chuyến cùng một Dispatcher. |
| FAILED | CFO `SE-2026-900251`, GBG, ST-001, `FAILED`. Có để tra nhóm thất bại. Sau T12/T14/T15, chạy sự kiện FAILED trên một chuyến thật của ca hai xe và đối chiếu cảnh báo T07 cùng thao tác xử lý T18. |

Dispatcher luân phiên gồm `DEMO-DISPATCHER`, `DEMO-DISPATCHER-2`,
`DEMO-DISPATCHER-3`; ID ghi trong `t26-seed.json`. Bước duyệt dùng
ApprovalService hiện hành và E1 WMS giả lập. Các đơn lịch sử có trạng thái báo cáo
đã dựng sẵn; ca hai xe và chính không có trạng thái đã duyệt dựng sẵn.
Source publish fixture `t26-r3-v1` và CFO nạp hai feed T12 vào bảng T09 với nguồn `synthetic_demo`. Hai lệnh nạp lại nằm trong [bàn giao T12](T12_DRIVER_VERIFICATION.md).
Công suất seed `06:00–14:00`, 7 người, 7 giờ hữu ích mỗi người cho mỗi kho,
ngày 01–04/12. Roster tương thích E0-04 phủ GBG/STO đến 04/12 trước khi T10 dùng bảng công suất ngày.

### Bật E1 cho proposal rank 2 đã có

Trong checkout dùng để chạy stack T26 có T19, giữ trang Sales đang hiển thị
plan #7 `proposed` của Source `SE-2026-000123`. Chạy từ repo root
trong môi trường Python đã cài backend, Playwright và `python-dotenv`.
Trên PowerShell, thay dòng đặt `PYTHONPATH` bằng `$env:PYTHONPATH = ".;backend"`.

```sh
PYTHONPATH=.:backend python -m tools.t27_integrated_browser --prepare-wms \
  --project cfo-demo-t26 --source-ref SE-2026-000123 --plan-id 7 --rank 2
```

Helper đọc proposal và batch tồn kho đã được chấp nhận trong DB của project.
Nó dùng image API hiện có, giữ volume PostgreSQL và chỉ tạo lại `cfo-api`
để bật WMS tại `127.0.0.1:8188` bên trong container. Đồng hồ Planning
là `2026-12-01T10:05:00+01:00`. Trên trang Sales đang mở, chọn **Rank 2**,
nhập `other` và chọn **Approve rank 2**. Ghi HTTP của
`POST /api/v1/plans/7/approve` rồi đối chiếu DB.

```sql
SELECT p.id, p.rank, p.status AS plan_status, o.status AS order_status,
       o.approved_plan_id, d.actor_role, d.snapshot->>'rank' AS audit_rank,
       d.reason_code,
       (SELECT count(*) FROM ops.notification n
        WHERE n.order_id = o.id AND n.template = 'CONFIRMED') AS confirmed_count
FROM plan.fulfilment_plan p
JOIN ops.customer_order o ON o.id = p.order_id
LEFT JOIN audit.decision_log d
  ON d.order_id = o.id AND d.plan_id = p.id AND d.action = 'PLAN_APPROVED'
WHERE o.external_ref = 'SE-2026-000123' AND p.id = 7;
```

Kỳ vọng HTTP `200`, `approved`, `APPROVED`, `approved_plan_id=7`,
audit của `sales` có rank `2` và `reason_code=other`, cùng đúng một
`CONFIRMED`. Nếu HTTP báo `RESOURCE_CONFLICT` khi refresh WMS, kiểm tra
`stg.sync_run` và `stg.sync_reject` của lượt stock sync tương ứng.
PR #245 đã ghi nhận `RISK_DEPENDENCY_UNAVAILABLE` ở bước này khi stack có
dữ liệu báo cáo.

Replay bằng Chromium, PostgreSQL 16 và API chạy local với T19 + #245, sáu đơn
báo cáo và đồng hồ trên cũng gặp lỗi này. Simulator ACK bốn dòng của plan #7
tại STO; refresh từ chối cả 12 dòng tồn kho. Approve trả HTTP `409`, plan
vẫn `proposed`, đơn `PLANNED`, có 0 audit `PLAN_APPROVED` và 0
`CONFIRMED` cho đơn. Giữ container simulator khi intent còn `acked` để
bảo toàn ledger phục vụ retry.

## Bước 12b · số liệu cố định

Kỳ `from=2026-11-26&to=2026-12-01`, tính cả hai đầu theo Stockholm.
`owner@cfo.demo` xem toàn market; owner ST-001
`demo-st-001-mgr@cfo.demo` giới hạn ở ST-001; tài khoản
`wm.got@cfo.demo` và `demo-sto-w00@cfo.demo` là owner kho GBG và STO.
Các ID DB được ghi trực tiếp trong JSON khi seed. Đơn hủy `SE-2026-900252`
có `ORDER_CANCELLED` tại 10:05 ngày 01/12, trước duyệt, thuộc ST-001 và
không có kho. Mã `SE-2026-900250` đã giao và mang toàn bộ doanh thu ghi nhận.

Mỗi ô là **số đơn / giá trị đơn SEK**. Các cửa hàng ST-003–ST-010 có 0
ở cả năm nhóm. Các cột kho có áp `location_id`.

| Nhóm | Toàn market | ST-001 | ST-002 | GBG | STO |
| --- | ---: | ---: | ---: | ---: | ---: |
| `approved` | 2 / 707.00 | 1 / 101.00 | 1 / 606.00 | 1 / 606.00 | 1 / 101.00 |
| `in_transit` | 1 / 202.00 | 1 / 202.00 | 0 / 0.00 | 0 / 0.00 | 1 / 202.00 |
| `completed` | 1 / 303.00 | 1 / 303.00 | 0 / 0.00 | 0 / 0.00 | 1 / 303.00 |
| `failed` | 1 / 404.00 | 1 / 404.00 | 0 / 0.00 | 1 / 404.00 | 0 / 0.00 |
| `cancelled` | 1 / 505.00 | 1 / 505.00 | 0 / 0.00 | 0 / 0.00 | 0 / 0.00 |
| Tổng | 6 / 2,121.00 | 5 / 1,515.00 | 1 / 606.00 | 2 / 1,010.00 | 3 / 606.00 |
| `/revenue/summary.recognised` | **303.00** | **303.00** | 0.00 | 0.00 | **303.00** |

Đối chiếu từng `groups[].orders` với `/revenue/orders.total` theo cùng kỳ,
`view`, `location_id` và `status_group`. Giá trị đơn lấy từ các mục drill-down.
Bước 12b chạy trên `cfo-demo-t26`. Dùng `cfo-demo-e004` và fixture driver T12 chung cho replay Approve/Dispatch T27. Mốc chạy kho và tài xế lấy từ thời điểm xuất xe của plan đã duyệt.

## Kết quả nghiệm thu

- Hai lượt trên PostgreSQL 16, Source HTTP và CFO FastAPI thật. Lượt reset
  xóa và tạo lại cả hai DB disposable; so khớp các Source refs, CFO mã đơn,
  số dòng seed, ID địa điểm và kết quả API bước 12b. Trước Sync, Source có
  `SE-2026-000249` ở trạng thái submit và CFO có 0 dòng cho ref này.
- Chromium thực hiện Sales Sync → Check, HTTP 200 cả hai bước. PostgreSQL
  có `order_id=7`, `run_id=6`, `plan_id=6`, một phương án `proposed`.
  Cùng bộ dữ liệu hiển thị đủ năm thẻ, 303 SEK doanh thu và drill-down đơn
  hủy ST-001 có đúng một dòng. API verifier đối chiếu 60 drill-down
  (10 stores + 2 warehouses, mỗi nơi 5 nhóm), cả count, giá trị và mã đơn.
- PostgreSQL ghi `NO_FEASIBLE_DATE` cho 000123 và 000160 trước khi T12
  được nối. 000123 có `VEHICLE_SCOPE_UNKNOWN` và `OUTSIDE_DRIVER_SHIFT`;
  000160 có `VEHICLE_SCOPE_UNKNOWN` ở GBG và `NO_TRUCK_FIT` ở STO.
  Chạy lại rank 2 (T12/T19), Approve + hai chuyến cùng Dispatcher (T12/T15),
  và FAILED/incident trên chuyến thực (T07/T14/T18) trước khi chấm PASS.
- Các lệnh Docker Compose đã được kiểm tra cú pháp. Lượt thực chạy dùng
  tiến trình local vì runner không có Docker. E1/Mailpit và toàn bộ trình
  tự T27 vẫn cần chạy trên môi trường Compose của nhóm.
- `tools/t26_verify.py` ghi `git_sha`, `fixture_sha256`, kỳ, timezone,
  location IDs và kết quả so khớp. Manifest `t26-r3-v1` có SHA-256
  `290980af7346c903e8e5027053f1bceaf8e3c61d5665e8c98d9eb335b2f904f6`.

**Assumptions: reviewed — none.** Áp dụng US-INT-06 AC1, US-REV-02 AC1–AC7,
DEC-R3-06/07/10; không đổi DB/API, quy tắc duyệt hay dữ liệu sản xuất.
