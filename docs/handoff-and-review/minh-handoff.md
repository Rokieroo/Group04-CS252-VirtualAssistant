# Bàn giao phần việc của Minh

Ngày thực hiện: 28/10/2026. Nguồn phân công: [slide kế hoạch 8 tuần](../schedule/presentation_schedule_slide.svg), hai hàng **Backend & Scheduler** và **AI GF & LLM** ghi “Minh, Thắng”. Minh đã xác nhận thực hiện cả hai mảng.

## Phạm vi đã triển khai

| Tuần / use case trong slide | Phần triển khai | Vị trí chính |
| --- | --- | --- |
| 1 — Schema DB, Auth API, FastAPI | Schema SQLAlchemy; đăng ký, đăng nhập, đăng xuất; session có hạn, thu hồi được; profile, timezone | `src/assistant/backend/models.py`, `routes_auth.py`, `database.py` |
| 2 — CRUD Tasks/Goals, UC-01 | CRUD goal/task, deadline, thời lượng, ưu tiên; lọc task theo ngày trong timezone người dùng; kiểm tra quyền sở hữu | `routes_tasks.py` |
| 3 — Scheduler, UC-02/03; check-in UC-05 | Trừ giờ bận khỏi giờ rảnh, chia phiên học, giới hạn mỗi ngày, báo phần chưa xếp được; check-in thực tế | `scheduler.py`, `routes_schedule.py` |
| 4 — Replan và ghép API, UC-06 | Preview rồi commit; replan giữ lịch đã check-in; Workspace React gọi API thật | `services.py`, `ui/src/api.ts`, `ui/src/Workspace.tsx` |
| 5 — Ổn định API | Transaction, ràng buộc dữ liệu, index truy vấn; cache báo cáo có TTL, tách user và xóa khi commit; kiểm thử hồi quy | `models.py`, `cache.py`, `tests/test_backend.py`, `tests/test_scheduler.py` |
| 6 — Team Workspace, UC-09/10 | Tạo workspace, lời mời có xác nhận, chia sẻ/giao task; lịch riêng của người được giao | `routes_teams.py` |
| 7 — Coordinate Schedule, UC-11 | Giao của giờ rảnh tất cả thành viên, trừ lịch bận và lịch đã xếp; lọc thời lượng tối thiểu | `routes_teams.py` |
| 6–7 — AI GF, UC-07/08 | Báo cáo tiến độ thật, mood, ba personality; Gemini/OpenAI-compatible adapter; lịch sử chat riêng; fallback offline rõ ràng | `companion.py`, `routes_ai.py` |
| Nhắc lịch, UC-12 | Nhắc trước tối đa 15 phút; chống trùng, đánh dấu đã đọc; UI polling 30 giây | `routes_schedule.py`, `Workspace.tsx` |

Các nhiệm vụ trình bày/bảo vệ tuần 8 cần nhóm thực hiện trong buổi bảo vệ.

Kết quả double-check, các lỗi đã sửa và việc còn phải nghiệm thu: [minh-review.md](minh-review.md).

## Chạy trên máy Minh

Từ thư mục gốc, dùng Python 3.10+:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\scripts\start_backend.cmd
```

Backend chạy tại `http://127.0.0.1:8000`; Swagger tại [`/docs`](http://127.0.0.1:8000/docs). Terminal thứ hai:

```powershell
cd ui
npm install
npm run dev
```

Vào `http://127.0.0.1:5173/#workspace`, tạo tài khoản rồi dùng Planner → Team → Companion. `scripts/start_backend.cmd` dùng Python trong `.venv`, không cần đổi execution policy của PowerShell. Nếu dùng lệnh `python` báo không tìm thấy Python, cài Python thật và mở terminal mới.

Backend dùng chung `DATABASE_URL` với Alembic và dev CLI (mặc định SQLite `local.db`) và chạy `alembic upgrade head` khi khởi động. Đổi schema = thêm migration mới và cập nhật `db/schema.sql`; `tests/test_schema_sync.py` kiểm tra migration, `schema.sql` và model ORM khớp nhau. File DB và `.env` được ignore. Không có tài khoản demo cố định hay password/API key thật trong repository.

Các trang Home/Schedule/Progress/Library/AI Reporter là bản demo khóa học có sẵn, lưu `pathly.demo.v1` trong localStorage. Workspace dùng dữ liệu API riêng; chưa chuyển tự động dữ liệu demo sang tài khoản. Session Workspace nằm trong sessionStorage của tab; đăng xuất thu hồi token ở server.

## PostgreSQL

Tạo một database PostgreSQL và user có quyền tạo bảng trong database đó. Cài driver:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[postgres]"
Copy-Item .env.example .env
```

Sửa `.env`, dùng thông tin database của mình:

```dotenv
DATABASE_URL=postgresql+psycopg://pathly:YOUR_PASSWORD@localhost:5432/pathly
```

Khởi động lại backend. Cả SQLite và PostgreSQL dùng cùng schema và API. Dữ liệu thời gian được chuẩn hóa về UTC; cách dùng dialect/driver tham khảo [SQLAlchemy PostgreSQL](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).

Để chạy bộ kiểm thử trên PostgreSQL, dùng **database kiểm thử riêng** với user được phép tạo schema:

```powershell
$env:PATHLY_TEST_DATABASE_URL = "postgresql+psycopg://pathly:YOUR_PASSWORD@localhost:5432/pathly_test"
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

Mỗi test tạo schema `pathly_test_<uuid>` rồi dọn đúng schema đó. Khi biến này được đặt, các test dùng fixture database chạy trên cả SQLite và PostgreSQL. CI đã có service PostgreSQL 17 và job riêng. Máy hiện tại chưa có server PostgreSQL để chạy integration thật; schema đã được compile bằng PostgreSQL dialect. Kết quả CI cần được xem sau khi nhóm push nhánh.

## Luồng thử nhanh

1. Tạo account, tạo goal và task có deadline trong tương lai.
2. Thêm giờ rảnh và block giờ học trên lớp.
3. Preview plan: chưa thay đổi calendar. Kiểm tra danh sách `unscheduled`.
4. Save this plan: lưu các phiên vào calendar.
5. Khi phiên bắt đầu, check-in số phút thực học hoặc đánh dấu missed. Gửi lại cùng check-in không cộng điểm lần hai; thay kết quả đã chốt trả 409.
6. Preview/Replan: sắp lại phần việc chưa học trong khoảng được chọn. Phiên đã quá giờ chưa check-in được báo trong preview; chỉ khi commit mới chuyển thành missed và xếp lại phần việc. Đã học 30/90 phút thì chỉ còn 60 phút cần xếp. Nếu preview đã qua phút bắt đầu, Save làm mới đề xuất trước và cần xác nhận lại.
7. Team: tạo workspace, tạo lời mời theo email; app hiện **mã mời** một lần, chủ workspace tự gửi mã cho người nhận. Người nhận đăng nhập bằng đúng email đó và nhập mã để chấp nhận (email chưa được xác minh nên email khớp thôi là chưa đủ). Lời mời nằm trong ứng dụng, không gửi email.
8. Chia sẻ task cho thành viên. Task xuất hiện trong workspace và chỉ được xếp vào lịch assignee. Tìm giờ rảnh chung sau khi mỗi thành viên thêm availability.
9. Companion: chọn mood, gửi tin nhắn; câu trả lời dựa trên task, lịch và báo cáo tuần của tài khoản.

Demo tự động dùng DB tạm và đồng hồ mô phỏng để kiểm tra check-in mà không cần chờ:

```powershell
.\.venv\Scripts\python.exe scripts/demo_backend.py
```

Demo không gọi nhà cung cấp AI và không thay đổi `local.db`.

## API cho frontend và Thắng

Mọi API `/api/v1/*` ngoài register/login/health yêu cầu `Authorization: Bearer <access_token>`. Token là chuỗi ngẫu nhiên; server chỉ lưu SHA-256 của token. Password được băm argon2id. Session mặc định hết hạn sau 60 phút (`SESSION_MINUTES`); sai mật khẩu 5 lần liên tiếp khóa đăng nhập 15 phút (429). Không trả password hash ra response.

| Nhóm | Endpoint |
| --- | --- |
| Tài khoản | `POST /api/v1/auth/register` (cần `birth_year`, tùy chọn `account_level`), `/login`, `/logout`; `GET/PATCH /api/v1/me` |
| Course/ingest (#13) | `GET/POST /api/v1/courses`; `GET/POST /api/v1/courses/{id}/sources` (multipart `file`, PDF ≤ 20 MB) |
| Goal | `GET/POST /api/v1/goals`; `GET/PATCH/DELETE /api/v1/goals/{id}` |
| Task | `GET/POST /api/v1/tasks`; `GET/PATCH/DELETE /api/v1/tasks/{id}`; `GET /api/v1/tasks?date=YYYY-MM-DD&team_id=...&status=pending` |
| Giờ rảnh/bận | `GET/PUT /api/v1/availability`; `GET/POST /api/v1/busy-blocks`; `DELETE /api/v1/busy-blocks/{id}` |
| Lịch | `GET /api/v1/schedule?starts_at=...&ends_at=...`; `POST /api/v1/schedule/plan`, `/replan`; `POST /api/v1/schedule/{id}/check-in` |
| Nhóm | `GET/POST /api/v1/teams`; `GET /api/v1/teams/{id}/members`; `POST /api/v1/teams/{id}/invitations` (trả `code` một lần); `GET /api/v1/invitations`; `POST /api/v1/invitations/{id}/accept` (body `{"code"}`); `DELETE /api/v1/teams/{id}/members/{user_id}` |
| Chia sẻ/phối hợp | `POST /api/v1/tasks/{id}/share`; `POST /api/v1/teams/{id}/coordinate` |
| Báo cáo/nhắc lịch | `GET /api/v1/reports/weekly?start_date=YYYY-MM-DD`; `GET /api/v1/notifications`; `POST /api/v1/notifications/{id}/read` |
| AI | `POST /api/v1/ai/chat`; `GET/DELETE /api/v1/ai/messages` |
| Health | `GET /api/v1/health` |

Hợp đồng đầy đủ gồm request, response và lỗi: [openapi.json](../openapi.json). Tạo lại bằng `python scripts/export_openapi.py`. Frontend đã có typed transport `ui/src/api.ts`, xử lý timeout, lỗi validation và session hết hạn.

Ví dụ request preview:

```json
{
  "starts_at": "2030-01-07T08:00:00+07:00",
  "ends_at": "2030-01-14T00:00:00+07:00",
  "max_session_minutes": 60,
  "min_session_minutes": 15,
  "daily_limit_minutes": 180,
  "commit": false
}
```

Thay ngày trong ví dụ bằng ngày hiện tại/tương lai khi thử trên server thật. `commit: true` tính lại với dữ liệu hiện tại và lưu transaction. Khoảng plan tối đa 90 ngày, timestamp bắt buộc có offset và chính xác đến phút. `priority: 1` cao nhất, `3` thấp nhất. Lọc task theo ngày lấy task đến hạn hoặc có phiên học giao với ngày đó trong timezone profile. Form web nhập giờ theo timezone thiết bị, lịch hiển thị theo timezone profile.

Mã lỗi: 401 session không hợp lệ/hết hạn, 403 thiếu quyền sửa trong team, 404 dữ liệu không tồn tại/không thuộc phạm vi được xem, 409 thao tác xung đột, 422 input không hợp lệ. Task có check-in history được giữ lại; dùng cancel thay vì xóa. Share task bỏ liên kết goal cá nhân, xóa các phiên chưa check-in cũ và yêu cầu người được giao preview/lưu lịch của họ. Hủy task cũng gỡ các phiên chưa check-in, giữ lại kết quả đã ghi.

## Thuật toán xếp lịch

1. Gộp các khoảng availability trùng/tiếp giáp; giao với planning horizon.
2. Trừ busy blocks và lịch đã chốt/đang diễn ra/nằm ngoài khoảng được thay.
3. Số phút còn lại = duration − completed − các phút đã có lịch hợp lệ ở ngoài khoảng replan. Phiên quá giờ chưa check-in không giữ chỗ cho phần việc còn lại.
4. Sắp task theo priority, deadline rồi ID; duyệt slot rảnh sớm nhất, không vượt deadline.
5. Chia phiên theo maximum, minimum và hạn mức ngày trong timezone profile. Phiên cuối được ngắn hơn minimum nếu đó là toàn bộ phần việc còn lại.
6. Trả riêng số phút không xếp được và lý do, cùng số phiên quá giờ chưa check-in. Preview không ghi DB; commit chuyển các phiên quá giờ này thành missed, thay các planned entry trong horizon và giữ completed/missed history.

Đây là heuristic greedy có thứ tự rõ ràng, không bảo đảm nghiệm tối ưu toàn cục. Không suy đoán availability khi người dùng chưa nhập. Đổi availability hoặc task ảnh hưởng lịch sẽ xóa các future planned entry liên quan; người dùng preview/commit lại. Thêm busy block xóa các future planned entry giao với block đó. Không triển khai recurring calendar, đồng bộ Google Calendar hay background push.

## Tích hợp AI

Copy `.env.example` thành `.env`; đặt cả `COMPANION_LLM_API_KEY` và `COMPANION_LLM_MODEL`. Giữ key ở backend. Model cần là model có sẵn trong tài khoản của Minh.

OpenAI-compatible endpoint:

```dotenv
COMPANION_LLM_BASE_URL=https://api.openai.com/v1
COMPANION_LLM_API_KEY=YOUR_API_KEY
COMPANION_LLM_MODEL=YOUR_AVAILABLE_MODEL
```

Adapter gửi `model` và `messages` tới `POST /chat/completions`, theo [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

Với Gemini, đổi base URL và dùng Gemini key/model theo [tài liệu OpenAI compatibility của Google](https://ai.google.dev/gemini-api/docs/openai):

```dotenv
COMPANION_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
COMPANION_LLM_API_KEY=YOUR_GEMINI_KEY
COMPANION_LLM_MODEL=YOUR_AVAILABLE_GEMINI_MODEL
```

Prompt nhận tên, mood, personality, báo cáo tuần, tối đa 5 pending task và phiên kế tiếp của chính user. Chỉ gửi tối đa 10 tin nhắn lịch sử làm ngữ cảnh. Không gửi email, password, bearer token hay task riêng của người khác. Các personality: `warm`, `direct`, `playful`.

AI không có tool ghi dữ liệu. Chat không tự sửa lịch/task; việc thay đổi diễn ra qua API có xác nhận ở Planner. Không cấu hình provider hoặc provider timeout/429/response lỗi thì trả `provider: "offline"`, `fallback_reason` tương ứng; câu trả lời ghi rõ `[Chế độ offline]`. Lịch sử được lưu riêng theo user và có endpoint xóa.

Tích hợp provider đã được kiểm thử bằng HTTP mock, gồm request đúng ngữ cảnh, timeout, rate limit, JSON hỏng và nội dung rỗng. Chưa gọi Gemini/OpenAI bằng key thật; cần cấu hình key/model để nghiệm thu live.

## Kiểm tra và giới hạn vận hành

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe -m ruff check .
cd ui
npm test
npm run build
```

Bản local ngày 28/10/2026 sau double-check: **57 test Python và 9 test frontend đã qua**, Ruff và production build đã qua. Bốn ca mới kiểm tra mất lịch sử khi xóa đồng thời, dữ liệu Task cũ sau khóa, thay availability khi lưu plan và replan phiên quá giờ. Chi tiết nghiệm thu và giới hạn nằm trong [minh-review.md](minh-review.md).

Bộ test bao gồm CLI cũ, scheduler, auth/session, quyền sở hữu và nhóm, timezone, preview/commit, check-in idempotent, replan, reminder, AI provider/fallback và lưu DB qua restart. Test frontend kiểm tra state demo cũ và API transport. CI có job Python, PostgreSQL và UI. Thư viện TestClient hiện phát một deprecation warning về việc chuyển từ httpx sang httpx2; các test vẫn chạy thành công.

SQLite mặc định dành cho một backend development process. PostgreSQL có row lock trong các transaction lên lịch/check-in. Cache báo cáo tách theo user/timezone/tuần, tối đa 128 mục, TTL 10 giây và xóa khi transaction commit trong cùng process. Nếu triển khai nhiều worker, cập nhật ở worker khác có thể mất tối đa 10 giây để hiện trong báo cáo. Chưa có password reset, email verification hay triển khai hosting. Có giới hạn 10 tin nhắn chat/phút mỗi user và khóa đăng nhập sau 5 lần sai. Nhắc lịch được ghi khi commit kế hoạch và hiện từ 15 phút trước phiên học (đọc thông báo không ghi DB); không có thông báo hệ điều hành khi đóng ứng dụng.

## Đồng bộ main ngày 28/10/2026

Main hiện có roadmap concept/câu hỏi mới. Scheduler Workspace là tính năng tùy chọn theo slide cũ; nó dùng `COMPANION_LLM_*` để không xung đột `LLM_*` của app (database đã được hợp nhất, xem mục dưới). Các issue #9 (concept extraction) và #10 (cited item generation) chưa được phần scheduler này giải quyết. Các kiểm tra concept, ingest, retrieval, auth theo roadmap mới cần được theo dõi trong issue tương ứng.

## Hợp nhất backend ngày 28/10/2026 (#13, #14)

Sau review PR #31, backend scheduler và app chính dùng **một** database và **một** lịch sử migration:

- `DATABASE_URL` thay cho `PATHLY_DATABASE_URL`; bảng `users` là bảng chuẩn của migration `0001` (có `birth_year`, `account_level`, `adult_verified`, `failed_login_attempts`, `locked_until`). Migration `0002_scheduling_workspace` thêm các bảng scheduler; `db/schema.sql` được cập nhật tương ứng.
- Mọi endpoint nằm dưới `/api/v1` theo spec; health ở `GET /api/v1/health`.
- Thêm `POST/GET /api/v1/courses` và upload PDF theo trang (#13).
- Auth theo #14: argon2id, mật khẩu ≥ 8 ký tự có chữ và số, khóa 15 phút sau 5 lần sai, session 60 phút. Vẫn dùng session opaque phía server (thu hồi được khi logout) thay vì JWT.
- Persona “girlfriend” chỉ bật được khi `adult_verified = 1`, tài khoản university và ≥ 18 tuổi; mặc định là `buddy`.
- Lời mời nhóm cần mã mời (xem Luồng thử nhanh, bước 7).
- Trên PostgreSQL không còn khóa toàn cục trong process; row lock `SELECT ... FOR UPDATE` theo user đã đủ. SQLite (dev) vẫn dùng khóa trong process.
