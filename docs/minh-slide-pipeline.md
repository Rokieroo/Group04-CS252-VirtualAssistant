# Bàn giao phần slide → concept → câu hỏi của Minh

Ngày: 02/11/2026. Phạm vi: #13, #9, #10 theo `docs/week1/DB_SECURITY.md` và `docs/week1/AI.md`.

## Trạng thái tích hợp khi xuất bản nhánh

Sau khi cập nhật remote ngày 02/11/2026, `origin/main` tại `31ca511` đã có các triển khai khác cho concept/item/ingest và migration `0002_scheduling_workspace`, `0003_source_visual_notes`. Bản này dùng giao diện hàm và ứng dụng API riêng, có migration `0002_concept_source_ids` cùng gốc `0001_initial`; **chưa tương thích để merge trực tiếp vào main hiện tại**. PR nháp dựa trên nhánh `codex/minh-scheduler-companion` nhằm review đúng phần chênh lệch. Trước khi đưa lên main, cần hợp nhất các giao diện, nối migration sau head hiện tại và chạy lại toàn bộ test trên code đã tích hợp. Các lệnh migration bên dưới dành cho nhánh này, không áp dụng nguyên trạng lên main mới.

## Đã triển khai

- **#13:** API health, tạo/liệt kê khóa học, upload và đọc các trang nguồn. Kiểm tra đuôi PDF, magic bytes, khả năng đọc và giới hạn file 20 MiB; giới hạn tổng request multipart 21 MiB ngay từ luồng nhận dữ liệu. Lưu từng trang bắt đầu từ 1 trong một transaction; >80% trang trắng trả cảnh báo `scanned_pdf`. Không lưu bản PDF gốc vào repository/database; bộ đọc multipart có thể dùng file tạm và đóng sau request. File trùng tên trả 409, giữ nguyên nội dung và citation cũ.
- **#9:** Trích concept theo cửa sổ 3 trang, bước 2, tách từng file; không gọi thêm cửa sổ đuôi đã được phủ. Gộp slug trùng hoặc tên chuẩn hóa có độ tương đồng ≥0,9. Kiểm tra JSON/Bloom/trang nguồn; loại concept trích trang ngoài cửa sổ. Giữ `source_pages` để hiển thị và `source_ids` để không nhầm tài liệu có cùng số trang.
- **#10:** Sinh 3–5 câu, có MCQ và short answer với rubric 2–4 tiêu chí; numeric tùy chọn. Đưa tối đa 3 trang không rỗng vào prompt; bỏ citation ngoài danh sách. Sau lọc mà không đủ số lượng/loại câu thì từ chối cả bộ. Câu lưu ở trạng thái `draft`, cần người duyệt nội dung trước khi dùng học.
- Prompt phiên bản `extract_v1`, `generate_v1`; temperature 0,2. Text slide và metadata được mã hóa trong khối dữ liệu không đáng tin cậy; delimiter trong dữ liệu được escape. Đây là lớp giảm rủi ro prompt injection, không phải bảo đảm model miễn nhiễm.
- Mọi đường đọc/ghi dữ liệu kiểm tra chủ sở hữu; dữ liệu người khác trả 404. Lỗi trả `{"error":{"code":"...","message":"..."}}`, không đưa lỗi provider/thông tin nhạy cảm ra response.

## Khởi chạy

Trong môi trường Python của dự án:

```powershell
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.api.main:app --app-dir src --host 127.0.0.1 --port 8001
```

Swagger: `http://127.0.0.1:8001/docs`. Cấu hình qua `.env` theo `.env.example`:

- `DATABASE_URL`: database Study Companion; tách với `PATHLY_DATABASE_URL` của Scheduler.
- `JWT_SECRET`: ít nhất 32 byte ngẫu nhiên, dùng chung với module #14. Không có giá trị mặc định. Thiếu cấu hình → 503; thiếu/sai/hết hạn token hoặc tài khoản không tồn tại → 401.
- `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`: module LLM của #8. `fake` mặc định không gọi mạng; khi không được cấp bảng đáp án test, FakeLLM trả `{}` nên API báo model output không hợp lệ thay vì bịa câu trả lời.

Database mới nên tạo qua Alembic trước khi chạy API. Với database cũ đã quản lý bằng Alembic: `python -m alembic upgrade head` thêm `concepts.source_ids` mà không sửa dữ liệu cũ. Concept cũ chưa có nguồn chính xác sẽ từ chối sinh câu hỏi; chạy đề xuất lại và xác nhận lại để thu thập nguồn. Concept đã xác nhận được giữ nguyên khi đề xuất lại; muốn bổ sung nguồn phải bỏ xác nhận trước.

Nếu database từng tạo bằng `python dev.py db init` và chưa có bảng `alembic_version`, chỉ `stamp` sau khi kiểm tra schema thực tế: schema cũ thiếu `source_ids` tương ứng `0001_initial`, schema mới đã có cột này tương ứng `head`. Không chạy lại migration tạo bảng trên database đã tồn tại; sao lưu trước thao tác quản trị. API phát hiện thiếu cột và dừng với hướng dẫn migration.

## Ghép với Thịnh (#14) và Thắng (#11)

Module #14 cấp JWT HS256 có `sub=users.id` và `exp`, ký bằng `JWT_SECRET`. Dependency `app.api.auth.current_user` là điểm ghép; bản này không triển khai đăng ký, đăng nhập, khóa tài khoản hoặc tuổi người dùng của #14. Session của Scheduler cũ dùng opaque token nên không dùng trực tiếp cho API mới.

Khi #11 chưa có, API chọn tối đa 3 trang theo `source_ids` của concept như phương án dự phòng đã ghi trong AI.md. Khi ghép BM25, thay khâu chọn trang tại `create_items`; `generate_items(concept, sources, client)` nhận danh sách trang đã xếp hạng và vẫn kiểm tra citation. Chỉ được truy xuất trang trong khóa học của chủ tài khoản.

## Hợp đồng API

Tất cả đường dẫn bên dưới có tiền tố `/api/v1`. Trừ health, gửi `Authorization: Bearer <JWT>`.

| Phương thức | Đường dẫn | Input / kết quả |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| POST | `/courses` | JSON `title`, tùy chọn `level`, `language`; trả course, 201 |
| GET | `/courses` | `{"courses":[...]}` |
| POST | `/courses/{id}/sources` | multipart field `file`; trả `file_name`, `pages`, `status`, `warnings`, 201 |
| GET | `/courses/{id}/sources` | `{"sources":[{"id","file_name","page","text",...}]}` |
| POST | `/courses/{id}/concepts:propose` | Không cần body; trả `concepts`, `prereqs:[]`; đề xuất lặp giữ ID |
| GET | `/courses/{id}/concepts` | Concept kèm `source_pages`, `source_ids`, `confirmed` |
| PATCH | `/concepts/{id}` | `{"confirmed":true}` sau khi người dùng duyệt |
| POST | `/concepts/{id}/items:generate` | Không cần body; concept phải xác nhận; trả item draft kèm nguồn file/trang |
| GET | `/concepts/{id}/items` | Danh sách draft kèm choices/rubric và nguồn |

Thiếu kiến thức → mảng rỗng + `missing_knowledge`; không đủ câu hợp lệ sau lọc → `insufficient_cited_items`. Model output sai → 502 `invalid_llm_response`, không lưu một phần. Model/network lỗi → 502 `llm_unavailable`. Upload lỗi: 400 `invalid_pdf`, 413 `file_too_large`, 415 `not_pdf`, 409 `source_conflict`.

## Kiểm tra và nghiệm thu còn lại

```powershell
python -m pytest tests/ -q
python -m ruff check .
python dev.py db scan-secrets
python dev.py ai benchmark validate
```

Bộ test dùng PDF sinh trong test, database tạm và FakeLLM. Có ca tích hợp PDF → concept → xác nhận → item draft; phân quyền đọc/ghi; token sai/hết hạn; PDF trùng tên; JSON lỗi; nguồn bịa; nguồn trùng số trang giữa 4 file; upload chia nhỏ nhiều file bị chặn trước xác thực; nâng cấp database giữ dữ liệu cũ.

Kết quả ngày 02/11/2026: **116 test Python passed**, Ruff sạch, quét secret cho file đang theo dõi và xác thực 20 case benchmark đều qua; `git diff --check` qua. Reviewer độc lập xác nhận hai lỗi quan trọng đã được sửa, không còn phát hiện Important/Critical trong các phần sửa. OpenAPI cho frontend: [study-openapi.json](study-openapi.json).

Chưa có bốn PDF môn học trong checkout nên chưa điền thống kê trích xuất/đánh giá concept và bảng duyệt 20 câu trong tài liệu tuần 1. Chưa gọi model thật và chưa xác minh chất lượng nội dung hoặc tương thích schema qua provider live. Chưa chạy PostgreSQL thật trong lượt này. Các kết quả này cần được ghi từ nghiệm thu thực tế; không suy ra từ FakeLLM. UI học tập chưa ghép vào API mới; xem Swagger và test tích hợp để bàn giao contract cho nhóm UI.
