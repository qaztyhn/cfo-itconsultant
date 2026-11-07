"""Dữ liệu mẫu cho test API đọc nhân sự/địa điểm/xe (06 mục 13.1). Giả lập, không PII thật.

Market 1 = SE (seed 0008), market 2 = ZZ (khác market). Hôm nay = 2026-11-04 (đồng hồ test cố định).
Địa điểm: 1 WH-1 (kho, SE), 2 ST-1 (cửa hàng, SE), 3 WH-2 (kho, SE), 4 ZZ-WH (kho, market ZZ),
5 OLD (kho đóng).
Nhân viên (market SE trừ khi ghi chú):
 1 Anna Admin (IT)           2 Dan Dispatcher        3 Wanda Warehouse (phân công WH-1)
 4 Will Worker (WH-1, operator) 5 Dora Driver (WH-1)   6 Sam Sales (ST-1)
 7 Wes Former (WH-1 đã kết thúc 2026-10-31, nay ở WH-2)   8 Fay Future (WH-1 từ 2026-12-01)
 9 Tom Terminated (WH-1)     10 Zed Zz (market ZZ, kho ZZ-WH)
Tài khoản (app_user.id = employee id): 1 admin, 2 dispatcher, 3 warehouse, 6 sales, 10 warehouse (ZZ);
11 = admin hệ thống (không gắn nhân viên); 12 = customer_service; 13 = viewer; 14 = driver (nhân viên 5).
"""


def _emp(
    market: int, no: str, first: str, last: str, pos: str, extra_cols: str = "", extra_vals: str = ""
) -> str:
    return (
        "INSERT INTO hr.employee (market_id, employee_no, first_name, last_name, position_code, "
        f"hire_date{extra_cols}) "
        f"VALUES ({market}, '{no}', '{first}', '{last}', '{pos}', '2025-01-01'{extra_vals})"
    )


def _assign(emp: int, loc: int, start: str, end: str | None = None) -> str:
    end_sql = f"'{end}'" if end else "NULL"
    return (
        "INSERT INTO hr.employee_assignment (employee_id, location_id, start_date, end_date) "
        f"VALUES ({emp}, {loc}, '{start}', {end_sql})"
    )


def _user(emp: int | None, email: str, roles: str, scopes: str = "{}") -> str:
    emp_sql = str(emp) if emp is not None else "NULL"
    return (
        "INSERT INTO ref.app_user (employee_id, email, password_hash, roles, kpi_scopes) "
        f"VALUES ({emp_sql}, '{email}', 'not-a-real-hash', '{roles}', '{scopes}')"
    )


SETUP: tuple[str, ...] = (
    "INSERT INTO ref.market (code, name, timezone, currency) VALUES ('ZZ', 'Other market', 'UTC', 'EUR')",
    "INSERT INTO ref.location (market_id, type, code, name, address, lat, lon, loading_cutoff_time) "
    "VALUES (1, 'warehouse', 'WH-1', 'Warehouse One', 'Dock 1', 59.32930, 18.06860, '15:00')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon) "
    "VALUES (1, 'store', 'ST-1', 'Store One', 59.4, 18.1)",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
    "VALUES (1, 'warehouse', 'WH-2', 'Warehouse Two', 57.7, 11.9, '14:30')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time) "
    "VALUES (2, 'warehouse', 'ZZ-WH', 'Other Warehouse', 50.0, 10.0, '15:00')",
    "INSERT INTO ref.location (market_id, type, code, name, lat, lon, loading_cutoff_time, is_active) "
    "VALUES (1, 'warehouse', 'OLD', 'Closed Warehouse', 55.6, 13.0, '15:00', false)",
    _emp(
        1,
        "SE-001",
        "Anna",
        "Admin",
        "IT_INTEGRATION",
        ", work_email, work_phone",
        ", 'anna@cfo.test', '+46000001'",
    ),
    _emp(1, "SE-002", "Dan", "Dispatcher", "DISPATCHER"),
    _emp(1, "SE-003", "Wanda", "Warehouse", "WAREHOUSE_MANAGER"),
    _emp(1, "SE-004", "Will", "Worker", "WAREHOUSE_OPERATOR"),
    _emp(1, "SE-005", "Dora", "Driver", "DRIVER", ", work_email", ", 'dora@cfo.test'"),
    _emp(1, "SE-006", "Sam", "Sales", "SALES_RETAIL"),
    _emp(1, "SE-007", "Wes", "Former", "WAREHOUSE_OPERATOR"),
    _emp(1, "SE-008", "Fay", "Future", "WAREHOUSE_OPERATOR"),
    _emp(
        1,
        "SE-009",
        "Tom",
        "Terminated",
        "WAREHOUSE_OPERATOR",
        ", status, end_date",
        ", 'terminated', '2026-10-01'",
    ),
    _emp(2, "ZZ-010", "Zed", "Zz", "WAREHOUSE_MANAGER"),
    _assign(1, 2, "2025-01-01"),  # admin gắn tạm ở cửa hàng
    _assign(2, 1, "2025-01-01"),
    _assign(3, 1, "2025-01-01"),
    _assign(4, 1, "2025-01-01"),
    _assign(5, 1, "2025-01-01"),
    _assign(6, 2, "2025-01-01"),
    _assign(7, 1, "2025-01-01", "2026-10-31"),
    _assign(7, 3, "2026-11-01"),
    _assign(8, 1, "2026-12-01"),
    _assign(9, 1, "2025-01-01"),
    _assign(10, 4, "2025-01-01"),
    "INSERT INTO hr.warehouse_staff (employee_id, role, counts_in_capacity) VALUES "
    "(3, 'manager', false), (4, 'operator', true), (7, 'operator', true), (8, 'operator', true)",
    "INSERT INTO hr.driver_staff (employee_id, home_warehouse_id, licence_class, licence_expires_on) "
    "VALUES (5, 1, 'CE', '2027-01-31')",
    "INSERT INTO hr.sales_staff (employee_id, role) VALUES (6, 'retail')",
    "INSERT INTO hr.dispatcher_staff (employee_id) VALUES (2)",
    _user(1, "admin@cfo.test", "{admin}"),
    _user(2, "dispatcher@cfo.test", "{dispatcher}", "{ops}"),
    _user(3, "wm@cfo.test", "{warehouse}", "{ops}"),
    _user(4, "worker-has-no-account@cfo.test", "{viewer}"),  # chỉ để giữ id = employee id
    _user(5, "driver-placeholder@cfo.test", "{viewer}"),
    _user(6, "sales@cfo.test", "{sales}"),
    _user(7, "p7@cfo.test", "{viewer}"),
    _user(8, "p8@cfo.test", "{viewer}"),
    _user(9, "p9@cfo.test", "{viewer}"),
    _user(10, "zz@cfo.test", "{warehouse}"),
    _user(None, "system-admin@cfo.test", "{admin}"),
    _user(None, "cs@cfo.test", "{customer_service}"),
    _user(None, "viewer@cfo.test", "{viewer}", "{revenue_all}"),
    "UPDATE ref.app_user SET roles = '{driver}' WHERE id = 5",
    # quản lý địa điểm: WH-1 chính = 3 (hiệu lực), phó cũ đã hết hạn, phó tương lai; WH-2 chính hết hạn
    "INSERT INTO hr.location_manager (location_id, employee_id, level, valid_from, valid_to) VALUES "
    "(1, 3, 'primary', '2025-01-01', NULL), (1, 7, 'deputy', '2025-01-01', '2026-10-31'), "
    "(1, 8, 'deputy', '2026-12-01', NULL), (3, 7, 'primary', '2025-01-01', '2026-11-03')",
    "UPDATE ref.location SET owner_employee_id = 3 WHERE id = 1",
)

ADMIN, DISPATCHER, WAREHOUSE, DRIVER, SALES, ZZ_WAREHOUSE, SYSTEM_ADMIN, CS, VIEWER = (
    1,
    2,
    3,
    5,
    6,
    10,
    11,
    12,
    13,
)
