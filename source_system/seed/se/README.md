# Seed nguồn Thụy Điển

Owner: Dev 2. Dữ liệu tổng hợp theo `08` §5.2/5.5 và ASM-009.

`python -m app.seed_reference` (sau `python -m app.init_db`) bổ sung 100 sản phẩm,
40 khách và 80 địa chỉ. Dùng DATABASE_URL/SOURCE_SCHEMA của nguồn; APP_NOW đặt đồng hồ demo.
Lệnh tương ứng: `make source-seed-reference` hoặc `make source-seed-reference-docker`.

Catalog nằm trong `catalog.py`, phân bổ N1–N6 là 25/20/20/8/15/12. Tên SKU, GTIN,
đơn vị, hệ số chuyển đổi, giá, khối lượng và thể tích được test đối chiếu với catalog CFO.
Nguồn không lưu trạng thái ánh xạ; ba SKU 448812/88412/449130 vẫn pending trong seed CFO.
Chạy lại chỉ thêm SKU thiếu, không ghi đè giá/tên hoặc timestamp đã được sửa.

Các ứng dụng đóng gói riêng, không import ứng dụng kia hoặc đọc dữ liệu CFO để ghi ngược
về nguồn. Việc đối chiếu fixture chỉ diễn ra trong test của repository.

Tồn kho, hàng nhập IN-SE-88213, lịch xe, giờ nhận hàng và các đơn kịch bản chưa được seed
bởi lệnh này. `backend/app/seed/generate_data.py` vẫn là entrypoint seed đầy đủ riêng;
thành công của seed tham chiếu không chứng minh hoàn thành M1 hoặc kết quả engine.
