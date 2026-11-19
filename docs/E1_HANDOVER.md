# Bàn giao E1 — Nối Approve với WMS giả lập (chưa hoàn tất)

**Nhánh:** `feat/e1-approve-wms-simulated` (từ `main`)
**Trạng thái:** DỪNG GIỮA CHỪNG. Chưa đạt tiêu chí nghiệm thu nào của E1 ở mức end-to-end.
**Người bàn giao:** Nguyễn Lưu Hương
**Ngày:** 19/11/2026

---

## 1. Mục tiêu và điểm dừng

Mục tiêu E1: đơn PLANNED có plan khả thi và hold còn hạn → Dispatcher bấm Approve → đơn APPROVED, có chuyến, có audit duyệt, và CFO đã cập nhật tồn kho sau lượt giữ hàng từ WMS giả lập.

**Đã làm được:** cơ chế bật/tắt an toàn, dựng yêu cầu giữ hàng, gọi WMS giả lập, ghi intent/ACK, tải và xác minh batch.

**Chưa làm:** nạp batch vào CFO, đánh dấu `refreshed`, sửa gate để xác minh liên kết batch, commit duyệt cuối, xử lý retry, tài liệu demo.

**Điểm chặn:** xem mục 5.

---

## 2. Những gì đã thay đổi

| File | Trạng thái | Nội dung |
|---|---|---|
| `backend/app/services/wms_mode.py` | mới (đã có trong zip) | Công tắc mô phỏng; mặc định tắt; ném 409 `PLAN_NOT_APPROVABLE` khi bật ở môi trường không cho phép |
| `backend/app/services/wms_request.py` | mới (đã có trong zip) | Dựng yêu cầu giữ hàng hoàn toàn từ dữ liệu server; SKU WMS lấy từ fixture |
| `backend/app/adapters/disposable_wms_client.py` | mới (đã có trong zip) | Client loopback tới WMS giả lập; đổi lỗi sang mã tĩnh |
| `backend/app/adapters/wms_batch_stock.py` | mới (đã có trong zip) | Đổi batch WMS sang snapshot tồn kho CFO; fail-closed |
| `backend/app/services/wms_reserve_phase.py` | mới (trong repo) | `reserve_simulated`: intent → gọi WMS (ngoài transaction) → ACK. `fetch_verified_batch`: tải batch, xác minh HMAC và chữ ký, dựng snapshot. **Chưa ghi DB tồn kho.** |
| `backend/app/services/approval_service.py` | sửa | Gọi `require_simulated_or_off()`; hàm `_reserve_before_approval` (chỉ khi `session is None`, có kiểm tra quyền Dispatcher và market); `approve()` gọi hàm này trước transaction duyệt |
| `backend/app/adapters/rest_adapter.py` | sửa nhỏ | Đổi tên biến vòng lặp `row` → `cancel_row` để sửa lỗi mypy có sẵn (không đổi logic) |
| `backend/app/core/config.py` | sửa | Thêm `synthetic_wms_url`, `synthetic_wms_api_key`, `synthetic_wms_shared_key` (mặc định `None`) |
| `.env.example` | sửa | Thêm biến WMS giả lập với giá trị rỗng |

**Commit đã tạo:** `918f61e` — "E1: nối công tắc WMS mô phỏng và bước giữ hàng vào approve (chưa hoàn tất)". Commit này **chưa** gồm: `fetch_verified_batch`, các import đã sửa trong `wms_reserve_phase.py`, và `SYNTHETIC_WMS_SHARED_KEY` trong `config.py`/`.env.example`. Các thay đổi này nằm trong working tree.

---

## 3. Kết quả kiểm tra đã quan sát (không suy diễn)

- `pytest tests/unit/test_wms_batch_stock.py`: **11 passed**.
- `ruff check` trên `wms_batch_stock.py`, `test_wms_batch_stock.py`, `approval_service.py`, `wms_reserve_phase.py`: **pass** (sau khi sửa import).
- `mypy app/adapters/wms_batch_stock.py`: **lỗi** trong `rest_adapter.py:307` trước khi sửa; sau khi đổi tên biến, chưa xác nhận lại bằng kết quả mypy trong phiên này.
- `mypy app/services/wms_reserve_phase.py`: không có lỗi trong file này; chỉ còn 11 lỗi có sẵn trong `app/adapters/disposable_wms_service.py`.
- `mypy app/services/approval_service.py`: **17 lỗi**, **giống hệt trên `main`** (đã so sánh bằng worktree). Lỗi có sẵn, không thuộc E1.

**Chưa chạy:** test tích hợp PostgreSQL; test `test_wms_mode.py`, `test_wms_request.py`, `test_disposable_wms_client.py`; `python tools/harness.py verify`; kiểm thử duyệt qua API; kiểm thử retry.

---

## 4. Quyết định thiết kế (đã ghi nhận)

- **Option A cho bằng chứng tồn kho:** WMS giả lập là nguồn tồn kho trong demo cách ly; batch có chứa `reservation_id` được nạp qua đường ghi tồn kho có kiểm tra scope hiện có; không đổi DDL/API. (Option B — Source publish batch có liên kết, đổi contract — **không** thuộc E1.)
- **Gọi WMS ở tầng `approve()`, không bên trong `_approve`:** `_approve` đang giữ khóa row trên order/plan, còn `begin_intent` khóa cùng order trong transaction riêng → nguy cơ treo/deadlock. Khi `session` được truyền từ ngoài, giữ hành vi fail-closed cũ.
- **Fail-closed hiện tại:** `inspect_wms_gate` vẫn trả `WMS_CFO_STOCK_BATCH_LINK_UNVERIFIED`. Đơn **không thể** chuyển APPROVED ở trạng thái code hiện tại. Đây là chủ đích.

---

## 5. Điểm chặn — cần owner quyết định

1. **Scope tồn kho đã duyệt chưa có trong môi trường demo.** `ingest_stock.apply` từ chối batch với `STOCK_SCOPE_NOT_CONFIGURED` nếu không có `stock_scope_version` còn hiệu lực. `docs/DEMO_SETUP.md` không seed scope này. Scope được duyệt theo `DEC-OWNER S1-S5` là quyết định của owner; tự seed một scope "đã duyệt" sẽ là tạo approval giả. **Cần owner quyết định** có cho phép scope demo-only, gắn nhãn synthetic, chỉ trong project `cfo-demo-*` dùng một lần hay không.

2. **Cổng D7 và cổng đặt hàng WMS (Dev 1).** `DEMO_SETUP.md` ghi rằng duyệt có thể vẫn trả 409 cho đến khi bằng chứng pháp lý D7 và cổng WMS được chứng minh. Tiêu chí "Dispatcher duyệt nhận HTTP 200" của E1 **có thể không đạt** chỉ bằng phần code E1. Cần Dev 1 xác nhận.

3. **Chưa có danh mục đơn vị dạng `SourceProduct`.** Luồng stock cần các dòng sản phẩm đủ trường (`sku`, `name`, `category`, `gtin`, `sale_unit`, `units_to_base`, `unit_price`, `weight_kg`, `volume_m3`, `updated_at`). Hiện chưa dựng từ fixture WMS giả lập.

---

## 6. Việc còn lại (sau khi owner quyết định điểm 5)

1. Nạp batch đã xác minh vào CFO qua `sync_entity(..., adapter=WmsBatchStockAdapter(...))`, dựng `SourceProduct` từ fixture.
2. Sau khi nạp thành công, gọi `mark_refreshed(...)` với `batch_id` và `inclusion_proven=True`.
3. Sửa `inspect_wms_gate`: thay vì luôn trả `WMS_CFO_STOCK_BATCH_LINK_UNVERIFIED`, kiểm tra `stock_write_run` có `status='accepted'` và `source_batch_id == intent.refreshed_batch_id`, cùng `scope_version_id` còn hiệu lực.
4. Hoàn tất giao dịch duyệt cuối; kiểm tra lại phiên bản đơn/plan và hạn hold dưới khóa hiện có; sinh chuyến; ghi audit `PLAN_APPROVED`.
5. Xử lý retry: cùng `Idempotency-Key` → trả cùng `trip_ids`; WMS đã giữ nhưng CFO chưa commit → tra trạng thái bằng khóa cũ.
6. Viết test PostgreSQL: duyệt thành công; gửi lại; thiếu/sai ACK; batch chưa phản ánh; production bật mô phỏng → 409.
7. Cập nhật `docs/DEMO_SETUP.md` (cấu hình, các bước chạy lại) và chạy `python tools/harness.py verify`.

---

## 7. Cách chạy lại trạng thái hiện tại

```bash
git checkout feat/e1-approve-wms-simulated
cd backend
python -m pytest tests/unit/test_wms_batch_stock.py -q   # kỳ vọng: 11 passed
ruff check app/services/wms_reserve_phase.py app/services/approval_service.py
```

Biến môi trường: giữ `WMS_RESERVATION_MODE=disabled` (mặc định). Không đặt khóa thật trong `.env.example` hoặc commit.

---

## 8. Bằng chứng còn thiếu (đánh dấu NOT VERIFIED)

- Duyệt qua UI với tài khoản Dispatcher: **NOT VERIFIED**
- Trip_ids, reservation_id, batch_id từ DB: **NOT VERIFIED**
- Idempotency/retry: **NOT VERIFIED**
- Test tích hợp PostgreSQL: **NOT VERIFIED**

Assumptions: đã review trong phiên làm việc; owner cần xác nhận các điểm mục 5.