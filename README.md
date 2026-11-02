# Study Companion — Group 04 (CS252 Virtual Assistant)

Trợ lý học tập AI cho **chính môn học bạn đang học**, từ THPT (K-12) đến đại học: thả slide bài giảng vào, ứng dụng biến chúng thành câu hỏi luyện tập có trích dẫn trang, lịch ôn tập hằng ngày và bản đồ kiến thức đã nắm vững, kèm một nhân vật đồng hành động viên bạn học.

## 📌 Tóm tắt ý tưởng (Improved idea)

**Vấn đề.** Học sinh, sinh viên nhận slide mới mỗi tuần nhưng thường chỉ đọc lại vào đêm trước khi thi, cách học kém hiệu quả nhất và quên rất nhanh. Coursera bán nội dung của họ; chưa có công cụ tốt làm việc trên **nội dung giáo viên của bạn đã đưa**.

**Giải pháp.**
- **Slide → câu hỏi có trích dẫn**: AI đề xuất concept và câu hỏi; mỗi câu trỏ về đúng trang slide, không có nguồn thì không trả lời (*cite or refuse*).
- **Ôn tập đúng lúc sắp quên**: lịch ôn theo thuật toán FSRS, buổi 10 phút gồm warm-up, core (xen kẽ chủ đề), wrap.
- **Gợi ý thay vì đáp án**: hint ladder; bài được chấm điểm chỉ nhận gợi ý.
- **Sửa lỗ hổng nền**: sai 2 lần thì quay lại concept tiên quyết.
- **Companion 3 mode**: study buddy (mặc định, mọi lứa tuổi), mentor, và girlfriend mode **chỉ cho người dùng 18+ đã xác minh tự bật**; không nội dung tình dục; unlock theo mức độ nắm vững, không theo thời gian dùng app.
- **Cho trường học (từ tuần 4)**: dashboard giáo viên, báo cáo phụ huynh, tài khoản K-12 an toàn.

**Nguyên tắc kỹ thuật.** Dùng giải pháp đơn giản nhất đủ dùng (*solution ladder*): graph, lịch ôn, chấm trắc nghiệm là thuật toán thường; LLM chỉ soạn câu hỏi, gợi ý và phản hồi, luôn có fallback.

**Lộ trình.** 6 tuần xây phần mềm cho toàn bộ 7 phase của lộ trình startup 18 tháng; kết quả pilot, hợp đồng trường học và gọi vốn tiếp tục sau đó.

| Tài liệu | Nội dung |
|---|---|
| [docs/roadmap/PLAN.md](docs/roadmap/PLAN.md) | Kế hoạch 6 tuần, việc theo 5 mảng mỗi tuần |
| [docs/roadmap/APP_SPECIFICATION.md](docs/roadmap/APP_SPECIFICATION.md) | Đặc tả đầy đủ: use case, màn hình, kiến trúc, dữ liệu, API, AI, companion, bảo mật |
| [docs/week1/](docs/week1/README.md) | Nhiệm vụ tuần 1 theo từng role |
| [docs/guidelines/](docs/guidelines/README.md) | Quy tắc nhánh, PR, commit |

## 👥 Team

| MSSV | Họ tên | Vai trò (theo danh sách lớp) | Mã role trong repo | `<name>` cho nhánh |
|---|---|---|---|---|
| 25125052 | Võ Thành Đạt | Leader, Presenter, Developer | `pm`, `devops` | `dat` |
| 25125040 | Lê Hồng Đăng | QA/QC, Developer | `qa`, `devops` | `dang` |
| 25125030 | Võ Gia Minh | AI-Integration, Security & Data | `ai`, `dbsec` | `minh` |
| 25125034 | Trần Quyết Thắng | AI-Integration, Security & Data | `ai`, `dbsec` | `thang` |
| 25125026 | Lê Phan Đức Mân | UI/UX, Developer | `uiux` | `man` |
| 25125066 | Nguyễn Quốc Thịnh | UI/UX, Security & Data | `uiux`, `dbsec` | `thinh` |

DevOps không có trong danh sách vai trò của lớp; phần này giao cho hai Developer là Võ Thành Đạt và Lê Hồng Đăng.

## ⚙️ Cài đặt (Setup)

Yêu cầu: Python 3.10+, Git; Node.js 24 nếu làm UI.

1. Tạo môi trường ảo:
   ```bash
   python -m venv .venv
   ```
2. Kích hoạt:
   - **PowerShell (Windows):**
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **Git Bash / Linux / macOS:**
     ```bash
     source .venv/bin/activate
     ```
3. Cài thư viện:
   ```bash
   pip install -r requirements.txt
   ```
4. Kiểm tra môi trường và cài git hook (bắt buộc, làm 1 lần):
   ```bash
   python dev.py devops check
   python dev.py devops install-hooks
   ```

## 🧰 Dev CLI theo từng mảng

Mọi lệnh chạy từ thư mục gốc repo, không cần cài thêm: `python dev.py <mảng> <lệnh>`. Xem đầy đủ: `python dev.py --help`, `python dev.py <mảng> --help`.

| Mảng | Lệnh | Việc |
|---|---|---|
| UI/UX | `python dev.py ui install \| dev \| build \| test` | Chạy các script npm của frontend trong `ui/` |
| AI | `python dev.py ai benchmark validate \| stats` | Kiểm tra / thống kê `eval/benchmark.jsonl` |
| AI | `python dev.py ai chat "câu hỏi"` | Chạy trợ lý (bản rule-based hiện tại) |
| Database & Security | `python dev.py db init [--reset]` | Tạo database SQLite cục bộ từ `db/schema.sql` |
| Database & Security | `python dev.py db scan-secrets` | Tìm API key, token, private key trong repo |
| QA/QC | `python dev.py qa test [-k từ_khóa]` | Chạy pytest |
| QA/QC | `python dev.py qa lint` | Chạy ruff |
| QA/QC | `python dev.py qa report --week N` | Tạo báo cáo QA tuần từ template |
| DevOps | `python dev.py devops check` | Kiểm tra môi trường |
| DevOps | `python dev.py devops ci` | Chạy toàn bộ kiểm tra như CI trước khi push |
| DevOps | `python dev.py devops branch [tên]` | Kiểm tra tên nhánh |
| DevOps | `python dev.py devops commit-msg "<msg>"` | Kiểm tra commit message |
| DevOps | `python dev.py devops install-hooks` | Cài hook chặn commit sai cú pháp |

## ▶️ Chạy trợ lý hiện tại

```bash
python dev.py ai chat "where is the training office?"
```

## 🧪 Kiểm thử

```bash
python dev.py qa test
python dev.py devops ci
```

## 📂 Cấu trúc thư mục

```text
├── .github/              # CI (GitHub Actions), PR template
├── data/                 # Dữ liệu và bảng tra cứu (không chứa dữ liệu cá nhân thật)
├── db/schema.sql         # Schema database (SQLite local, Postgres staging)
├── dev.py                # Điểm vào của Dev CLI
├── docs/
│   ├── guidelines/       # Quy tắc Git, PR, commit
│   ├── roadmap/          # PLAN.md, APP_SPECIFICATION.md
│   ├── week1/            # Nhiệm vụ tuần 1 theo role
│   ├── qa/reports/       # Báo cáo QA hằng tuần
│   └── schedule/         # Lịch trình trình bày
├── eval/benchmark.jsonl  # Bộ benchmark chất lượng
├── scripts/              # Script tiện ích (check_env.py)
├── src/assistant/        # Trợ lý rule-based hiện tại
├── src/devcli/           # Mã nguồn Dev CLI (ui, ai, db, qa, devops)
├── tests/                # Test tự động
└── ui/                   # Frontend (React + Vite, nhánh codex/pathly-ui)
```

## 🌿 Đóng góp (Contributing)

Issue → nhánh `<role>-<name>/<issue>-<task>` → commit `<type>(<scope>): <mô tả>` → `python dev.py devops ci` → PR `[<role>-<name>] ...` → 1 approve + CI xanh → squash merge. Chi tiết: [docs/guidelines/](docs/guidelines/README.md).

## Scheduling Workspace (legacy eight-week plan)

Luồng học từ slide mới (#13 → #9 → #10): API `app.api.main:app`, hướng dẫn khởi chạy, migration và hợp đồng ghép auth/BM25 tại [docs/minh-slide-pipeline.md](docs/minh-slide-pipeline.md).

The optional scheduling backend and connected Workspace are documented in [docs/minh-handoff.md](docs/minh-handoff.md). Run `.venv/Scripts/python.exe -m uvicorn assistant.backend.main:app --app-dir src --host 127.0.0.1 --port 8000`, then open `http://127.0.0.1:5173/#workspace`. It has its own real account/session flow. This feature is separate from the current concept extraction and cited-question roadmap.
