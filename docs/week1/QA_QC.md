# Tasks for QA/QC (Tuần 1: Test Plan, Benchmark, Integration Tests, Báo cáo tuần)

Tài liệu này mô tả chi tiết nhiệm vụ QA/QC tuần 1 (Lê Hồng Đăng): quy trình kiểm thử hằng tuần, cách viết benchmark, checklist review PR và báo cáo thứ Sáu.

> **Lưu ý cập nhật Spec 3.0:** Tài liệu này phản ánh nhiệm vụ Sprint Tuần 1. Kể từ Sprint 2, dự án áp dụng chuẩn **Spec 3.0** (`docs/roadmap/APP_SPECIFICATION.md`) với 18 use cases (UC-01 đến UC-18). Các use case Tuần 1 đã được chuẩn hóa lại trong `docs/qa/TEST_PLAN.md` và `eval/benchmark.jsonl`.

## 🎯 Sứ mệnh tuần 1

Đặt **thước đo chất lượng** ngay từ tuần đầu: kế hoạch kiểm thử, 20 case benchmark, integration test cho mọi tính năng mới và báo cáo QA mỗi thứ Sáu.

Dưới đây là các hạng mục công việc cần hoàn thiện:

- [X] **Task 1: Test plan + benchmark 20 case + báo cáo tuần (#15, 10 giờ)**
  - **Test plan**: `docs/qa/TEST_PLAN.md`.
  - **Benchmark**: `eval/benchmark.jsonl` từ 6 lên ≥ 20 case, đủ 4 kind.
  - **Báo cáo**: `docs/qa/reports/week-1.md` (template đã tạo bằng `python dev.py qa report --week 1`).
- [X] **Task 2: Integration test ingest, retrieval, auth (#16, 10 giờ)**
  - **Fixture**: `client`, `user_a`, `user_b`, `sample_pdf` trong `tests/conftest.py`.
  - **Số lượng**: ≥ 12 test, chạy offline, không cần API key.
  - **Review**: PR của #11, #13, #14 theo checklist bên dưới.

---

## 🔄 Quy trình QA hằng tuần (dùng cho cả 6 tuần)

| Ngày | Việc |
| --- | --- |
| Thứ Hai | Đọc issue của tuần, viết danh sách test cần có cho mỗi issue, comment vào issue |
| Thứ Ba–Năm | Review PR trong 24 giờ; viết integration test khi PR tính năng mở |
| Thứ Năm | Chạy `python dev.py devops ci` trên `main`; thêm case benchmark cho tính năng mới |
| Thứ Sáu | Điền báo cáo QA tuần, trình bày 2 phút trong demo |

## 🧪 Viết case benchmark

Mỗi dòng trong `eval/benchmark.jsonl`:

```json
{"id": "B007", "use_case": "UC-12", "kind": "normal",
 "question": "Hai loại yêu cầu (requirement) chính trong problem framing là gì?",
 "expected": "Functional và non-functional; trích dẫn đúng slide",
 "source": "CSC10014_2026_Week01_Problem_Framing.pdf#<trang>"}
```

| Trường | Quy tắc |
| --- | --- |
| `id` | `B` + 3 chữ số, không trùng |
| `use_case` | `UC-01` … `UC-18` (spec mục 3) |
| `kind` | `normal` · `missing_knowledge` (không có trong tài liệu, phải trả "không tìm thấy") · `privacy` (đòi dữ liệu người khác) · `safety` (đòi đáp án bài graded, companion sai mode) |
| `expected` | Hành vi mong đợi, đủ rõ để 2 người chấm giống nhau |
| `source` | `<tên file>#<trang>` đã mở PDF kiểm tra tận mắt; `null` nếu không có nguồn |

**Phân bổ tuần 1 (≥ 20):** 10 normal · 4 missing_knowledge · 3 privacy · 3 safety. Mục tiêu 60 case ở tuần 3 và 100 ở tuần 6.

## ✅ Checklist review PR

- [X] Tên nhánh, tiêu đề PR, commit đúng `docs/guidelines/`
- [X] Có test cho code mới; test cả trường hợp lỗi, không chỉ trường hợp đúng
- [X] CI xanh; tự chạy `python dev.py devops ci` ở máy mình
- [X] Không secret, không dữ liệu cá nhân thật, không log nội dung nhạy cảm
- [X] Code AI: output LLM được kiểm tra định dạng trước khi lưu
- [X] Đã cập nhật tài liệu trong `docs/week1/`

## 🐞 Mức độ bug

| Mức | Định nghĩa | Thời hạn sửa |
| --- | --- | --- |
| Blocker | Chặn demo hoặc lộ dữ liệu / secret | Trong ngày |
| Major | Sai chức năng chính, có cách né | Trong tuần |
| Minor | Giao diện, câu chữ | Tuần sau |

Mỗi bug: issue label `bug` + label role + milestone tuần; ghi vào Bug log của báo cáo tuần.

## 🤝 Phối hợp với role khác

| Với | Cần gì | Khi nào |
| --- | --- | --- |
| AI (Minh) | Review 5 case `normal`; chọn `MIN_SCORE` cùng Thắng | Thứ Ba–Tư |
| DB&Security | Fixture DB tạm, PDF mẫu | Thứ Tư |
| UI/UX | Checklist test thủ công Upload + Concept editor | Thứ Năm |
| DevOps | Thêm bước test vào CI | Thứ Hai |

## 📊 Kết quả tuần 1 (điền khi xong)

| Chỉ số | Kết quả |
| --- | --- |
| Số case benchmark | _..._ |
| Số test tự động (unit + integration) | _..._ |
| Bug mở / đã đóng | _... / ..._ |

## 🌿 Git Workflow & Branching

- Nhánh: `qa-dang/<issue>-<task>`, ví dụ `qa-dang/15-test-plan-benchmark`.
- Commit: `test(qa): add 14 benchmark cases`, `docs(qa): add week 1 report`.
