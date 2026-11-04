# 🚀 Kế hoạch Phát triển 6 Tuần (6-Week Roadmap)

Tài liệu này là kế hoạch triển khai chính thức của Group 04: trong 6 tuần, team xây **ứng dụng học tốt nhất có thể** trên web, xoay quanh một luồng duy nhất: **tải syllabus lên → knowledge graph của cả môn → roadmap có lịch → nguồn học đã xác minh cho từng concept**. Việc chia theo 5 mảng: **UI/UX · AI implementation · Database & Security · QA/QC · DevOps**. Mô tả chi tiết sản phẩm nằm ở [APP_SPECIFICATION.md](APP_SPECIFICATION.md); tiêu chuẩn chất lượng ở mục 1.5 của spec.

> [!IMPORTANT]
> **Knowledge graph là trung tâm.** Từ syllabus, app dựng một graph cho thấy mọi concept môn học cần và concept nào phải học trước concept nào; roadmap, lịch và nguồn học đều đọc từ graph đó (spec mục 1.1, 10.1). Kế hoạch **không** bao gồm thương mại hóa (gói trả phí, thanh toán, landing page, gọi vốn) và **không** làm nền tảng mobile (app native, PWA). Toàn bộ thời gian dành cho độ đúng, độ tin cậy của nguồn, an toàn, trải nghiệm và hiệu năng. Mục có nhãn **(stretch)** là thứ bỏ đầu tiên khi tuần bị trễ.

---

## 📌 1. Tổng quan (Overview)

| Tuần | Chủ đề | Lớp chất lượng | Demo thứ Sáu | Tag |
|---:|---|---|---|---|
| 1 ✅ | Nền móng: tài liệu vào theo trang, trích dẫn ra | Đúng: mọi nội dung AI có trang nguồn | Upload PDF, nhận câu hỏi có trích dẫn trang | `v0.1` |
| 2 ✅ | Core loop đầu tiên: syllabus → roadmap → nguồn | Đáng tin: verify or drop, evidence quote | Upload syllabus, roadmap theo tuần có mốc kiểm tra, mỗi chặng có nguồn đã chấm điểm | `v0.2` |
| 3 | **Knowledge graph của cả môn từ syllabus** | Đúng: graph đủ concept, đúng prerequisite, luôn là DAG | Upload syllabus CSC10014 → graph kiểu Obsidian của cả môn (≥ 30 concept), bấm node thấy CLO, trang syllabus, mốc kiểm tra | `v0.3` |
| 4 | Nguồn đã xác minh trên graph + học tại node | Đáng tin + hiệu quả học | Bấm node thấy nguồn catalog đã xác minh; luyện tập, ôn FSRS và hỏi đáp mở từ node | `v0.4` |
| 5 | K-12, giáo viên, người tự học | An toàn, phân quyền | Giáo viên xuất bản graph và nguồn cho lớp; tài khoản K-12 an toàn; placement test tô "đã biết" trên graph | `v0.5` |
| 6 | Hoàn thiện chất lượng, bảo mật, phát hành | Nhanh, bền, dễ dùng | Full benchmark ≥ 90%, load test pass, usability test với 50 sinh viên | `v1.0` |

**Định nghĩa Done chung (mọi tuần):** tính năng có test, chạy trên staging, qua safeguard test liên quan, có trạng thái empty/loading/error, dùng được bằng bàn phím và trên màn hình nhỏ (trình duyệt), và không làm giảm điểm benchmark của tuần trước.

**Phân công theo mảng** (theo danh sách vai trò của lớp; DevOps giao cho hai Developer):

| Mảng | Mã role | Người phụ trách |
|---|---|---|
| UI/UX | `uiux` | Lê Phan Đức Mân, Nguyễn Quốc Thịnh |
| AI implementation | `ai` | Võ Gia Minh, Trần Quyết Thắng |
| Database & Security | `dbsec` | Võ Gia Minh, Trần Quyết Thắng, Nguyễn Quốc Thịnh |
| QA/QC | `qa` | Lê Hồng Đăng |
| DevOps | `devops` | Lê Hồng Đăng, Võ Thành Đạt |
| Leader / Presenter | `pm` | Võ Thành Đạt |

**Nhịp tuần (Weekly rhythm):** Thứ Hai: PM mở milestone và issue của tuần · Hằng tối: standup 15 phút · Thứ Tư: merge giữa tuần, gỡ vướng · Thứ Sáu: demo, báo cáo QA, retro, tag release.

---

## 📍 Tuần 1: Nền móng (Foundation) ✅

* **Mục tiêu**: Upload một file tài liệu, nhận câu hỏi có trích dẫn đúng trang.
* **Chi tiết từng role**: [docs/week1/](../week1/README.md) · Issue: #5 đến #18.
* **Vai trò trong sản phẩm hiện tại**: ingest theo trang, module `llm`, schema, auth, CI và staging là nền cho cả luồng syllabus. Phần slide trở thành tính năng bổ trợ "tài liệu riêng của chặng" (UC-09).

| Mảng | Đã làm |
|---|---|
| UI/UX | Wireframe, design tokens, app shell Pathly (React + Vite) có đăng nhập |
| AI | Module `llm` (1 vendor phía sau), prompt bắt buộc trích dẫn trang, BM25 trên page chunks |
| Database & Security | Schema (`db/schema.sql`) + migration, FastAPI + ingest PDF theo trang, hash mật khẩu, secret chỉ trong `.env` |
| QA/QC | Test plan, `eval/benchmark.jsonl`, template bug log, báo cáo QA tuần 1 |
| DevOps | Git flow, CI (lint + test + quét secret + benchmark), Docker Compose, staging |

## 📍 Tuần 2: Core loop đầu tiên: syllabus → roadmap → nguồn ✅

* **Mục tiêu**: Từ một syllabus thật ra roadmap theo tuần có mốc kiểm tra, mỗi chặng có nguồn đã kiểm tra link và chấm điểm.
* **Kết quả**: release [`v0.2`](../releases/v0.2.md).

| Mảng | Đã làm |
|---|---|
| UI/UX | Điều hướng core loop (#53, #79) |
| AI | Parser syllabus có trích dẫn trang và kiểm tra deterministic (#59, #89) · syllabus preview + validation offline (#90) · chuẩn hóa chủ đề (#50, #73) · roadmap builder có cạnh prerequisite và mốc kiểm tra (#60, #85) · search provider không chứa PII (#61, #84) · vetting, chấm 7 tiêu chí, MMR, thay nguồn "không hữu ích" (#62, #87) |
| Database & Security | Upload syllabus PDF/DOCX/text (#49, #74) · API syllabus và roadmap (#63) · planner theo phụ thuộc và tải tuần (#52, #80) · safe fetcher chống SSRF, domain policy (#64, #86) |
| QA/QC | Benchmark 10 syllabus đa định dạng + gold standard · benchmark nguồn và red-team fixture (#66, #83) |
| DevOps | Job queue + worker, cache nguồn 7 ngày, kiểm tra link hằng ngày (#68, #81) · dashboard chi phí theo chặng (#69, #88) |

## 📍 Tuần 3: Knowledge graph của cả môn từ syllabus

* **Mục tiêu**: Sau khi xác nhận syllabus, người học thấy **toàn bộ môn học trên một graph**: mọi concept môn cần, cạnh prerequisite, mốc kiểm tra bao phủ concept nào, và tiến độ của mình. Roadmap của tuần 2 được đọc lại từ graph này (spec 10.1). Đây là phần lõi của epic #94.
* **Sự kế thừa từ Tuần 2**: Dùng lại parser syllabus, roadmap builder, `concepts`, `prereqs`, Kahn's sort và Tarjan SCC.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Wireframe graph (#107) · component `GraphCanvas` (#108), dùng chung cho S5 và S14 · panel node: tóm tắt, CLO, trang syllabus, prerequisite / mở khóa, mốc kiểm tra, mastery · sửa cạnh trên graph (thêm, bỏ, đổi strict/soft) | Upload syllabus CSC10014 → mở graph cả môn (≥ 30 concept), kéo/zoom mượt, bấm node thấy trang syllabus nguồn |
| AI | Trích concept của cả môn từ syllabus (chủ đề + CLO + giáo trình), mỗi concept có `source_page` · gộp concept trùng bằng embeddings · đề xuất cạnh `strict` có confidence · service graph: chặn cycle khi thêm cạnh, local graph, transitive reduction (#97) | Trên 5 graph tham chiếu: recall concept ≥ 90%, precision cạnh `strict` ≥ 80% theo người chấm |
| Database & Security | Migration graph + chặn cycle khi ghi (#100) · API knowledge graph: global, local, sửa cạnh (#103) · layout và mastery lưu theo từng user | Không có cách nào (UI, API, import) lưu được một cycle; không user nào thấy mastery hoặc layout của user khác (có test) |
| QA/QC | 5 graph tham chiếu (gold) từ 5 syllabus thật · đo recall concept và precision/recall cạnh · test hiệu năng graph (#112, phần 1) · báo cáo QA tuần 3 | Báo cáo 3 có số liệu graph trên cả 5 syllabus |
| DevOps | Seed dev có syllabus và graph mẫu · số liệu graph (số concept, số cạnh bị chặn) trên dashboard · tag `v0.3` | Seed dev dựng graph mẫu bằng 1 lệnh |

## 📍 Tuần 4: Nguồn đã xác minh trên graph + học tại node

* **Mục tiêu**: Mỗi concept trên graph có nguồn học **đã xác minh** từ catalog (epic #92), và người học học ngay tại node: luyện tập, ôn tập, hỏi đáp.
* **Sự kế thừa từ Tuần 3**: Graph của môn là điểm vào cho mọi tính năng; resource finder của tuần 2 dùng catalog làm provider đầu tiên.
* **Thứ tự phụ thuộc**: #93 → #95 → #96, #98 → #99 → #101 → #102; panel nguồn (#109) chờ #102.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Panel node + nguồn đã xác minh (#109) · tìm, lọc, local graph, chế độ danh sách (#110) · màn admin duyệt nguồn + nhãn "Đã xác minh" (#104) · lối vào luyện tập / ôn tập / hỏi đáp từ node · review session | Một sinh viên đi từ graph → node → nguồn → 5 câu luyện tập không cần hướng dẫn |
| AI | Taxonomy môn học và gắn nhãn (#99) · pipeline xác minh + hàng chờ duyệt (#101) · gắn nguồn catalog vào node và resource finder (#102) · sinh câu hỏi có trích dẫn cho node (UC-10) · chấm short answer theo rubric · hỏi đáp có trích dẫn (UC-12) · hint ladder (UC-13) | Mỗi concept trong 5 graph tham chiếu có ≥ 3 nguồn catalog đã xác minh (hoặc báo `insufficient`); chấm điểm khớp người chấm ≥ 85% |
| Database & Security | ADR 004: phạm vi, nguồn được phép, giấy phép (#93) · migration `0008_verified_catalog` (#95) · danh sách ~500 trường (ROR + OpenAlex) và tier uy tín (#96) · khung connector + MIT OCW, OpenStax, Open Yale (#98), tôn trọng `robots.txt` · scheduler `fsrs` + review log (UC-11) · mastery của node tính từ review log | Nguồn chưa xác minh không bao giờ hiện cho người học (có test); 100% dòng catalog có giấy phép |
| QA/QC | Benchmark chất lượng catalog (#106) · benchmark câu hỏi lên 60 case · red-team: 30 lộ đáp án, 15 trang web chèn lệnh · báo cáo QA tuần 4 | Link chết trong catalog đang hiện < 2%; mọi safeguard test pass trong CI |
| DevOps | Job làm mới catalog định kỳ, snapshot, seed dev (#105) · tag `v0.4` | Job làm mới chạy hằng đêm trên staging |

## 📍 Tuần 5: K-12, giáo viên, người tự học

* **Mục tiêu**: Cùng luồng syllabus → graph → roadmap dùng được an toàn cho học sinh lớp 10–12, hữu ích cho giáo viên, và cho người tự học không có syllabus.
* **Sự kế thừa từ Tuần 4**: Graph, catalog, câu hỏi và scheduler; companion khóa ở buddy/mentor cho K-12.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | UI K-12 (câu đơn giản, tiếng Việt trước) · dashboard giáo viên: graph của lớp tô theo concept lớp đang yếu, ghim/loại nguồn, xuất bản (UC-15) · email tuần cho phụ huynh (UC-16) · companion panel 3 mode (UC-14) · placement test tô concept "đã biết" trên graph (UC-17) | Giáo viên xuất bản graph và nguồn cho lớp trong < 5 phút |
| AI | Graph K-12 từ khung chương trình của Bộ (toán lớp 10–12) · "syllabus nháp" cho người tự học từ mục lục khóa học · prompt companion buddy, mentor, girlfriend · gộp concept liên môn (#111) **(stretch)** | 30 câu K-12 được giáo viên duyệt, ≥ 90% đúng; placement cắt ≥ 30% lộ trình với người thử có kinh nghiệm |
| Database & Security | Role student, teacher, parent, admin · đồng ý của phụ huynh · tối thiểu hóa dữ liệu trẻ vị thành niên · age gate 18+ và feature flag cho girlfriend mode · luồng xử lý khi có dấu hiệu tự hại · xuất và xóa dữ liệu tài khoản | 0 tài khoản K-12 vào được girlfriend mode trong 50 test |
| QA/QC | Ma trận test phân quyền · bộ test an toàn trẻ em · 20 hội thoại companion · regression · báo cáo QA tuần 5 | Ma trận phân quyền pass 100% |
| DevOps | Staging có dữ liệu lớp học giả lập · audit log hành động của giáo viên/admin · dịch vụ feature flag · tag `v0.5` · CLI companion cho học viên **(stretch)** | Lớp demo (giáo viên, học sinh, phụ huynh) hoạt động end-to-end |

## 📍 Tuần 6: Hoàn thiện chất lượng, bảo mật, phát hành

* **Mục tiêu**: Bản `v1.0` ổn định, an toàn, đạt mọi ngưỡng benchmark, được kiểm chứng bằng usability test với 50 sinh viên.
* **Sự kế thừa từ Tuần 5**: Toàn bộ hệ thống; tuần này không thêm tính năng mới, chỉ đo, sửa và đánh bóng.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Hoàn thiện S3–S7 và S14 (graph) · trạng thái empty/loading/error · onboarding lần đầu · rà accessibility lần cuối (WCAG AA) · usability test với 50 sinh viên, sửa 10 vấn đề lớn nhất | ≥ 4/5 người dùng mới tự đi hết syllabus → graph → roadmap không cần trợ giúp |
| AI | Chạy full benchmark (syllabus, graph, nguồn, câu hỏi), sửa 10 lỗi lớn nhất · cache câu trả lời theo trang · kiểm tra companion (không gây cảm giác tội lỗi, giới hạn thời gian) · hiệu chỉnh ngưỡng điểm nguồn | Benchmark ≥ 90% về trích dẫn và độ đúng; F1 syllabus ≥ 90% |
| Database & Security | Index và tối ưu truy vấn (cả truy vấn graph) · rà OWASP Top 10 for LLM Applications · sửa phát hiện · quy trình xử lý sự cố 1 trang | Không còn lỗi mức nghiêm trọng cao |
| QA/QC | Load test 1.000 user giả lập · test hiệu năng graph (#112, phần 2) · full regression · tổng hợp usability test · báo cáo QA cuối với bug còn mở và giới hạn | p95 < 2 giây ở 1.000 user; graph 30+ concept mượt trên laptop tầm trung |
| DevOps | Deploy production · dashboard (latency, lỗi, chi phí LLM, cờ an toàn, link chết) · runbook và lịch trực · tag `v1.0` | Production chạy, cảnh báo gửi về nhóm chat |

---

## 🚧 2. Sau tuần 6 (What continues)

| Việc | Vì sao không xong trong 6 tuần | Bắt đầu |
|---|---|---|
| Đo mức độ dùng lại sau 4 tuần (app có thật sự có ích không) | Cần người dùng thật dùng ít nhất 4 tuần | Tuần 6 |
| Nghiên cứu khả năng nhớ (recall study) | Cần độ trễ ≥ 1 tuần giữa học và kiểm tra | Tuần 5 |
| Mở rộng catalog đã xác minh lên ≥ 2.000 khóa học từ ≥ 100 trường (epic #92) | Mỗi connector cần rà giấy phép và điều khoản riêng | Tuần 4 |
| Hiệu chỉnh ước lượng thời lượng chặng theo dữ liệu thật | Cần ≥ 2 tuần `actual_minutes` của từng người | Tuần 6 |
| Nghiên cứu kết quả học tập 3 tháng | Cần trọn một học kỳ | Sau tuần 6 |

**Kiểm tra khối lượng (Honest load check):** Kế hoạch này khoảng **3 lần** khối lượng của MVP 4 tuần cho cùng 6 người. Dự kiến bỏ phần lớn mục **(stretch)** và làm mỏng tính năng bổ trợ ở tuần 4–5. Ưu tiên tuyệt đối: luồng syllabus → graph → roadmap, safeguard test và benchmark (đây là yêu cầu tối thiểu được chấm điểm).

## ⚠️ 3. Rủi ro chính

| # | Rủi ro | Giảm thiểu |
|---|---|---|
| 1 | Graph thiếu concept hoặc sai prerequisite | Mọi concept có trang syllabus, người dùng sửa và xác nhận graph, 5 graph tham chiếu đo mỗi tuần |
| 2 | LLM sinh câu hỏi sai hoặc không trích dẫn | Bước duyệt của người dùng, bắt buộc citation, mục tiêu 90% trên benchmark |
| 3 | Syllabus trích xuất kém (bảng, ảnh, định dạng lạ) | Bước duyệt S4 bắt buộc, benchmark 20 syllabus, cho phép dán text thay thế |
| 4 | Phạm vi phình to | Non-goals trong spec (gồm thương mại hóa và mobile); PM từ chối issue ngoài kế hoạch |
| 5 | Girlfriend mode lộ cho người dưới 18 tuổi | Age gate + feature flag + 50 test K-12; mode tắt mặc định |
| 6 | Quá tải người làm | Cắt (stretch) trước; không cắt safeguard và benchmark |
| 7 | Catalog thu thập nguồn sai giấy phép hoặc vi phạm `robots.txt` | ADR 004 (#93) chốt danh sách nguồn được phép; chỉ lưu metadata + link; nguồn không cho thu thập chỉ thêm tay |
| 8 | Graph lớn bị chậm hoặc khó đọc | Local graph mặc định, transitive reduction, chế độ danh sách; test hiệu năng (#112) |

---
**Tóm lược:** Tuần 1–2 **xây lõi** (syllabus → roadmap → nguồn) $\rightarrow$ Tuần 3 **knowledge graph của cả môn** từ syllabus $\rightarrow$ Tuần 4 **đáng tin** (nguồn đã xác minh trên mỗi node, học tại node) $\rightarrow$ Tuần 5 **an toàn và mở rộng người dùng** (K-12, giáo viên, người tự học) $\rightarrow$ Tuần 6 **hoàn thiện** (benchmark, bảo mật, hiệu năng, usability test).
