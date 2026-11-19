# Log sự cố Docker / runbook demo — cần sửa (nguồn: E0, 2026-11-19)

Repo: `qaztyhn/cfo-itconsultant`, đo trên `main` tại `d57e9cbe270099e02f925efe3f2ad24c36d9c3ba`.
Môi trường gặp lỗi: macOS (Apple Silicon, aarch64), Docker Desktop, Docker Engine 29.9.2, Compose v5.6.1, shell zsh.
Báo cáo đầy đủ: `docs/reviews/E0_BASELINE_20261119.md` (PR #221). File này chỉ gom **các lỗi liên quan Docker và runbook dựng môi trường**. Lỗi nghiệp vụ (stock scope, POS UI, v.v.) nằm ở báo cáo, không thuộc phạm vi file này.

Quy ước: **Đã đo** = có bằng chứng chạy thật. **Giả thuyết** = chưa kiểm chứng, bạn tự xác nhận trước khi sửa.

---

## D-1 (E0-01) Postgres khởi động lần đầu thất bại, thoát mã 126

**Mức:** Trung bình. Có cách vượt qua (chạy lại `tools/demo_setup.sh`), nhưng người dựng mới sẽ gặp lỗi ngay ở lệnh đầu tiên.

**Tái hiện**
1. Clone mới trên macOS Docker Desktop, tạo `.env`, `COMPOSE_PROJECT_NAME=cfo-demo-e0`.
2. Chạy `bash tools/demo_setup.sh` lần đầu (volume `pgdata` trống).

**Kết quả kỳ vọng:** Postgres khởi động, chạy script init, tạo database `source_se`, healthy.

**Kết quả thực tế (đã đo)**
```
/usr/local/bin/docker-entrypoint.sh: running /docker-entrypoint-initdb.d/10-source-db.sh
/usr/local/bin/docker-entrypoint.sh: /docker-entrypoint-initdb.d/10-source-db.sh: /bin/sh: bad interpreter: Permission denied
```
- `initdb` và `CREATE DATABASE cfo` đã chạy xong trước đó; lỗi xảy ra đúng ở bước chạy script init.
- Setup in: `container cfo-demo-e0-postgres-1 exited (126)`; `docker inspect` → `exited exit=126`.
- Chạy lại `bash tools/demo_setup.sh` thì qua: volume đã có `PG_VERSION` nên entrypoint bỏ qua toàn bộ init, rồi `demo_setup.sh` tự chạy lại script init bằng `sh` (log in `CREATE DATABASE`) và `source_se` được tạo.

**Dữ kiện đã đo về file**
- `git ls-files -s tools/postgres/init-source-db.sh` → mode `100644` (không có bit thực thi trong git).
- Dòng đầu file: `#!/bin/sh` + `\n` (không CRLF). `file` → "POSIX shell script text executable, ASCII text".
- `ls -l` trên máy → `-rw-r--r--@` (dấu `@` = có extended attribute).
- Mount trong `docker-compose.yml` (service `postgres`): `./tools/postgres/init-source-db.sh:/docker-entrypoint-initdb.d/10-source-db.sh:ro`.

**Nguyên nhân gốc: chưa xác định.** Entrypoint của image `postgres` chạy trực tiếp các file `*.sh` nó thấy là thực thi được, và chỉ `source` các file không có quyền thực thi. Lỗi cho thấy entrypoint đã chạy trực tiếp nhưng `exec` `/bin/sh` bị từ chối, dù file trên host là `100644`.

**Giả thuyết (chưa kiểm chứng)**
- H1: bind mount của Docker Desktop (file sharing) hiện file với quyền thực thi trong container nhưng mount không cho `exec` (kiểu noexec), nên `#!/bin/sh` báo "Permission denied".
- H2: extended attribute `@` trên file (ví dụ `com.apple.provenance` hoặc `com.apple.quarantine`) liên quan. Kiểm tra: `xattr -l tools/postgres/init-source-db.sh`.
- H3: chỉ xảy ra với một số phiên bản Docker Desktop (29.x) hoặc kiểu file sharing nhất định.

**Hướng sửa gợi ý (chưa thử, bạn đánh giá)**
- A. Không phụ thuộc quyền thực thi của file bind mount: tạo image Postgres nhỏ `FROM postgres:16` và `COPY --chmod=0755 tools/postgres/init-source-db.sh /docker-entrypoint-initdb.d/10-source-db.sh`, hoặc dùng `build:` trong `docker-compose.yml`.
- B. Nếu muốn giữ mount: đảm bảo script chạy được cả khi entrypoint `source` nó (không dựa vào `exec` trực tiếp), và kiểm tra lại với bit thực thi (`git update-index --chmod=+x`) để biết có đổi hành vi không.
- C. Tối thiểu: ghi rõ trong `docs/DEMO_SETUP.md` rằng lần chạy đầu trên macOS có thể báo exit 126 và phải chạy lại `demo_setup.sh`. (Chỉ là tài liệu, không giải quyết lỗi.)

**Nghiệm thu**
- Trên macOS Docker Desktop, volume trống (`docker compose down -v` trong project `cfo-demo-*`, **chỉ project cách ly**), chạy `bash tools/demo_setup.sh` **một lần** là xong, không exit 126.
- `docker compose exec -T postgres psql -U cfo -d postgres -Atc "SELECT datname FROM pg_database;"` có cả `cfo` và `source_se`.
- Không làm đổi hành vi trên Linux/CI.

---

## D-2 (E0-02) `.env` mẫu trong runbook hỏng khi nạp bằng shell → `alembic` lỗi

**Mức:** Thấp (tài liệu), nhưng chặn bước migrate với người làm theo runbook.

**Tái hiện**
1. Tạo `.env` có dòng `CORS_ORIGINS=["http://localhost:5173"]` (đúng như ví dụ ở `docs/DEMO_SETUP.md` §2, không có nháy bao ngoài).
2. `set -a; . ./.env; set +a` rồi `bash tools/demo_setup.sh`.

**Kỳ vọng:** migrate chạy thành công.

**Thực tế (đã đo)**
```
pydantic_settings.exceptions.SettingsError: error parsing value for field "cors_origins" from source "EnvSettingsSource"
json.decoder.JSONDecodeError: Expecting value: line 1 column 2 (char 1)
```
(từ `alembic upgrade head`, `/srv/alembic/env.py` → `get_settings()`).

**Nguyên nhân (đã đo):** khi `source` `.env` bằng shell, dấu `"` bị bỏ, biến thành `[http://localhost:5173]` (không còn là JSON). Compose ưu tiên biến của shell nên `cfo-api` nhận giá trị hỏng.

**Cách vượt qua đã dùng:** `CORS_ORIGINS='["http://localhost:5173"]'` (nháy đơn ngoài). Sau khi nạp, `printf '%s\n' "$CORS_ORIGINS"` ra đúng `["http://localhost:5173"]`.

**Hướng sửa gợi ý**
- Sửa ví dụ ở `docs/DEMO_SETUP.md` §2 (và `.env.example` nếu có dòng này) dùng nháy đơn bọc ngoài.
- Cân nhắc: hoặc không hướng dẫn `set -a; . ./.env`, hoặc cho `tools/demo_setup.sh` tự chuẩn hóa/kiểm tra `CORS_ORIGINS` là JSON hợp lệ trước khi chạy migrate và báo lỗi rõ.

**Nghiệm thu:** làm đúng từng lệnh trong runbook trên máy trắng, không cần sửa tay `.env`, migrate chạy xong.

---

## D-3 (E0-06, một phần) Runbook không nói về trùng cổng và trùng tên project Compose

**Mức:** Thấp.

**Tái hiện:** máy đã có stack dev khác chạy từ cùng thư mục repo (project Compose mặc định tên theo thư mục, `cfo-itconsultant`) và đang giữ các cổng 5432, 8100, 8025, 1025. Chạy `demo_setup.sh` với `COMPOSE_PROJECT_NAME=cfo-demo-e0`.

**Thực tế (đã đo):**
```
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint cfo-demo-e0-postgres-1 (...): Bind for 127.0.0.1:5432 failed: port is already allocated
```
(`demo_setup.sh` dừng, `exit=` trống.) Lỗi chỉ ra theo từng cổng: Postgres, rồi Source, rồi Mailpit.

**Cách vượt qua đã dùng:** thêm vào `.env` các biến `docker-compose.yml` đã hỗ trợ: `POSTGRES_PORT=55432`, `SOURCE_PORT=18100`, `MAILPIT_HTTP_PORT=18025`, `MAILPIT_SMTP_PORT=11025` (còn `CFO_API_PORT`, `CFO_WEB_PORT` nếu cần). URL trong container vẫn dùng `postgres:5432`, không phải đổi `DATABASE_URL`. Khi chạy smoke phải truyền `--source-url http://127.0.0.1:18100/api/v1` (`tools/demo_smoke.py` có cờ này).

**Hướng sửa gợi ý**
- Thêm một mục "Trùng cổng" vào `docs/DEMO_SETUP.md`: liệt kê các biến `*_PORT`, cảnh báo project mặc định theo tên thư mục, và cách chạy smoke với cổng tùy biến.
- (Tùy chọn) `tools/demo_setup.sh` kiểm tra cổng trống trước khi `up` và in danh sách cổng bị chiếm cùng biến cần đặt.

**Nghiệm thu:** người làm theo runbook khi trùng cổng biết ngay phải đặt biến nào; không cần đọc `docker-compose.yml`.

---

## Phạm vi và ràng buộc khi sửa

- Làm trên nhánh `chore/...` và mở PR có review, theo `AGENTS.md`. Không push thẳng `main`.
- Không đổi các chốt an toàn của `tools/demo_setup.sh` (môi trường cách ly, `DEMO_DISPOSABLE`, không ghi vào dữ liệu thật). Chỉ dùng `docker compose down -v` trong project `cfo-demo-*`.
- Không commit `.env`, log, đường dẫn tuyệt đối của máy cá nhân, hay bí mật.
- Mô tả PR cần ghi: máy đã kiểm (OS, kiến trúc, bản Docker), và nếu không kiểm được trên macOS thì ghi **NOT VERIFIED** cho phần đó.
- Ngoài phạm vi file này: E0-04 (stock scope), E0-03 (POS UI) và các lỗi giao diện; đã ghi ở báo cáo E0.