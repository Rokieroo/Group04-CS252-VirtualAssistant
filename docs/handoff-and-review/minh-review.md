# Rà soát phần việc của Minh — 28/10/2026

## Căn cứ và cách kiểm tra

Đối chiếu [slide phân công](../schedule/presentation_schedule_slide.svg), README và [tài liệu bàn giao](minh-handoff.md). Phần của Minh/Thắng là Backend & Scheduler và AI GF & LLM; Minh đã xác nhận làm cả hai.

Áp dụng Superpowers: requesting-code-review, systematic-debugging, test-driven-development và verification-before-completion. Một reviewer độc lập chỉ đọc code; các lỗi nghiêm trọng được tái hiện bằng kiểm thử trên database tạm trước khi sửa. Không thay đổi quyền trong workspace đang dùng để phục vụ kiểm thử.

## Các lỗi đã xử lý

| Vấn đề | Tác động | Cách sửa / chứng cứ |
| --- | --- | --- |
| Xóa task chạy đồng thời với check-in | Cả hai yêu cầu có thể thành công nhưng lịch sử vừa ghi bị xóa | Khóa theo assignee, đọc lại task và kiểm tra lịch sử trước khi xóa; test hai request thật chạy đồng thời |
| Cập nhật/chia sẻ dùng Task đã đọc trước khi lấy khóa | Có thể hủy task đã hoàn thành hoặc giảm thời lượng sai dữ liệu mới | Reload sau khóa, phát hiện assignee thay đổi và kiểm tra lại quyền/tiến độ |
| Lưu plan chạy xen với thay đổi availability/busy/task/share trên SQLite | Có thể lưu phiên học sau khi giờ rảnh đã bị xóa | Dùng cùng khóa process với planner/check-in cho các thao tác ảnh hưởng lịch; rollback trước khi nhả khóa khi có lỗi |
| Phiên quá giờ chưa check-in giữ hết phần việc còn lại | Replan không tạo phiên mới dù chưa ghi nhận phút học nào | Preview loại phần giữ chỗ quá giờ và báo số phiên; commit mới đánh dấu missed, giữ lịch sử và xếp lại công việc |
| Refresh nhóm không tải thành viên mới | Người mới chấp nhận lời mời chưa xuất hiện trong dropdown giao task | Refresh tải lại roster của nhóm đang chọn; chặn response của nhóm cũ ghi đè nhóm mới |
| Lưu preview sau phút bắt đầu bị lỗi và mất đề xuất | Người dùng đọc kế hoạch lâu rồi Save nhận 422, phải tạo preview lại | Nếu thời gian đã qua, Save chỉ tạo preview mới và yêu cầu xác nhận lại; lỗi request giữ đề xuất để thử lại |

Các ca hồi quy nằm trong `tests/test_review_regressions.py`. Reviewer đã kiểm tra lại ba sửa đổi về đồng thời/khóa và không còn phát hiện Important trong các đường xử lý đó. Điều này không thay thế nghiệm thu PostgreSQL thật.

## Kết quả xác minh

- Python: **57 passed**, gồm bốn ca hồi quy mới. Có một deprecation warning của TestClient về httpx/httpx2; không lọc/ẩn warning.
- Frontend: **9 passed**; TypeScript và Vite production build thành công bằng Node 24.22.1.
- Ruff, `pip check` và `git diff --check`: thành công.
- Browser: tái hiện Save preview cũ nhận 422 trước sửa; sau sửa, Save làm mới đề xuất, calendar chưa thay đổi, lần xác nhận kế tiếp mới lưu. Đã thấy phiên cũ thành missed và phiên mới planned, số phút hoàn thành vẫn 0.
- Backend đã được khởi động lại với mã mới; hợp đồng OpenAPI đã xuất lại.
- Ca kiểm thử thêm thành viên vào workspace đang chạy chưa thực hiện: automatic approval review từ chối vì tạo account/lời mời và mở rộng quyền thành viên. Không thử lại qua UI hay đường gián tiếp. Các ca invitation, ownership và sharing dùng database tạm trong suite đã qua; nghiệm thu UI hai tài khoản trên database live vẫn cần nhóm tự thực hiện hoặc cho phép rõ phạm vi test.

## Việc của Minh còn lại theo kế hoạch

| Ưu tiên | Phần việc | Trạng thái hiện tại | Điều kiện chốt |
| --- | --- | --- | --- |
| 1 | Nghiệm thu PostgreSQL (tuần 1, 5–7) | Schema/driver và CI đã chuẩn bị; chưa chạy với server PostgreSQL thật trên máy này | Có database test riêng; chạy suite với `PATHLY_TEST_DATABASE_URL`, xem kết quả CI và kiểm tra hai tài khoản thao tác đồng thời |
| 1 | Nghiệm thu Gemini hoặc OpenAI thật (UC-07/08) | Adapter, prompt, mood/personality, lịch sử riêng và fallback đã có; live provider chưa cấu hình | Đặt key/model trong backend `.env`; thử báo cáo, tired/stressed/happy và lỗi provider; kiểm tra câu trả lời không bịa tiến độ/lịch |
| 2 | Chốt ghép API với frontend cùng Thắng và nhóm UI (tuần 4, 6–7) | Workspace dùng API thật; năm trang khóa học cũ vẫn là demo localStorage | Nhóm thống nhất màn hình dùng khi bảo vệ; nếu dùng các trang demo cũ thì nhóm UI cần ghép API tương ứng, Minh/Thắng hỗ trợ contract |
| 2 | Bàn giao nhánh và chạy CI cùng nhóm | Mã đang ở working tree, chưa commit/push trong lượt này | Tạo/chọn nhánh phù hợp, review diff, mở PR; xác nhận job Python, PostgreSQL và UI xanh cùng Đăng |
| 3 | Demo/bảo vệ tuần 8 | Có demo tự động và hướng dẫn API | Minh nắm thuật toán greedy, giới hạn, schema/quyền và trình bày được luồng cá nhân + nhóm + AI thật |

Theo slide, CI/QA thuộc Đăng, các màn hình frontend thuộc Mân/Thịnh/Đạt; đây là phần phối hợp, không phải mặc định Minh phải viết lại toàn bộ frontend. Password reset, xác thực email, lịch lặp, calendar bên ngoài và hosting không được ghi là yêu cầu riêng của Minh trong slide này.

## Kịch bản Minh cần trình bày

1. Tạo goal/task, đặt deadline/priority và nhập availability/busy time.
2. Preview → đọc phần chưa xếp được → commit → calendar không trùng giờ bận.
3. Check-in một phần hoặc missed → replan → giữ lịch sử và không cộng phút học hai lần.
4. Mời một tài khoản test vào nhóm → người nhận chấp nhận → chia sẻ task → tìm giờ rảnh chung.
5. Chat với provider thật về tiến độ và mood; giải thích khi nào hệ thống chuyển offline.

Lệnh chạy, biến môi trường và API đầy đủ nằm trong [minh-handoff.md](minh-handoff.md). Các mục PostgreSQL/AI live vẫn cần nghiệm thu trước khi khẳng định hoàn tất toàn bộ phần việc.
