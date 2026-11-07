# Tasks for DevOps (Tuần 1: Git Workflow, CI, Docker Compose, Staging)

Tài liệu này mô tả chi tiết nhiệm vụ DevOps tuần 1 (Võ Thành Đạt, Lê Hồng Đăng, hai Developer của team): rào chắn cho quy trình Git, CI, môi trường chạy chung và staging tự deploy.

## 🎯 Sứ mệnh tuần 1

Để mọi người code an toàn và nhanh: **không ai push thẳng `main`**, mọi PR được kiểm tra tự động, cả team chạy cùng môi trường và mỗi lần merge thì staging tự cập nhật.

Dưới đây là các hạng mục công việc cần hoàn thiện:

- [X] **Task 1: Git workflow (#17, Võ Thành Đạt, 5 giờ, phần milestone xong sáng thứ Hai)**
  - **Milestone**: `Week 1` … `Week 6`; gán `Week 1` cho #5–#18.
  - **Branch protection**: PR bắt buộc, 1 approve, CI pass, cấm force push.
  - **CI**: lint, test, quét secret, kiểm tra benchmark, kiểm tra tên nhánh của PR.
  - **Hook**: 6/6 thành viên chạy `python dev.py devops install-hooks`.
- [X] **Task 2: Docker Compose + staging (#18, Lê Hồng Đăng, 10 giờ)**
  - **Local**: `docker compose up --build` chạy API + Postgres 16.
  - **Staging**: UI trên Vercel; API + DB trên dịch vụ free tier; auto-deploy từ `main`.
  - **Tài liệu**: `docs/notes/devops/DEPLOYMENT.md`, ADR `docs/adr/002-hosting.md`.

---

## 🧰 Dev CLI (đã có trong repo)

| Lệnh | Việc |
| --- | --- |
| `python dev.py devops check` | Kiểm tra môi trường (Python, venv, git, pytest) |
| `python dev.py devops ci` | Chạy toàn bộ kiểm tra như CI: ruff, pytest, quét secret, benchmark |
| `python dev.py devops branch [tên]` | Kiểm tra tên nhánh `<role>-<name>/<issue>-<task>` |
| `python dev.py devops commit-msg "<msg>"` | Kiểm tra commit message |
| `python dev.py devops install-hooks` | Cài hook `commit-msg` chặn commit sai cú pháp |
| `python dev.py db scan-secrets` | Tìm API key, token, private key trong file git đang theo dõi |

## 🏗️ CI hiện tại (`.github/workflows/ci.yml`)

| Bước | Lệnh | Fail khi |
| --- | --- | --- |
| Lint | `ruff check .` | Lỗi cú pháp, import thừa |
| Test | `pytest tests/` | Bất kỳ test nào fail |
| Quét secret | `python dev.py db scan-secrets` | Có key/token hoặc file `.env` bị commit |
| Benchmark | `python dev.py ai benchmark validate` | Sai định dạng, trùng id |
| Tên nhánh (chỉ PR) | `python dev.py devops branch "$HEAD_REF"` | Nhánh không đúng cú pháp |

**Tuần 1 thêm:** `alembic upgrade head` trên SQLite tạm (phối hợp #12); build UI `npm run build` khi `ui/package.json` đã có (sau #6).

## 🌐 Môi trường

| Môi trường | Dùng cho | Cập nhật | Dữ liệu |
| --- | --- | --- | --- |
| Local | Code hằng ngày | Tay | SQLite `data/local.db` hoặc Postgres trong Compose |
| Staging | Demo thứ Sáu, test ghép nối | Tự động khi merge `main` | User giả lập |
| Production | Pilot (từ tuần 6) | Tag `v*` | Người dùng thật |

**Bảng service/port (local)**

| Service | Port | Kiểm tra |
| --- | ---: | --- |
| API (FastAPI) | 8000 | `curl http://127.0.0.1:8000/api/v1/health` |
| UI (Vite) | 5173 | mở `http://127.0.0.1:5173` |
| Postgres | 5432 | `docker compose ps` (healthy) |

## 🚀 Deploy API lên Vercel (PR #43)

Backend FastAPI chạy trên Vercel (project `cs252-virtual-assistant`, preset FastAPI), DB là Postgres trên Neon (gắn qua Vercel Marketplace).

| Môi trường | URL | Bảo vệ |
| --- | --- | --- |
| Production | <https://cs252-virtual-assistant.vercel.app> | Công khai |
| Preview | `cs252-virtual-assistant-<hash>-vodat2553-4664.vercel.app` | Vercel Authentication (chỉ thành viên team) |

**Cách hoạt động**

- `index.py` ở gốc repo là entrypoint (`[tool.vercel] entrypoint = "index:app"` trong `pyproject.toml`): Vercel import module từ gốc repo, còn code nằm trong `src/`, nên file này thêm `src/` vào `sys.path` rồi re-export `app`.
- `.vercelignore` chặn `.env*`, `*.db` và cache để `vercel deploy` không upload secret hay DB local.
- App đọc **`DATABASE_URL`**; nếu thiếu sẽ rơi về SQLite và crash (`unable to open database file`) vì filesystem của Vercel chỉ đọc. Biến này phải có ở **cả Preview và Production**. Các biến `POSTGRES_*`/`PG*` do Neon tạo không được app dùng.

**Deploy (chưa nối Git, deploy bằng CLI)**

```bash
npm i -g vercel && vercel link          # lần đầu
vercel deploy                           # preview
vercel curl <preview-url>/api/v1/health # qua lớp bảo vệ, mong đợi {"status":"ok",...}
vercel deploy --prod                    # production
curl https://cs252-virtual-assistant.vercel.app/api/v1/health
vercel logs --deployment <url> --query 'level:error'
```

**Lưu ý**

- Thêm/sửa biến môi trường: `vercel env add <NAME> <preview|production>` (chạy trong PowerShell; trong Git Bash/Anaconda shell lệnh `vercel` có thể lỗi `Cannot find module ...\vc.js`) hoặc qua dashboard → Settings → Environment Variables.
- Chưa có `LLM_*`/`COMPANION_LLM_*` trên Vercel nên health trả `ai_provider: offline`.
- `/` trả 404 là bình thường: API nằm dưới `/api/v1`, tài liệu ở `/docs`.
- UI (`ui/`) chưa deploy lên Vercel.

## 🔐 Quản lý secret

| Secret | Ở đâu | Ai giữ |
| --- | --- | --- |
| `LLM_API_KEY` | `.env` local, dashboard dịch vụ staging | AI lead + DevOps |
| `JWT_SECRET` | `.env` local (giá trị ngẫu nhiên riêng), dashboard staging | DevOps |
| `DATABASE_URL` | `.env` local, Vercel env (Preview + Production, Neon) | DevOps |

Lỡ commit secret: **thu hồi key ở nhà cung cấp trước**, báo DevOps, sau đó mới xóa khỏi lịch sử.

## 🤝 Phối hợp với role khác

| Với | Cần gì | Khi nào |
| --- | --- | --- |
| Cả team | Cài hook, đọc `docs/guidelines/` | Standup thứ Hai |
| DB&Security (#12, #13) | Migration và app FastAPI chạy được trong container | Thứ Tư–Năm |
| UI/UX (#6) | Cấu hình Vercel cho `ui/` | Thứ Năm |
| QA | Thêm test mới vào CI | Liên tục |

## 📊 Kết quả tuần 1 (điền khi xong)

| Hạng mục | Kết quả |
| --- | --- |
| Thành viên đã cài hook | _1/6_ (xem bảng dưới) |
| URL staging UI | _..._ |
| URL staging API | <https://cs252-virtual-assistant.vercel.app> (Vercel, PR #43) |
| Thời gian từ merge đến staging cập nhật | _... phút_ |

### Ai đã cài hook (#17)

Cách cài: `python dev.py devops install-hooks`. Kiểm tra: `git commit --allow-empty -m "update code"` phải bị chặn với `[FAIL]`. Cài xong thì tự sửa dòng của mình trong PR tiếp theo.

| Thành viên | Đã cài | Ngày |
| --- | --- | --- |
| Võ Thành Đạt | ✅ | 2026-10-25 |
| Lê Hồng Đăng | ⬜ | |
| Võ Gia Minh | ⬜ | |
| Trần Quyết Thắng | ⬜ | |
| Lê Phan Đức Mân | ⬜ | |
| Nguyễn Quốc Thịnh | ⬜ | |

## 🌿 Git Workflow & Branching

- Nhánh: `devops-<name>/<issue>-<task>`, ví dụ `devops-dat/17-git-workflow`, `devops-dang/18-compose-staging`.
- Commit: `ci(devops): check branch names on pull requests`, `chore(devops): add docker compose for api and db`.
