"""Write the source OpenAPI artifact: `python -m app.openapi_export` (run from source_system/).

The artifact is only a baseline once a reviewer approves the diff. Routes that are not built yet are hidden
from the schema (they answer 501), so the baseline never documents a stub as if it were a working contract.
"""

from pathlib import Path

import yaml

from app.config import Settings
from app.main import create_app

HEADER = (
    "# Hợp đồng nguồn dùng chung mọi nước (06 mục 16; US-SRC-02). Sinh bằng `python -m app.openapi_export`\n"
    "# và được CI so sánh (tools/check_openapi.py). Chỉ gồm endpoint đã triển khai; endpoint chưa có: 501.\n"
)
TARGET = Path(__file__).resolve().parent.parent / "openapi.yaml"


def build() -> dict[str, object]:
    return create_app(Settings("postgresql+asyncpg://localhost/source", "src_se")).openapi()


def main() -> None:
    TARGET.write_text(HEADER + yaml.safe_dump(build(), sort_keys=True, allow_unicode=True), encoding="utf-8")


if __name__ == "__main__":
    main()
