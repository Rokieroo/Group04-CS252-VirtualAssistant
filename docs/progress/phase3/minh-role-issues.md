# Bàn giao role của Minh — phase 3

Ngày: 05/11/2026. Tài khoản: `MikaelVo639` (Võ Gia Minh), role `ai`, `dbsec`.
Nguồn phân công là **người phụ trách đề xuất trong nội dung issue**, không phải trường GitHub assignee (hiện trống).

| Issue | Phần đã triển khai | Điều kiện nghiệm thu bên ngoài còn lại |
| --- | --- | --- |
| [#96](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/96) | Builder OpenAlex + ROR; CSV 500 trường; snapshot CC0 có phiên bản; CLI seed idempotent; authority theo tier; thêm domain tier 1 | 11 đề xuất trường Việt Nam/K-12 cần hai người duyệt theo ADR 004 trước khi áp tier ưu tiên |
| [#99](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/99) | 55 nhãn Việt–Anh, ba cấp; rule theo tiêu đề/mã môn/CLO; Gemini semantic embedding bật tùy chọn và vector lexical offline có version và điểm tin cậy; bảo toàn nhãn manual; hàng chờ nhãn resource < 0,6 | Đo precision trên 100 nguồn do người chấm; bộ hiện có 10 syllabus, chưa phải 20; nghiệm thu Gemini embedding thật cần key/model và quota; adapter có test offline bằng SDK giả lập |
| [#100](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/100) | Migration 0009; cạnh + concept FK + layout riêng; transaction lock dùng DB, cycle path; lưu strict/soft của graph; API thêm/xóa cạnh và layout | Xác nhận job PostgreSQL của PR; API global/local graph và GraphCanvas thuộc #97/#103/#108 |
| [#102](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/102) | Tài liệu riêng trước; catalog đọc DB, bốn check mới nhất phải pass và chưa quá 30 ngày; lọc chủ đề/trình độ/ngôn ngữ; BM25 + vector lexical hoặc semantic cùng model, điểm bảy tiêu chí, MMR; summary một lượt; tín hiệu insufficient; đủ 3 nguồn ≥ 0,8 không gọi web/LLM | Connector/xác minh #98/#101 và tự gắn tài liệu #114 cung cấp dữ liệu thật; Precision@5 của #106 và p95 staging chưa được đo |
| [#115](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/115) | Migration 0010; bài tập có nguồn, hash, giấy phép và quyền sở hữu; trích bài đánh số/offset; đáp án chỉ từ nguồn; API practice/checkpoint; FSRS bridge có exercise_id; bỏ prompt và đường LLM soạn đề | Cần nạp nguồn đã xác minh; checkpoint thiếu 10 câu trả insufficient; chưa tuyên bố đã đủ 10 câu CSC10014 |

## Tích hợp main và migration

Đã tích hợp main `82a2ce5` chứa PR #118 (#95) và #117 (#65). **Giữ nguyên** migration `0008_verified_catalog` và các model/schema chính thức của #95. Không mở lại hoặc đóng #95 bằng nhánh này.

- `0009_roadmap_graph`: `roadmap_nodes.concept_id`, `roadmap_edges`, `graph_layouts`, `node_materials` (contract từng trang cho #114), `catalog_embeddings`, `node_source_status`; bổ sung `resources.catalog_course_id` để nối với khóa catalog.
- `0010_quoted_exercises`: `exercises`, `exercise_subjects`, `node_exercises`, `items.exercise_id`. Các item cũ không có exercise provenance chuyển `rejected`; giữ card/review và lịch sử, không xóa dữ liệu.
- SQLite dùng native ADD/DROP COLUMN, tránh rebuild bảng cha gây cascade mất dữ liệu. Test migration nâng/hạ có card, review và node-resource tồn tại trước 0008.
- Kiểm tra FK SQLite đọc `PRAGMA foreign_key_list` trực tiếp: SQLAlchemy hiện không phản ánh đầy đủ action của FK inline tạo bằng ADD COLUMN. Cả schema SQL và migration vẫn được đối chiếu kiểu, nullability, index và FK thật.
- `add_roadmap_edge()` phải chạy trong transaction; caller commit/rollback. No-op UPDATE khóa dòng roadmap trên PostgreSQL và writer trên SQLite trước khi đọc cạnh. Hai worker thêm a→b và b→a chỉ một worker được commit; không chỉ dựa vào mutex trong process.
- `persist_built_edges()` nhận cạnh từ builder với **ID trùng node đã lưu**, mọi cạnh đi qua cùng repository. Replan chỉ thay lịch, không xóa cạnh/layout.

## Chạy lại offline

```powershell
.\.venv\Scripts\python.exe scripts/build_institutions.py --snapshots data/catalog/institution-snapshots --output .tmp/institutions-rebuilt.csv
(Get-FileHash data/catalog/institutions.csv).Hash -eq (Get-FileHash .tmp/institutions-rebuilt.csv).Hash

.\.venv\Scripts\python.exe dev.py db init
.\.venv\Scripts\python.exe dev.py db seed-institutions
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe dev.py devops ci
```

`db init`/seed ở trên dùng DATABASE_URL của môi trường hiện tại; không dùng `--reset` trên dữ liệu cần giữ. Kiểm thử dùng database tạm. Snapshot registry là metadata tổ chức công khai, không chứa dữ liệu người học. Manifest ghi DOI ROR và hash bản tải OpenAlex. Hai file gzip chỉ giữ các trường builder sử dụng; gzip có timestamp cố định để tái lập. Tải bản mới (cần mạng) bằng `--download --snapshots <thư_mục>`; public basic paging lấy 2.000 ứng viên để sort tất định và lọc 500 trường. Cursor của OpenAlex cần API key nên không dùng cursor.

`institutions-vn.json` là **đề xuất**, `reviewers` trống được bỏ qua. Không tự ghi tên reviewer hoặc giả định phê duyệt. `allowlist_tier1.txt` chỉ được thêm domain, không xóa quy tắc cũ.

Nguồn kỹ thuật chính thức: [OpenAlex institutions](https://help.openalex.org/data/institutions/), [ROR schema](https://ror.readme.io/docs/ror-data-structure), [ROR Zenodo download](https://ror.readme.io/docs/zenodo). Nhãn môn do dự án viết, tham khảo họ chủ đề của [ACM CCS](https://www.acm.org/publications/class-2012), [MSC2020](https://mathscinet.ams.org/mathscinet/msc/msc2020.html) và chương trình GDPT; không coi đây là bản sao đầy đủ các taxonomy đó.

## API để nhóm UI/AI ghép

Mọi route dưới `/api/v1`, dùng bearer token. Contract đầy đủ: [openapi.json](../../openapi.json).

| Route | Hành vi |
| --- | --- |
| `GET /concepts/{node_id}/sources?limit=5` | ID là **node roadmap**, không phải ID concept cũ; tối đa 5 mục, tài liệu riêng đứng đầu; nguồn công khai có institution/license/format/score/reason |
| `GET /roadmaps/{id}/sources:summary` | Count và status cho toàn bộ node, truy vấn bulk; GET không sửa DB |
| `POST /roadmap-nodes/{id}/materials` | Body `{source_id}`; gắn một trang cùng môn/chủ sở hữu; nối bài tập sẵn có của trang; contract thủ công cho #114, không tự động suy đoán map slide |
| `GET /roadmap-nodes/{id}/exercises?role=practice\|checkpoint` | Mỗi bài có citation; không trả đáp án; `auto_grade=false` khi nguồn không có đáp án hoặc bài chỉ-link; checkpoint < 10 → insufficient |
| `POST /roadmaps/{id}/edges` | Body `{parent_id,child_id,kind,reason}`; origin user do server đặt; 409 có `detail.path` khi cycle |
| `DELETE /roadmaps/{id}/edges/{parent}/{child}` | Cùng khóa transaction với thêm cạnh |
| `GET/PUT /roadmaps/{id}/layout` | PUT `{positions:[{node_id,x,y,pinned}]}`; tọa độ hữu hạn; không đọc/ghi layout người khác |
| `GET /admin/catalog/subject-review-queue` | Chỉ admin, chỉ nhãn resource dùng chung có confidence < 0,6; không lộ nội dung node/tài liệu riêng |

Nguồn pending/rejected/stale, thiếu bất kỳ check fetch/domain/license/metadata, check mới nhất fail, link chết hoặc check quá 30 ngày không hiện. Nhãn low confidence không được dùng làm căn cứ match nguồn. `node_source_status` để #105 tìm các node insufficient.

Catalog không được thay thế provenance bằng tên trường: trường chỉ đóng góp authority. Không dùng danh sách 500 trường làm danh sách crawl. Hàm nhập bài catalog cần text nguồn tạm có hash khớp resource; connector #98/#101 phải thống nhất hash của text được trích xuất. Không lưu toàn văn nguồn bên thứ ba.

## Thay đổi hành vi câu hỏi

`items:generate` và CLI cũ giữ tên để tránh phá caller, nhưng chỉ trích các bài đánh số đã có trong tài liệu và **không gọi model**. Không có bài thì API trả `409 exercise_bank_insufficient`. Các prompt `generate_v1/v2` đã được bỏ. Tài liệu tuần 1 mô tả sinh câu hỏi là lịch sử và đã bị chính sách #115 thay thế.

Prompt/choices/answer phải khớp nguyên văn sau chuẩn hóa khoảng trắng; offset boolean, số thực, ngoài biên hoặc kèm prose mới đều bị loại. Có test loại 10 câu bịa. Thay text trang hoặc content_hash nguồn khiến bài cũ không còn được trả. Nguồn CC BY-NC-SA hoặc giữ mọi quyền chỉ lưu link + vị trí theo ADR 004, không lưu đề/choices/answer. Câu không có đáp án không được tự bịa đáp án/rubric.

## Phạm vi chứng cứ

Các test tự động kiểm tra code path, quyền, migration, freshness và cite-or-refuse bằng dữ liệu giả lập; **không** chứng minh precision trên nguồn thật, năng lực semantic embeddings, độ phủ 20 syllabus hay hiệu năng staging. Không đóng các issue có tiêu chí chấm tay/chờ đồng đội chỉ dựa trên test xanh. PR dùng `Refs` để reviewer phân biệt phần triển khai với nghiệm thu sản phẩm.


## Kiểm tra local ngày 05/11/2026

- `python dev.py devops ci`: qua, **593 test Python**, Ruff, quét secret và benchmark validation đều qua.
- Frontend: **100 test Vitest / 17 file** qua; TypeScript và Vite production build qua. Chạy trực tiếp các binary đã cài bằng Node vì pnpm wrapper cần tải phiên bản package-manager qua mạng; không sửa lockfile có sẵn. jsdom vẫn báo `scrollTo` chưa được hỗ trợ trong vài test.
- Snapshot registry dựng lại từ bộ gzip đã commit: SHA-256 CSV giống hệt.
- Test summary 40 node: tối đa 16 câu SELECT, không ghi DB; đây là invariant truy vấn local, không phải kết quả p95 staging.
- Docker CLI có trên máy nhưng daemon chưa chạy; không tuyên bố đã thử PostgreSQL local. Bộ test tích hợp và race cạnh dùng database_url fixture để CI chạy thêm trên PostgreSQL khi đặt PATHLY_TEST_DATABASE_URL.


Lần CI PostgreSQL đầu phát hiện DDL tổng quát dùng DATETIME (và DOUBLE) không portable. Đã chuyển 0009/0010 sang khai báo Alembic tĩnh được biên dịch theo dialect; thêm test biên dịch SQL PostgreSQL và từ chối các kiểu tổng quát này. Theo dõi lượt CI mới trên commit đã sửa.

API nguồn học và feedback từ #117 cũng dùng hàng rào xác minh chung: nguồn pending/rejected/stale không thể đi vòng qua route cũ; nguồn dự phòng chưa xác minh không được trả trong feedback. Các test curation dùng verifier fixture minh bạch, không giả định cache có điểm là đã xác minh.


## Embedding ngữ nghĩa tùy chọn (#99/#102)

Cấu hình `LLM_PROVIDER=gemini`, `LLM_API_KEY` và `EMBEDDING_MODEL=gemini-embedding-001` trên backend/worker; mặc định model trống nên không có lời gọi embedding. Adapter nằm trong `app.llm`, batch tối đa 100 văn bản, chuẩn hóa vector và từ chối response rỗng/NaN/khác số lượng. Không dùng adapter này cho Embedding 2 vì model đó gộp các input trong một lần gọi (theo [tài liệu Gemini](https://ai.google.dev/gemini-api/docs/embeddings)).

`python dev.py ai tag-catalog` gắn nhãn và lưu vector cho nguồn đã ingest. Roadmap generation/search dùng cùng helper cho node với ngữ cảnh môn + CLO. Cache trong DB kiểm tra model và content hash; vocabulary công khai và vector node/resource đã có không bị gọi lại. Matcher chỉ so semantic vector khi model khớp nhau, còn lại dùng lexical. GET sources/summary không gọi provider. Lỗi vendor chỉ log loại lỗi, không log text/key, và fallback offline.

Test SDK giả lập kiểm tra batching, cache qua hai lượt, model opt-in và lỗi provider; không chứng minh chất lượng model thật. Không có câu hỏi nào được model embedding viết ra. Phần PostgreSQL còn sửa binding riêng cho `subjects.id` và `subjects.slug`, vì PostgreSQL không suy ra cùng một tham số SQL cho cả VARCHAR và TEXT.

Bộ embedding có 10 test trọng tâm đã qua, bao gồm dùng adapter trong API tạo roadmap và GET không gọi provider. Chưa gọi Gemini thật vì phiên này không có model/key/quota được cấu hình.


## Self-review trước merge

Theo yêu cầu trực tiếp của tác giả: tự review và merge PR #119. Đây là self-review, không phải approve độc lập từ thành viên khác. Các tiêu chí nghiệm thu dữ liệu thật ở trên vẫn được giữ để theo dõi, không tự đánh dấu đã đạt.

Các ca hồi quy mới đã tái hiện lỗi trước sửa và qua sau sửa: nguồn bị ẩn do stale có thể hiện lại sau khi xác minh, trong khi nguồn user đã từ chối vẫn bị loại; đổi giấy phép làm bài cũ bị ẩn đến khi nhập lại theo quyền mới; quote và nguồn dự phòng trong cache phải có content hash khớp nguồn đang được xác minh. Nhập lại nguồn chỉ-link xóa prompt/choices/answer khỏi bản bài tập tương ứng.

Bổ sung upsert taxonomy/nhãn/vector để nhiều worker không gặp lỗi unique khi khởi tạo cùng lúc; giữ nhãn manual và vector semantic hiện có khi nhập bài tập. Encoder kiểm tra cả chiều vector giữa các batch và vector đã cache. Bộ kiểm thử tích hợp cho các phần này đã qua trước khi đẩy commit review.
