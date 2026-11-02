# Kế hoạch kiểm thử (Test Plan) — Tuần 1

Tài liệu này mô tả phạm vi, các tầng kiểm thử, tiêu chí pass/fail và quy trình báo bug của dự án. Cập nhật mỗi tuần khi phạm vi đổi. Tham chiếu: spec mục 13.1 (safeguards) và 15 (metrics), `docs/week1/QA_QC.md`.

## 1. Phạm vi tuần 1 (Scope)

| Tính năng | Use case | Ghi chú |
| --- | --- | --- |
| Ingest PDF theo trang | UC-04 | Trích text deterministic, mỗi trang một bản ghi, gắn vào tài liệu chặng |
| Retrieval có trích dẫn | UC-12 | Top-5 trang trong tài liệu của chặng; dưới ngưỡng → "không tìm thấy" |
| Sinh câu hỏi (item generation) | UC-10 | 3–5 item draft từ concept của chặng, mỗi item có `source_id` hợp lệ |
| Auth và phân quyền | — | Đăng ký, đăng nhập, user chỉ thấy dữ liệu của mình |
| UI Upload + Concept editor | UC-04, UC-09 | Kiểm thử thủ công |

**Ngoài phạm vi tuần 1**: FSRS scheduler (UC-11), hint ladder đầy đủ (UC-13), companion (UC-14). Case benchmark cho các phần này đã có sẵn để đo khi tính năng xong.

## 2. Các tầng kiểm thử (Test layers)

| Tầng | Công cụ | Lệnh | Pass khi |
| --- | --- | --- | --- |
| Unit | pytest, vitest | `python dev.py qa test` · `cd ui && npm test` | 100% pass, không cần mạng hay API key |
| Integration (API + DB) | pytest + fixture `client`, `user_a`, `user_b`, `sample_pdf` (#16) | `python dev.py qa test` | 100% pass, chạy offline với `LLM_PROVIDER=fake` |
| Benchmark (AI quality) | `eval/benchmark.jsonl` | `python dev.py ai benchmark validate` · `stats` | Định dạng hợp lệ; khi có pipeline: ≥ 90% trích dẫn đúng trang (spec mục 15) |
| Red-team (safeguards) | Case `missing_knowledge`, `privacy`, `safety` | Chấm theo `expected` | 0 lần lộ đáp án item graded; 0 lần lộ dữ liệu người khác; "không tìm thấy" khi không có nguồn |
| Manual (UI) | Checklist với UI/UX | — | Không có bug Blocker/Major mở |
| CI | GitHub Actions | `python dev.py devops ci` | Ruff, pytest, scan-secrets, benchmark validate đều xanh |

## 3. Quy ước benchmark

- Mỗi dòng: `id`, `use_case`, `kind`, `question`, `expected`, `source` (xem `docs/week1/QA_QC.md`).
- `source` = `<tên file>#<trang>`, trong đó **trang là số trang của file PDF** (trang thứ mấy khi mở trong trình xem PDF, bắt đầu từ 1), **không phải** số "Page N" in trên slide. Lý do: hệ thống ingest và trích dẫn theo trang PDF. Lưu ý `Week 0 - Orientation.pdf` lệch 3 trang từ trang 40 trở đi (trang PDF 50 in "Page 53").
- Mỗi case `normal` phải được mở PDF kiểm tra tận mắt trước khi merge.
- `expected` phải đủ rõ để 2 người chấm cho cùng kết quả.

## 4. Mức độ bug (Severity)

| Mức | Định nghĩa | Thời hạn sửa |
| --- | --- | --- |
| Blocker | Chặn demo hoặc lộ dữ liệu / secret | Trong ngày |
| Major | Sai chức năng chính, có cách né | Trong tuần |
| Minor | Giao diện, câu chữ | Tuần sau |

## 5. Quy trình báo bug

1. Tạo issue với label `bug` + label role phụ trách (ví dụ `role: ai`), gắn milestone của tuần.
2. Mô tả: bước tái hiện, kết quả mong đợi, kết quả thực tế, mức độ.
3. Ghi vào **Bug log** của báo cáo tuần (`docs/qa/reports/week-<n>.md`).
4. Khi sửa: PR ghi `Closes #<issue>` và thêm test (hoặc case benchmark) tái hiện bug.

## 6. Lịch hằng tuần

| Ngày | Việc |
| --- | --- |
| Thứ Hai | Đọc issue của tuần, comment danh sách test cần có |
| Thứ Ba–Năm | Review PR trong 24 giờ; viết integration test khi PR tính năng mở |
| Thứ Năm | Chạy `python dev.py devops ci` trên `main`; thêm case benchmark |
| Thứ Sáu | Điền báo cáo QA tuần, trình bày 2 phút trong demo |
