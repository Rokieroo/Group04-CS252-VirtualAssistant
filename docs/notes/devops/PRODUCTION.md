# Server cho người dùng (production)

Runbook cho một server thật phục vụ người học (issue #18). Staging trên Render/Vercel vẫn theo [DEPLOYMENT.md](DEPLOYMENT.md); tài liệu này dành cho một máy chủ riêng (VPS hoặc máy của trường) chạy toàn bộ bằng Docker Compose.

| Thành phần | Ở đâu | Ghi chú |
|---|---|---|
| `db` | PostgreSQL 16, volume `pgdata` | Không mở cổng ra ngoài; chỉ mạng `internal` |
| `migrate` | chạy một lần mỗi lần `up` | `alembic upgrade head` bằng role `pathly_owner` |
| `api` | FastAPI, 2 worker uvicorn | Đăng nhập DB bằng `pathly_app` (chỉ đọc/ghi dòng), `RUN_MIGRATIONS=0` |
| `worker` | job nền (tìm nguồn, kiểm tra link) | Cùng role `pathly_app` |
| `web` | Caddy, cổng 80/443 | UI đã build + proxy `/api`, HTTPS tự động (Let's Encrypt) |
| `backup` | `pg_dump` mỗi 24 giờ | Giữ 7 bản trong `deploy/backups/` |

Mọi file nằm trong `deploy/` và `db/postgres/`.

## Vai trò trong database

| Role | Quyền | Ai dùng |
|---|---|---|
| `postgres` | superuser | Chỉ lần khởi tạo volume đầu tiên |
| `pathly_owner` | chủ schema, tạo/sửa bảng | `migrate`, `backup` |
| `pathly_app` | `SELECT/INSERT/UPDATE/DELETE` trên mọi bảng, không DDL | `api`, `worker` |

[`db/postgres/roles.sql`](../../../db/postgres/roles.sql) tạo hai role và database, thu hồi quyền `CREATE` trên schema `public`, và đặt `ALTER DEFAULT PRIVILEGES` để bảng do migration sau này tạo ra cũng tự cấp quyền cho `pathly_app`. Mật khẩu truyền qua biến của `psql`, không nằm trong file. Chạy lại an toàn.

Dùng với database có sẵn (Neon, Supabase, RDS…) thay vì container `db`:

```bash
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 \
  -v db_name=pathly -v owner_password="$OWNER_PW" -v app_password="$APP_PW" \
  -f db/postgres/roles.sql
```

Muốn xem SQL của migration trước khi chạy (cho người duyệt): `DATABASE_URL=postgresql+psycopg://... alembic upgrade head --sql > migration.sql`.

## Cài lần đầu

Yêu cầu: Linux có Docker 24+ và Docker Compose v2, tên miền trỏ về IP server, cổng 80 và 443 mở.

```bash
git clone https://github.com/Rokieroo/Group04-CS252-VirtualAssistant.git pathly
cd pathly
cp deploy/env.production.example deploy/.env
# Điền DOMAIN và ba mật khẩu (openssl rand -hex 24 cho mỗi cái)
nano deploy/.env
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```

Thiếu một biến bắt buộc thì `docker compose` dừng ngay và báo tên biến. Lần đầu Caddy cần khoảng một phút để lấy chứng chỉ HTTPS.

Kiểm tra:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env ps
curl -fsS https://$DOMAIN/api/v1/health
python scripts/smoke_server.py https://$DOMAIN   # tạo 1 user thử, đi hết syllabus → graph
```

`smoke_server.py` đăng ký một tài khoản `smoke-…@example.com`, tải syllabus CSC10014, dựng roadmap, đọc graph, lưu layout và thử một cạnh tạo cycle (phải bị từ chối 409). Mọi bước đều ghi dữ liệu, nên chạy qua được nghĩa là role `pathly_app` có đủ quyền.

## Cập nhật phiên bản

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```

`migrate` chạy trước, `api` chỉ khởi động khi migration thành công. Nếu migration lỗi, API cũ vẫn chạy; xem `docker compose ... logs migrate`.

## Backup và khôi phục

Backup tự động nằm ở `deploy/backups/pathly-<thời điểm UTC>.dump` (định dạng custom của `pg_dump`). Nên chép thư mục này sang máy khác hằng ngày.

Khôi phục vào database mới để kiểm tra:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec db \
  createdb -U postgres -O pathly_owner pathly_restore
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
  pg_restore -U postgres -d pathly_restore --no-owner < deploy/backups/<file>.dump
```

Khôi phục đè lên database đang chạy: dừng `api`, `worker`; `dropdb`/`createdb` database `pathly` với owner `pathly_owner`; `pg_restore` như trên; chạy lại `psql -f db/postgres/roles.sql` để cấp lại quyền cho `pathly_app`; `up -d`.

Đã thử: backup 4 lần với `BACKUP_KEEP=2` chỉ giữ 2 bản mới nhất; khôi phục bản mới nhất vào database rỗng cho đủ dữ liệu.

## Xoay mật khẩu

1. Đổi giá trị trong `deploy/.env`.
2. `docker compose ... exec db psql -U postgres -c "ALTER ROLE pathly_app PASSWORD '<mới>'"` (tương tự cho `pathly_owner`).
3. `docker compose ... up -d` để `api`, `worker`, `backup` nhận mật khẩu mới.

## Xử lý sự cố

| Dấu hiệu | Kiểm tra |
|---|---|
| `api` không healthy | `logs api`; thường do sai `PATHLY_APP_PASSWORD` hoặc `migrate` chưa xong |
| `permission denied for table …` | Bảng tạo bằng role khác `pathly_owner`; chạy lại `roles.sql` |
| HTTPS lỗi | Tên miền chưa trỏ đúng IP, hoặc cổng 80 bị chặn (Let's Encrypt cần cổng 80) |
| Đầy đĩa | `du -sh deploy/backups`; giảm `BACKUP_KEEP` |

## Kiểm tra trong CI

Job `postgres-integration` trong `.github/workflows/ci.yml` chạy toàn bộ test trên PostgreSQL, rồi dựng đúng bố cục production: tạo role từ `roles.sql`, migrate bằng `pathly_owner`, chạy API bằng `pathly_app` với `RUN_MIGRATIONS=0`, chạy `smoke_server.py`, và xác nhận `pathly_app` không tạo được bảng.
