# Phase 2 — AI

## Parser syllabus (issue #59, spec mục 9)

### Luồng

1. `app.ingest.extract_pages` trích text theo trang (PDF, DOCX, TXT).
2. `app.syllabus.anchors.find_anchors`: nhận dạng deterministic ngày (VN `dd/mm/yyyy` và ISO),
   "Tuần N"/"Week N", phần trăm, mã CLO. Tài liệu không có tuần, phần trăm lẫn CLO bị trả
   `not_a_syllabus` **trước khi gọi LLM**.
3. `app.syllabus.extract.extract_syllabus`: prompt `prompts/syllabus_v1.txt`, text và mỏ neo nằm
   trong khối dữ liệu (`<syllabus_anchors>`, `<document_text>`), JSON schema 5 phần + `document_kind`,
   `temperature = 0.1`.
4. Cite-or-refuse: mục không chỉ ra trang đã hiển thị bị bỏ; `course` không có trang thì để trống
   cho người dùng nhập; mã CLO hoặc trọng số không xuất hiện trên trang nguồn bị xóa. Số giá trị
   bị bỏ thành cảnh báo `missing_source`.
5. `app.syllabus.checks.check_syllabus`: tổng trọng số 100% ± 1 (**chặn**), ngày ngoài học kỳ
   (**chặn**), tuần tăng dần không trùng, chủ đề chỉ thuộc 1 tuần, mốc kiểm tra có tuần hoặc ngày.

### Khi nào là `not_a_syllabus`

- Mỏ neo không có tuần, phần trăm lẫn CLO (không tốn lượt LLM).
- LLM phân loại `document_kind` khác `syllabus`.
- Sau khi làm sạch không còn bằng chứng: cần lịch ≥ 2 tuần, hoặc ≥ 2 mục có trọng số, hoặc mã
  CLO có thật trên trang. Tài liệu chỉ có **đúng 1 tuần** là slide của tuần đó, trừ khi có mã CLO:
  rubric của một milestone hay bảng điểm bài tập về nhà không đủ.

### Kết quả benchmark (2026-11-04)

`python eval/run_syllabus.py --refuse <slide>...`, Gemini (`gemini-3.5-flash-lite`, fallback
`gemini-3.1-flash-lite`), 10 syllabus trong `eval/syllabus/` (1 PDF, 2 DOCX, 7 TXT).

| Trường | F1 |
| --- | ---: |
| Tuần | 1.000 |
| Chủ đề | 1.000 |
| Mốc kiểm tra (tên + tuần hạn) | 1.000 |
| Trọng số | 1.000 |

- Giá trị không có trang nguồn: **0**.
- Slide bài giảng CSC10014 Week01, Week02, Week03: cả 3 bị nhận diện `not_a_syllabus`.
- `Week 0 - Orientation.pdf` **được** parse thành syllabus, đúng ý đồ: deck này chứa lịch 8 tuần,
  CLO1–CLO8 và bảng trọng số tổng 100%, tức chính là syllabus ở dạng slide.

Lỗi tìm được khi chạy và đã sửa: với Week02/Week03, model trả `document_kind = syllabus` và lấy
rubric Milestone 1 (20/20/25/20/15%) hoặc bảng điểm HW1–HW5 làm `assessments`. Quy tắc "đúng 1 tuần
mà không có CLO là slide" chặn được cả hai mà không phụ thuộc model.

### Chạy lại

```bash
python dev.py ai syllabus <file> [--json]       # một file
python eval/run_syllabus.py [--limit N] [--refuse slides.pdf ...]
```

Mỗi syllabus tốn 1 lượt gọi LLM; key Gemini miễn phí chỉ có ~20 lượt/ngày/model.
