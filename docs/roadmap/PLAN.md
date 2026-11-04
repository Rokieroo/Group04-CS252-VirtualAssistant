# 🚀 Kế hoạch Phát triển 6 Tuần (6-Week Roadmap)

Tài liệu này là kế hoạch triển khai chính thức của Group 04: trong 6 tuần, team xây **ứng dụng học tốt nhất có thể** trên web, mỗi tuần nâng thêm một lớp chất lượng, chia việc theo 5 mảng: **UI/UX · AI implementation · Database & Security · QA/QC · DevOps**. Mô tả chi tiết sản phẩm nằm ở [APP_SPECIFICATION.md](APP_SPECIFICATION.md); tiêu chuẩn chất lượng ở mục 1.5 của spec.

> [!IMPORTANT]
> Kế hoạch **không** bao gồm thương mại hóa (gói trả phí, thanh toán, landing page, gọi vốn) và **không** làm nền tảng mobile (app native, PWA). Toàn bộ thời gian dành cho độ đúng, độ tin cậy của nguồn, an toàn, trải nghiệm và hiệu năng. 6 tuần đủ để **xây và kiểm chứng** mọi tính năng bằng benchmark, test và usability test; các nghiên cứu cần thời gian dài (nhớ sau nhiều tuần, dùng lâu dài) bắt đầu trong 6 tuần này nhưng kết thúc sau đó. Mục có nhãn **(stretch)** là thứ bỏ đầu tiên khi tuần bị trễ.

---

## 📌 1. Tổng quan (Overview)

| Tuần | Chủ đề | Lớp chất lượng | Demo thứ Sáu | Tag |
|---:|---|---|---|---|
| 1 | Nền móng: slide vào, câu hỏi có trích dẫn ra | Đúng: mọi câu hỏi có trích dẫn trang | Upload PDF, xác nhận concept, nhận 10 câu hỏi có trích dẫn trang | `v0.1` |
| 2 | Vòng ôn tập hằng ngày + knowledge graph | Đúng: chấm điểm khớp người chấm, graph không cycle | Một buổi review 10 phút; graph tự dựng có kiểm tra cycle | `v0.2` |
| 3 | Adaptive engine, dạng bài nâng cao, companion | Hiệu quả học + an toàn | Buổi học interleaving, câu spot-the-bug, gap repair, 3 mode companion | `v0.3` |
| 4 | K-12 và giáo viên | An toàn cho trẻ vị thành niên, phân quyền | Giáo viên giao bài; tài khoản K-12 không mở được girlfriend mode; email phụ huynh | `v0.4` |
| 5 | Knowledge graph tương tác + nguồn đã xác minh | Đáng tin: mỗi concept có nguồn đã kiểm chứng | Graph kiểu Obsidian của một môn thật, bấm node thấy nguồn đã xác minh; placement test cắt bớt lộ trình | `v0.5` |
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

## 📍 Tuần 1: Nền móng (Foundation)

* **Mục tiêu**: Upload một file slide, xác nhận danh sách concept và nhận 10 câu hỏi, mỗi câu trích dẫn đúng trang slide.
* **Chi tiết từng role**: [docs/week1/](../week1/README.md) · Issue: #5 đến #18.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Wireframe upload, concept editor, review session, ask panel, companion panel · design tokens · merge frontend Pathly (React + Vite), app shell có đăng nhập | Figma được team duyệt; app shell lên staging |
| AI | Module `llm` interface (1 vendor phía sau) · prompt trích concept · prompt sinh câu hỏi bắt buộc trích dẫn trang · BM25 retrieval trên page chunks | 20 câu hỏi kiểm tra tay, ≥ 80% đúng |
| Database & Security | Schema (`db/schema.sql`) + migration · FastAPI + ingest PDF theo trang · đăng ký/đăng nhập, hash mật khẩu · secret chỉ trong `.env` | Migration chạy trong CI; quét secret sạch |
| QA/QC | Test plan · `eval/benchmark.jsonl` 20 case · template bug log · báo cáo QA tuần 1 | 20 case được commit; báo cáo 1 được merge |
| DevOps | Git flow: branch, PR, 1 review, CI (lint + test + quét secret + benchmark) · Docker Compose API + DB · deploy staging | Mỗi lần merge `main` tự deploy staging |

## 📍 Tuần 2: Vòng ôn tập + Knowledge graph

* **Mục tiêu**: Học sinh làm một buổi review 10 phút, được chấm và thấy khi nào câu hỏi quay lại; graph tự dựng từ slide và được kiểm tra cycle.
* **Sự kế thừa từ Tuần 1**: Dùng lại bảng `sources`, `concepts`, `items` và module `llm`.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Màn hình review session và kết quả · mastery map (danh sách tô màu) · graph view 2D kéo thả cạnh · hàng chờ duyệt câu hỏi | Một sinh viên tự làm xong buổi 10 phút không cần hướng dẫn |
| AI | Chấm short answer theo rubric · graph builder: concept theo trang, gộp trùng bằng embeddings, đề xuất cạnh kèm confidence · hybrid retrieval (BM25 + vector) | Chấm điểm khớp người chấm ≥ 85% trên 40 câu |
| Database & Security | Scheduler dùng thư viện `fsrs` + review log · Kahn's sort và Tarjan SCC khi lưu graph · kiểm tra quyền theo từng user · rate limit endpoint LLM | Không user nào đọc được thẻ của user khác (có test) |
| QA/QC | Unit test grader và scheduler · benchmark lên 40 case · 5 graph tham chiếu để đo precision/recall cạnh · báo cáo QA tuần 2 | Báo cáo 2 có số liệu grader và graph |
| DevOps | Error tracking (Sentry free tier) · log chi phí LLM mỗi request · backup DB hằng đêm · tag `v0.2` | Chi phí mỗi buổi review hiện trên dashboard |

## 📍 Tuần 3: Adaptive engine, dạng bài nâng cao, companion

* **Mục tiêu**: Scheduler interleaving, các dạng bài bậc cao, gợi ý theo bậc (hint ladder), sửa lỗ hổng kiến thức (gap repair) và companion 3 mode.
* **Sự kế thừa từ Tuần 2**: Review log là nguồn dữ liệu cho scheduler, gap repair và companion.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Ask panel với citation bấm được · UI hint ladder · companion panel có chuyển mode và 3 cảnh unlock · session planner (warm-up / core / wrap) | Test với 3 sinh viên, sửa 3 vấn đề lớn nhất |
| AI | Hint ladder · câu spot-the-bug sinh từ câu đã duyệt · câu inversion và "giải thích bằng lời đơn giản" · interleaving giữa các nhánh anh em · prompt companion cho buddy, mentor, girlfriend · bài code trong sandbox **(stretch)** | Tỷ lệ lộ đáp án ≤ 2% trên 30 prompt red-team |
| Database & Security | Gap repair sau 2 lần sai · age gate 18+ và feature flag cho girlfriend mode · lọc prompt injection trong text upload · log an toàn (không log câu trả lời) | Age gate không bị vượt trong 10 lần thử |
| QA/QC | Bộ red-team: 30 lộ đáp án, 10 slide chèn lệnh, 20 hội thoại companion · benchmark lên 60 case · báo cáo QA tuần 3 | Mọi safeguard test pass trong CI |
| DevOps | Dịch vụ feature flag · staging có dữ liệu user giả lập · tag `v0.3` | Đổi mode bằng flag không cần deploy lại |

## 📍 Tuần 4: K-12 và giáo viên

* **Mục tiêu**: Sản phẩm an toàn cho học sinh lớp 10–12 và thật sự hữu ích cho giáo viên khi giao bài.
* **Sự kế thừa từ Tuần 3**: Dùng lại engine câu hỏi, scheduler, companion (khóa ở buddy/mentor cho K-12).

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | UI học sinh K-12 (câu đơn giản, tiếng Việt trước) · dashboard giáo viên: chủ đề yếu của lớp, giao bài, xuất điểm · email tuần cho phụ huynh · rà accessibility (bàn phím, screen reader) | Giáo viên giao và xem một bộ bài trong < 5 phút |
| AI | Dạng câu K-12 (MCQ, số, điền khuyết) · graph mẫu toán lớp 10–12 từ mục lục sách giáo khoa · companion K-12 chỉ buddy hoặc mentor | 30 câu K-12 được giáo viên duyệt, ≥ 90% đúng |
| Database & Security | Role: student, teacher, parent, admin · lưu đồng ý của phụ huynh · tối thiểu hóa dữ liệu trẻ vị thành niên · bản nháp privacy policy · luồng xử lý khi có dấu hiệu tự hại | 0 tài khoản K-12 vào được girlfriend mode trong 50 test |
| QA/QC | Ma trận test phân quyền · bộ test an toàn trẻ em · regression · báo cáo QA tuần 4 | Ma trận phân quyền pass 100% |
| DevOps | Staging có dữ liệu lớp học giả lập · audit log hành động của giáo viên/admin · tag `v0.4` | Lớp demo (giáo viên, học sinh, phụ huynh) hoạt động end-to-end |

## 📍 Tuần 5: Knowledge graph tương tác + nguồn đã xác minh

* **Mục tiêu**: Nâng graph thành màn hình khám phá kiến thức riêng kiểu Obsidian (epic #94), mỗi node có nguồn học lấy từ catalog đã xác minh (epic #92); thêm placement test và lộ trình nhiều môn cho người tự học.
* **Sự kế thừa từ Tuần 4**: Dùng lại `concepts`, `prereqs`, Kahn's sort và Tarjan SCC của tuần 2, phân quyền theo user của tuần 4, vetting và safe fetch của resource finder.
* **Thứ tự phụ thuộc**: catalog (#93 → #95 → #96, #98 → #99 → #101 → #102) chạy song song với service và migration graph (#97, #100); API graph (#103) và panel node (#109) chờ #102.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Wireframe graph (#107) · component `GraphCanvas` (#108) · panel node + nguồn đã xác minh (#109) · tìm, lọc, local graph, chế độ danh sách (#110) · màn admin duyệt nguồn + nhãn "Đã xác minh" (#104) · màn hình lộ trình nhiều môn · placement test | Mở graph của một môn thật (≥ 30 concept), kéo/zoom/lọc mượt, bấm node thấy nguồn đã xác minh; dùng được hoàn toàn bằng bàn phím và screen reader |
| AI | Service graph: chặn cycle khi thêm cạnh, local graph, transitive reduction (#97) · taxonomy môn học và gắn nhãn (#99) · pipeline xác minh + hàng chờ duyệt (#101) · gắn nguồn catalog vào node và resource finder (#102) · placement test đánh dấu concept đã biết · gộp concept liên môn (#111) **(stretch)** | Mỗi concept trong 5 graph tham chiếu có ≥ 3 nguồn catalog đã xác minh (hoặc báo `insufficient`); placement cắt ≥ 30% lộ trình với người thử có kinh nghiệm |
| Database & Security | ADR 004: phạm vi, nguồn được phép, giấy phép (#93) · migration `0008_verified_catalog` (#95) · danh sách ~500 trường (ROR + OpenAlex) và tier uy tín (#96) · khung connector + MIT OCW, OpenStax, Open Yale (#98), tôn trọng `robots.txt` · migration graph + chặn cycle khi ghi (#100) · API knowledge graph (#103) · xuất và xóa dữ liệu tài khoản | Không có cách nào (UI, API, import) lưu được một cycle; không user nào thấy mastery hoặc layout của user khác (có test) |
| QA/QC | Test và hiệu năng graph (#112) · benchmark chất lượng catalog (#106) · ma trận trình duyệt (Chrome, Edge, Firefox, Safari) và kích thước màn hình · báo cáo QA tuần 5 | Link chết trong catalog đang hiện < 2%; graph 30+ concept mượt trên laptop tầm trung |
| DevOps | Job làm mới catalog định kỳ, snapshot, seed dev (#105) · cache asset tĩnh · tag `v0.5` · CLI companion cho học viên **(stretch)** | Seed dev dựng catalog mẫu bằng 1 lệnh; job làm mới chạy hằng đêm trên staging |

## 📍 Tuần 6: Hoàn thiện chất lượng, bảo mật, phát hành

* **Mục tiêu**: Bản `v1.0` ổn định, an toàn, đạt mọi ngưỡng benchmark, được kiểm chứng bằng usability test với 50 sinh viên.
* **Sự kế thừa từ Tuần 5**: Toàn bộ hệ thống; tuần này không thêm tính năng mới, chỉ đo, sửa và đánh bóng.

| Mảng | Việc cần làm | Done when |
|---|---|---|
| UI/UX | Hoàn thiện 5 màn hình chính và S14 (graph) · trạng thái empty/loading/error · onboarding lần đầu · rà accessibility lần cuối (WCAG AA) · usability test với 50 sinh viên, sửa 10 vấn đề lớn nhất | ≥ 4/5 người dùng mới tự đi hết core loop không cần trợ giúp |
| AI | Cache câu trả lời theo trang · chạy full benchmark, sửa 10 lỗi lớn nhất · kiểm tra companion (không gây cảm giác tội lỗi, giới hạn thời gian hoạt động) · hiệu chỉnh ngưỡng điểm nguồn trên catalog | Benchmark ≥ 90% về trích dẫn và độ đúng |
| Database & Security | Index và tối ưu truy vấn (cả truy vấn graph) · rà OWASP Top 10 for LLM Applications · sửa phát hiện · quy trình xử lý sự cố 1 trang | Không còn lỗi mức nghiêm trọng cao |
| QA/QC | Load test 1.000 user giả lập · full regression · tổng hợp kết quả usability test · báo cáo QA cuối với bug còn mở và giới hạn | p95 < 2 giây ở 1.000 user |
| DevOps | Deploy production · dashboard (latency, lỗi, chi phí LLM, cờ an toàn, link chết) · runbook và lịch trực · tag `v1.0` | Production chạy, cảnh báo gửi về nhóm chat |

---

## 🚧 2. Sau tuần 6 (What continues)

| Việc | Vì sao không xong trong 6 tuần | Bắt đầu |
|---|---|---|
| Đo mức độ dùng lại sau 4 tuần (app có thật sự có ích không) | Cần người dùng thật dùng ít nhất 4 tuần | Tuần 6 |
| Nghiên cứu khả năng nhớ (recall study) | Cần độ trễ ≥ 1 tuần giữa học và kiểm tra | Tuần 5 |
| Mở rộng catalog đã xác minh lên ≥ 2.000 khóa học từ ≥ 100 trường (epic #92) | Mỗi connector cần rà giấy phép và điều khoản riêng | Tuần 5 |
| Hiệu chỉnh ước lượng thời lượng chặng theo dữ liệu thật | Cần ≥ 2 tuần `actual_minutes` của từng người | Tuần 6 |
| Nghiên cứu kết quả học tập 3 tháng | Cần trọn một học kỳ | Sau tuần 6 |

**Kiểm tra khối lượng (Honest load check):** Kế hoạch này khoảng **3 lần** khối lượng của MVP 4 tuần cho cùng 6 người. Dự kiến bỏ phần lớn mục **(stretch)** và làm mỏng một số tính năng tuần 4–5. Ưu tiên tuyệt đối: safeguard test và benchmark (đây là yêu cầu tối thiểu được chấm điểm).

## ⚠️ 3. Rủi ro chính

| # | Rủi ro | Giảm thiểu |
|---|---|---|
| 1 | LLM sinh câu hỏi sai hoặc không trích dẫn | Bước duyệt của người dùng, bắt buộc citation, mục tiêu 90% trên benchmark |
| 2 | PDF trích xuất kém (ảnh, công thức) | Thử cả 4 file slide ở tuần 1; cho phép dán text thay thế |
| 3 | Phạm vi phình to | Non-goals trong spec (gồm thương mại hóa và mobile); PM từ chối issue ngoài kế hoạch |
| 4 | Girlfriend mode lộ cho người dưới 18 tuổi | Age gate + feature flag + 50 test K-12; mode tắt mặc định |
| 5 | Quá tải người làm | Cắt (stretch) trước; không cắt safeguard và benchmark |
| 6 | Catalog thu thập nguồn sai giấy phép hoặc vi phạm `robots.txt` | ADR 004 (#93) chốt danh sách nguồn được phép; chỉ lưu metadata + link; nguồn không cho thu thập chỉ thêm tay |
| 7 | Graph lớn bị chậm hoặc khó đọc | Local graph mặc định, transitive reduction, chế độ danh sách; test hiệu năng (#112) |

---
**Tóm lược:** Tuần 1–2 **xây lõi** (slide → câu hỏi có trích dẫn → ôn tập) $\rightarrow$ Tuần 3 **thông minh hóa** (adaptive, companion) $\rightarrow$ Tuần 4 **an toàn cho K-12 và giáo viên** $\rightarrow$ Tuần 5 **đáng tin** (knowledge graph, nguồn đã xác minh) $\rightarrow$ Tuần 6 **hoàn thiện** (benchmark, bảo mật, hiệu năng, usability test).
