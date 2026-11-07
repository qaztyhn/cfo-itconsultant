"""Đọc DDL `CREATE TABLE` trong docs/05 để test đối chiếu schema thật với tài liệu (không chép tay).

Chỉ lấy tên bảng và tên cột; kiểu/ràng buộc được test riêng bằng thao tác thật trên PostgreSQL.
"""

import re
from functools import lru_cache
from pathlib import Path

SPEC = Path(__file__).resolve().parents[3] / "docs" / "05_Database_Design.md"
COMMON_COLUMNS = frozenset({"created_at", "updated_at"})  # 05 mục 1, ASM-001
_TABLE_RE = re.compile(r"CREATE TABLE ([a-z_]+)\.([a-z_]+) \(")
_NOT_COLUMN = {"PRIMARY", "UNIQUE", "CONSTRAINT", "CHECK", "EXCLUDE", "FOREIGN"}


def _body(text: str, start: int) -> str:
    depth, i = 1, start
    while depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[start : i - 1]


def _top_level_items(body: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in body:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    items.append("".join(current))
    return [item.strip() for item in items if item.strip()]


@lru_cache
def spec_tables() -> dict[str, frozenset[str]]:
    """{'schema.table': {cột theo 05}} — chỉ CFO DB (bỏ bảng src_* của hệ thống nguồn)."""
    text = "\n".join(line.split("--", 1)[0] for line in SPEC.read_text(encoding="utf-8").splitlines())
    tables: dict[str, frozenset[str]] = {}
    for match in _TABLE_RE.finditer(text):
        items = _top_level_items(_body(text, match.end()))
        columns = {item.split()[0] for item in items if item.split()[0] not in _NOT_COLUMN}
        tables[f"{match.group(1)}.{match.group(2)}"] = frozenset(columns)
    return tables


def spec_tables_in(*schemas: str) -> dict[str, frozenset[str]]:
    return {name: cols for name, cols in spec_tables().items() if name.split(".")[0] in schemas}


# Bảng/cột 05 do migration 0009 thêm (Q12/Q12b/Q14) — test của migration trước đó so với spec "trước 0009".
TABLES_ADDED_IN_0009 = frozenset({"hr.employee_shift_schedule", "hr.driver_duty_log", "ops.order_routing"})
COLUMNS_ADDED_IN_0009 = {"ref.vehicle": frozenset({"max_permissible_mass_kg", "regulation_561_scope"})}


def spec_tables_before_0009(*schemas: str) -> dict[str, frozenset[str]]:
    """spec_tables_in(...) bỏ những gì 0009 thêm — dùng cho test chạy tới revision ≤ 0008."""
    return {
        name: cols - COLUMNS_ADDED_IN_0009.get(name, frozenset())
        for name, cols in spec_tables_in(*schemas).items()
        if name not in TABLES_ADDED_IN_0009
    }
