# Study Companion — Group 04 (CS252 Virtual Assistant)

**Bạn mang syllabus, mục tiêu và tài liệu của mình; app dựng lộ trình học: học gì, học lúc nào, học từ nguồn nào.** Study Companion dành cho người học (học sinh THPT, sinh viên đại học, người tự học). Đây **không** phải nền tảng khóa học như Coursera hay Duolingo: app không có khóa học dựng sẵn. App đọc đề cương môn học của bạn, dựng knowledge graph của cả môn, sắp thành roadmap theo tuần trong giờ rảnh của bạn, rồi đề xuất nguồn học và bài tập có sẵn, đã được kiểm tra, cho từng concept.

## 📌 Ý tưởng sản phẩm

**Vấn đề.** Đầu kỳ, sinh viên nhận syllabus của mỗi môn nhưng hiếm khi biến nó thành kế hoạch học theo tuần. Khi cần tài liệu ngoài slide, họ mất hàng giờ tìm trên Google và YouTube, rồi thường dừng ở kết quả đầu tiên, dù nó sai trình độ, lỗi thời hoặc là bản lậu. Vấn đề không phải thiếu tài liệu, mà là **có quá nhiều tài liệu kém** và không biết học gì vào tuần nào.

**Người học đưa vào (Input).**

| Đầu vào | Ví dụ | Bắt buộc |
| --- | --- | --- |
| Syllabus | Đề cương PDF/DOCX hoặc dán text; người tự học dán mục lục hoặc mô tả điều muốn học | Có (hoặc mô tả mục tiêu) |
| Mục tiêu học | "Ôn chương 3–5 trước giữa kỳ", "nắm chắc đệ quy", số giờ rảnh mỗi tuần | Không |
| Tài liệu học | Slide, giáo trình, ghi chú, đề bài tập của chính bạn | Không, thêm sau được |

**Chức năng chính (core loop).**

1. **Đọc syllabus, mục tiêu và tài liệu**: trích chuẩn đầu ra (CLO), chủ đề từng tuần, mốc kiểm tra và trọng số. Mỗi trường có chip trang nguồn để bạn kiểm tra và sửa trước khi xác nhận.
2. **Dựng knowledge graph của cả môn**: mọi concept môn học cần và concept nào phải học trước concept nào (luôn là DAG), xem tương tác kiểu Obsidian. Graph là trung tâm: roadmap, lịch và nguồn học đều đọc từ nó.
3. **Sắp graph thành roadmap có lịch**: theo tuần, kiến thức nền và mục tiêu của bạn, ước lượng thời lượng, xếp vào giờ rảnh. Không chặng nào bị xếp sau bài kiểm tra cần nó; trễ kế hoạch thì app đề xuất lịch mới để bạn duyệt.
4. **Đề xuất nguồn học đã xác minh cho từng concept**: từ tài liệu của bạn, catalog nguồn đã xác minh (khóa học mở của các trường, OER) và web; mở thật từng link, lọc trang lậu và paywall, chấm điểm theo 7 tiêu chí và chỉ giữ nguồn đạt ngưỡng, kèm lý do có trích dẫn nguyên văn từ trang.

**Tính năng bổ trợ** (luôn mở từ một node của graph hoặc một chặng của roadmap): bài tập để kiểm tra tiến độ lấy từ **tài liệu của bạn và nguồn đã xác minh**, mọi bài đều có trích dẫn vị trí, **không có câu hỏi nào do AI soạn**; concept chưa có bài tập thì app nói rõ và đưa nguồn đọc thay vì quiz · ôn tập ngắt quãng FSRS và xen kẽ (interleaving) · hỏi đáp có trích dẫn · gợi ý theo bậc thay vì đưa đáp án · thư viện nguồn cá nhân và tổng kết tuần · companion động viên (study buddy, mentor; girlfriend mode chỉ cho người dùng 18+ đã xác minh, không nội dung tình dục, không bao giờ mở cho tài khoản K-12).

**Nguyên tắc.**

- **Chỉ phục vụ người học**: không có tài khoản giáo viên hay phụ huynh, không thương mại hóa, không app mobile; toàn bộ công sức dành cho chất lượng trải nghiệm trên web.
- **Ít mà tốt**: tối đa 5 nguồn mỗi chặng; không đủ nguồn tốt thì nói thẳng thay vì lấp bằng nguồn kém (*curate or abstain*).
- **Không bịa link, không bịa bài**: chỉ hiện link hệ thống đã tự mở và kiểm tra (*verify or drop*); bài tập đo tiến độ luôn có nguồn; không sao chép nội dung của bên thứ ba ngoài phạm vi giấy phép.
- **Giải pháp vừa đủ** (*solution ladder*): ngày tháng, xếp lịch, thứ tự chặng, chặn cycle, lọc link là thuật toán thường; LLM chỉ dùng để đọc syllabus, đề xuất prerequisite, gắn bài tập vào concept và đánh giá nguồn, luôn có fallback.

| Tài liệu | Nội dung |
| --- | --- |
| [docs/APP_SPECIFICATION.md](docs/APP_SPECIFICATION.md) | Đặc tả 3.1: tiêu chuẩn chất lượng, use case, màn hình, kiến trúc, dữ liệu, API, parser syllabus, knowledge graph, planner, bộ tìm nguồn, bảo mật, metric |
| [docs/roadmap/PLAN.md](docs/roadmap/PLAN.md) | Kế hoạch 6 tuần theo từng mảng |
| [docs/adr/](docs/adr/) | Quyết định kiến trúc (database, hosting, bố cục code, catalog nguồn và giấy phép) |
| [docs/notes/devops/DEPLOYMENT.md](docs/notes/devops/DEPLOYMENT.md) | Chạy bằng Docker Compose, staging, worker |
| [docs/guidelines/](docs/guidelines/README.md) | Quy tắc nhánh, PR, commit |

## 👥 Team

| MSSV | Họ tên | Vai trò (theo danh sách lớp) | Mã role trong repo | `<name>` cho nhánh |
| --- | --- | --- | --- | --- |
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
| --- | --- | --- |
| UI/UX | `python dev.py ui install \| dev \| build \| test` | Chạy các script npm của frontend trong `ui/` |
| AI | `python dev.py ai benchmark validate \| stats` | Kiểm tra / thống kê `eval/benchmark.jsonl` |
| AI | `python dev.py ai catalog-ingest --syllabus <id\|file.gold.json> [--benchmark] [--connector <tên>]` | Nạp nguồn catalog (MIT OCW, OpenStax, Open Yale, YAML thêm tay) cho môn của syllabus, rồi báo số ứng viên mỗi chặng; chạy lại không tạo dòng mới (#98) |
| AI | `python dev.py ai tag-catalog` | Gắn taxonomy/vector cho nguồn đã nhập; embedding Gemini là tùy chọn, mặc định offline |
| AI | `python dev.py ai concepts <file.pdf>` | Đề xuất concept/chủ đề từ một file PDF |
| AI | `python dev.py ai items --concepts <file.json> <file.pdf>` | Trích bài tập có sẵn từ tài liệu, kèm trang; không gọi AI soạn đề (#115) |
| AI | `python dev.py ai syllabus-preview <file.pdf/docx/txt> [--llm]` | Xem trước syllabus, kiểm tra trang nguồn; mặc định offline ([bàn giao](docs/progress/phase2/minh-syllabus-preview.md)) |
| Database & Security | `python dev.py db init [--reset]` | Tạo database SQLite cục bộ từ `db/schema.sql` |
| Database & Security | `python dev.py db seed-institutions` | Nạp registry ROR/OpenAlex tái lập (#96) |
| Database & Security | `python dev.py db scan-secrets` | Tìm API key, token, private key trong repo |
| QA/QC | `python dev.py qa test [-k từ_khóa]` | Chạy pytest |
| QA/QC | `python dev.py qa lint` | Chạy ruff |
| QA/QC | `python dev.py qa report --week N` | Tạo báo cáo QA tuần từ template |
| DevOps | `python dev.py devops check` | Kiểm tra môi trường |
| DevOps | `python dev.py devops ci` | Chạy toàn bộ kiểm tra như CI trước khi push |
| DevOps | `python dev.py devops branch [tên]` | Kiểm tra tên nhánh |
| DevOps | `python dev.py devops commit-msg "<msg>"` | Kiểm tra commit message |
| DevOps | `python dev.py devops install-hooks` | Cài hook chặn commit sai cú pháp |

## ▶️ Chạy ứng dụng

Cách nhanh nhất là Docker Compose (Postgres + API + worker cho tác vụ nền như phân tích syllabus và tìm nguồn):

```bash
cp .env.example .env       # điền LLM_API_KEY, YOUTUBE_API_KEY, SEARCH_API_KEY nếu có
docker compose up --build -d
```

Không có API key thì để `LLM_PROVIDER=fake`: luồng vẫn chạy với dữ liệu giả lập để phát triển và test. Frontend:

```bash
python dev.py ui install
python dev.py ui dev       # mở http://127.0.0.1:5173
```

Chi tiết (chạy không cần Docker, staging, xem log worker): [docs/notes/devops/DEPLOYMENT.md](docs/notes/devops/DEPLOYMENT.md).

## 🧪 Kiểm thử

```bash
python dev.py qa test
python dev.py devops ci
```

## 📂 Cấu trúc thư mục

```text
├── .github/              # CI (GitHub Actions), PR template
├── alembic/              # Migration database
├── data/                 # Dữ liệu mẫu (không có dữ liệu cá nhân thật)
├── db/schema.sql         # Schema database (SQLite local, Postgres staging)
├── dev.py                # Điểm vào của Dev CLI
├── docker-compose.yml    # Postgres + API + worker
├── docs/
│   ├── APP_SPECIFICATION.md  # Đặc tả chi tiết
│   ├── roadmap/          # PLAN.md
│   ├── adr/              # Quyết định kiến trúc
│   ├── guidelines/       # Quy tắc Git, PR, commit
│   ├── progress/         # Nhiệm vụ và kết quả theo phase: phase1/, phase2/, phase3/
│   ├── handoff-and-review/  # Tài liệu bàn giao và rà soát
│   ├── notes/            # Ghi chú theo role: uiux/, ai/, db-security/, qa/, devops/
│   └── wireframes/       # Wireframe các màn hình
├── eval/                 # Benchmark chất lượng
├── src/app/              # Logic thuần (không phụ thuộc HTTP):
│   ├── syllabus/         #   đọc syllabus → CLO, tuần, mốc kiểm tra
│   ├── roadmap/          #   chặng, prerequisite, thời lượng
│   ├── planner/          #   xếp lịch, lập lại kế hoạch
│   ├── search/ vetting/ curator/  # tìm, kiểm tra, chấm điểm, chọn nguồn học
│   ├── ingest/ concepts/ retrieval/ items/ companion/ llm/  # nền và tính năng bổ trợ
├── src/assistant/backend/  # FastAPI: route, schema, worker
├── src/devcli/           # Mã nguồn Dev CLI (ui, ai, db, qa, devops)
├── tests/                # Test tự động
└── ui/                   # Frontend (React + TypeScript + Vite)
```

## 🌿 Đóng góp (Contributing)

Issue → nhánh `<role>-<name>/<issue>-<task>` → commit `<type>(<scope>): <mô tả>` → `python dev.py devops ci` → PR `[<role>-<name>] ...` → 1 approve + CI xanh → squash merge. Chi tiết: [docs/guidelines/](docs/guidelines/README.md).
