"""Engine lập kế hoạch — HÀM THUẦN (09 bất biến 6, 04 mục 6).

Cấm import sqlalchemy, httpx, requests, app.services/adapters/providers; cấm datetime.now(),
đọc env/file, ghi log, gọi mạng. Mọi dữ liệu và "bây giờ" truyền vào qua tham số.
Kiểm bằng import-linter (pyproject) và tests/unit/test_engine_purity.py. mypy --strict.
Phủ test ≥ 90% dòng. KHÔNG có thiết bị kho trong MVP (v1.1). v1.2: một đơn có thể nhiều xe cùng kho
(ít xe nhất), giờ công theo đơn vị cơ sở nhỏ nhất, không còn kết quả "manual".

Owner: Dev 1 (luồng A) — M4 (đường găng).
"""
