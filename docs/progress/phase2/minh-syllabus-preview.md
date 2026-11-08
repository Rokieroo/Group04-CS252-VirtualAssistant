# Bổ sung preview cho parser syllabus — Minh, theo sau PR #89

Ngày kiểm tra: 04/11/2026. Nhánh: `ai-minh/59-syllabus-parser`, đã hợp nhất `origin/main` tại `026d7b9` (PR #89).
Phân công: [#59 Parser syllabus](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/59).
Phần vetting/curator [#62](https://github.com/Rokieroo/Group04-CS252-VirtualAssistant/issues/62) đã có trên main qua PR #87.

## Đã thực hiện

- `app.syllabus.preview_syllabus(pages, client=None)` trả bản xem trước JSON gồm `course`, `outcomes`, `weeks`, `assessments`, `textbooks`. Khi có client, hàm dùng lại `extract_syllabus(llm, pages)` và prompt/schema của PR #89 rồi kiểm tra bằng chứng chặt hơn. Giữ nguyên giao diện parser, CLI `ai syllabus`, evaluator `eval/run_syllabus.py` và tài liệu `AI.md` đã có trên main.
- Mỏ neo deterministic: `Tuần N`/`Week N`, `CLO1`/`CLO 1`, phần trăm có dấu phẩy, ngày ISO và ngày Việt Nam `dd/mm/yyyy`. Không suy đoán năm hoặc lấy ngày máy làm ngày học kỳ.
- Có thể đọc offline các dòng gắn nhãn rõ. Khi truyền `LLMClient`, dùng prompt `syllabus_v1.txt`, JSON schema và temperature 0,1 từ parser chính; không có adapter vendor/prompt trích xuất thứ hai. Dữ liệu trang và mỏ neo nằm trong `document_text`/`syllabus_anchors`; các delimiter được xử lý qua `app.llm.blocks` dùng chung.
- Mỗi metadata của course có `{value, source_page}` riêng vì chúng có thể nằm ở các trang khác nhau. CLO, tuần, đánh giá, giáo trình mang `source_page` ở cấp dòng; nội dung chính phải có trong trang được trích dẫn sau chuẩn hóa khoảng trắng/chữ hoa. Ngày, số tuần, mã CLO, trọng số được đối chiếu với mỏ neo của trang. Trường thiếu nguồn hoặc không có bằng chứng bị bỏ và sinh cảnh báo chặn.
- Cảnh báo: tổng trọng số ngoài 100% ± 1; tuần trùng/không tăng; chủ đề nằm ở nhiều tuần; tuần trống; hạn thiếu hoặc ngoài lịch/học kỳ; ngày học kỳ đảo ngược. Tuần ước lượng được gắn nhãn và kiểm tra với độ dài học kỳ nếu có. `can_confirm` chỉ thể hiện kết quả kiểm tra, không tự xác nhận/lưu dữ liệu.
- JSON sai schema, giá trị không hữu hạn, kiểu boolean giả số và response rỗng bị từ chối. Lỗi API không chứa response/provider text. Slide không có dấu hiệu syllabus bị từ chối trước khi gọi model.
- CLI đọc PDF/DOCX/text qua ingest #49. API preview có kiểm tra chủ sở hữu và chọn đúng một tài liệu; không ghép các trang có cùng số của nhiều file.

## Chạy thử

Tại thư mục gốc, dùng Python trong `.venv` đã cài `requirements.txt`:

```powershell
python dev.py ai syllabus-preview eval/syllabus/01_csc10014_problem_framing.txt
python dev.py ai syllabus-preview eval/syllabus/02_cs102_database_systems.docx
python dev.py ai syllabus-preview path/to/syllabus.pdf --llm
```

Mặc định đọc offline, không gọi mạng. `--llm` dùng `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY` trong môi trường/`.env`. `fake` không có bảng response sẽ báo output không hợp lệ, không tạo dữ liệu giả để dùng học.

## Ghép với backend/UI

`POST /api/v1/courses/{course_id}/syllabus:parse`, gửi bearer token của tài khoản sở hữu course.

```json
{"text":"CLO1: Frame a problem.\nWeek 1: Problem framing","use_llm":false}
```

Hoặc upload bằng `POST /courses/{id}/sources` (multipart `kind=syllabus`) rồi gửi:

```json
{"file_name":"syllabus.pdf","use_llm":true}
```

Phải gửi đúng một trong `text` và `file_name`. Nguồn phải thuộc course hiện tại và có `kind=syllabus`. Response chứa `parsed`, `warnings[{code,message,blocking,path}]`, `pages`, `method`, `prompt_version`, `status=draft`, `can_confirm`, `file_name`. Text/DOCX dùng trang logic của ingest; PDF giữ trang vật lý. Mọi số trang trong một response chỉ thuộc tài liệu được chọn.

Lỗi: 401 chưa đăng nhập; 404 course/tài liệu không thuộc tài khoản hoặc không tồn tại; 422 input không hợp lệ/`not_a_syllabus`; 502 `invalid_llm_response`; 503 `llm_unavailable`. Preview chưa lưu bản nháp vào `syllabi`, không thay đổi endpoint nhập liệu của #63. Consumer lưu/xác nhận phải gọi `validate_syllabus(edited_parsed, original_pages)` và kiểm tra `can_confirm` khi áp dụng contract xác nhận của spec 8.2. Không dùng trường `status` do client gửi làm bằng chứng đã xác nhận. OpenAPI được cập nhật tại `docs/openapi.json`.

## Đánh giá tái lập

```powershell
python eval/run_syllabus_preview.py --output docs/progress/phase2/syllabus-results.json
python eval/run_syllabus_preview.py --formats --output docs/progress/phase2/syllabus-format-results.json
python eval/run_syllabus_preview.py --llm --limit 1
python -m pytest tests/ -q
python -m ruff check .
python dev.py db scan-secrets
python dev.py ai benchmark validate
```

Evaluator truyền **chỉ trang tài liệu** vào parser, rồi mới đọc `.gold.json` để chấm. Không dùng gold làm FakeLLM response hoặc làm input cho thuật toán. Tuần là tập số tuần; chủ đề là cặp `(tuần, text)`; mốc là `(tên, hạn)`; trọng số là `(tên, phần trăm)`. F1 micro đếm cả false positive và false negative; không chỉ tính trên các dòng trả về. Dấu chấm cuối câu, chữ hoa và khoảng trắng được chuẩn hóa. Bộ này không chấm Bloom level, textbook, độ chính xác ngày hay khả năng khái quát ra syllabus khác.

| Bộ dữ liệu | Số bản | F1 tuần | F1 chủ đề | F1 mốc | F1 trọng số | Dòng/field thiếu citation |
|---|---:|---:|---:|---:|---:|---:|
| 10 file text từ #66, deterministic | 10 | 1,000 | 1,000 | 1,000 | 1,000 | 0 |
| Thêm 1 PDF + 2 DOCX có sẵn, deterministic | 13 | 0,960 | 0,960 | 0,947 | 0,947 | 0 |

Từng mẫu SYL-01 đến SYL-10 đều đạt F1 1,0 trên bản text; kết quả máy đọc được ở [syllabus-results.json](syllabus-results.json), kết quả thêm định dạng ở [syllabus-format-results.json](syllabus-format-results.json). Khi thêm định dạng, PDF mẫu CSC10014 khiến `pypdf` cảnh báo `incorrect startxref pointer` và một số dòng không được đọc đủ; DOCX dùng trang logic. Kết quả định dạng được báo riêng, không thay thế kết quả 10 bản text.

Sau khi ghép PR #89: **511 test Python passed**, trong đó **26 test preview/API** và **21 test parser/evaluator chính**; `python dev.py devops ci` (Ruff, toàn bộ test, quét secret, benchmark validation), kiểm tra tên nhánh và whitespace đều qua. Test dùng FakeLLM, database tạm và dữ liệu mẫu; test API cần chạy ngoài sandbox Windows trong phiên này do sandbox chặn socketpair nội bộ của TestClient.

## Giới hạn còn lại

- Kết quả trên là **deterministic với 10 mẫu có định dạng gắn nhãn tương tự**, chưa phải F1 của LLM hoặc syllabus thật đa dạng. Chưa chạy model thật trong phiên này; `--llm` cần chạy riêng khi có key/quota. FakeLLM kiểm tra đường code, schema, citation và lỗi, không đo năng lực đọc của model.
- Kiểm tra substring xác minh bằng chứng ở trang, không chứng minh model ghép đúng mọi trọng số/hạn với đúng dòng trên cùng một trang. Người học vẫn phải duyệt S4.
- Offline fallback chưa đọc bảng tùy ý, dòng qua nhiều trang, suy luận giáo trình hay tự chia lịch không có tuần. LLM giữ khả năng và giới hạn của parser chính; validator nhận thêm nhãn tuần ước lượng nếu consumer cung cấp, và cần thời gian học kỳ để xác minh. OCR và chế độ tự học/K-12 catalog thuộc các luồng riêng.
- Prompt data block giảm rủi ro injection; test delimiter không phải bằng chứng chống được mọi lệnh chèn với model thật.
- Lưu version, xác nhận có hiệu lực trong database, job nền, giao diện S4 và roadmap từ parsed đầy đủ cần ghép với #63/#68/#56. API preview là điểm bàn giao parser, không tự triển khai các phần này. Chưa chạy PostgreSQL trong phiên này; CI có job PostgreSQL.
