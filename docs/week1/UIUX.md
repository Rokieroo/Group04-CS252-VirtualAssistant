# Tasks for UI/UX (Tuần 1: Wireframe, App Shell, Upload & Concept Editor)

Tài liệu này mô tả chi tiết nhiệm vụ tuần 1 của nhóm UI/UX (Nguyễn Quốc Thịnh, Lê Phan Đức Mân): vì sao làm, làm theo thứ tự nào, chuẩn thiết kế phải theo và phối hợp với các role khác.

## 🎯 Sứ mệnh tuần 1
Thiết kế và dựng phần đầu tiên của luồng chính, **tải slide lên và xác nhận concept**, sao cho tuần 2 chỉ cần đổi lớp API mock sang API thật là chạy.

Dưới đây là các hạng mục công việc cần hoàn thiện:

- [x] **Task 1: Wireframe 5 màn hình chính (#5, Thịnh, 8 giờ)** → [Wireframes](#-wireframes-5)
  - **Màn hình**: S3 Upload, S4 Concept editor, S6 Review session, S8 Ask panel, S10 Companion panel (định nghĩa ở spec mục 5).
  - **Kích thước**: desktop 1440×900 và mobile 390×844.
  - **Trạng thái**: empty, loading, error cho từng màn hình.
  - **Duyệt**: ≥ 2 người khác role comment trên Figma trước thứ Tư.
  *(Ghi chú PM: Thịnh vẽ thiết kế, Mân code (Developer). S6, S8, S10 chưa code trong tuần 1 nhưng phải vẽ ngay để AI biết dữ liệu UI cần.)*
- [ ] **Task 2: Merge Pathly + design tokens + app shell (#6, Mân, 10 giờ)**
  - **Merge**: `codex/pathly-ui` vào `main` qua nhánh `uiux-man/6-pathly-shell`.
  - **Tokens**: CSS variables màu, chữ, khoảng cách, bo góc, dark mode.
  - **Shell**: header, điều hướng 5 mục (dưới đáy trên mobile), đăng nhập/đăng ký mock có validate.
- [ ] **Task 3: Màn hình Upload + Concept editor với mock (#7, Mân, 12 giờ)**
  - **API mock**: `ui/src/api/courses.ts`, đúng định dạng spec mục 8.1–8.2.
  - **Upload**: chỉ PDF, ≤ 20 MB, tiến trình, 3 loại lỗi.
  - **Concept editor**: rename, merge, delete (undo 5 giây), add prerequisite, chặn vòng lặp.

---

## 📐 Chuẩn thiết kế (Design rules)

| Quy tắc | Chi tiết |
|---|---|
| Lưới và khoảng cách | Bước 4 px; khoảng giữa các khối 16 px; lề mobile 16 px |
| Chữ | Inter; 14 (phụ), 16 (thân), 20 (tiêu đề khối), 24 (tiêu đề trang) |
| Màu | Chỉ dùng token, không mã màu cứng; tương phản WCAG AA (4.5:1 cho chữ thường). Màu nhấn (accent) không viết thẳng mã màu: dùng `--color-primary`, `--color-tint`, `--gradient-brand`… (đều suy ra từ `--accent-a` / `--accent-b`) để đổi theo lựa chọn của người dùng |
| Chuyển động | Dùng token `--ease-standard` / `--ease-decelerate` và `--duration-fast/base/slow` (150/220/320 ms); chỉ animate `transform` và `opacity`; không dùng `filter: blur()` cho thứ chạy liên tục (máy không có GPU phải vẽ lại mỗi khung hình); `prefers-reduced-motion` tắt hết |
| Vùng bấm | ≥ 44×44 px |
| Trích dẫn | Mọi nội dung do AI tạo có citation chip `Tên file · tr. N` hoặc nhãn "không có nguồn" |
| Ngôn ngữ | Tiếng Việt mặc định; thuật ngữ môn học giữ như slide |
| Companion | Girlfriend mode hiển thị khóa (ổ khóa + "Chỉ dành cho người dùng 18+ đã xác minh"), không hiện hình ảnh lãng mạn khi chưa mở |

## 🎨 Tùy chỉnh giao diện (Appearance)

Người dùng chọn màu nhấn và chế độ sáng/tối trong **Settings → Appearance**. Lựa chọn áp dụng ngay, lưu theo thiết bị (`localStorage`, khóa `pathly.appearance.v1`) và được áp dụng trước lần render đầu nên không bị nháy màu mặc định. Reset demo (`pathly.demo.v1`) không xóa lựa chọn này.

| Màu nhấn | `--accent-a` → `--accent-b` | Tương phản chữ trắng (thấp nhất) |
|---|---|---|
| Violet (mặc định) | `#6654d9` → `#c2417c` | 4.84:1 |
| Ocean | `#1f6fd1` → `#0f7a8a` | 4.94:1 |
| Forest | `#1f7a4d` → `#3f7a12` | 5.24:1 |
| Sunset | `#c2410c` → `#be185d` | 5.18:1 |
| Slate | `#475569` → `#334155` | 7.58:1 |

Chế độ: **Match device** (theo `prefers-color-scheme`), **Light**, **Dark**. Màu sáng/tối viết bằng `light-dark()` nên ép một chế độ chỉ cần đổi `color-scheme`.

**Thêm một màu nhấn mới:**
1. Thêm khối `[data-accent="ten-moi"] { --accent-a: …; --accent-b: …; }` trong `ui/src/styles.css`.
2. Thêm `{ id: "ten-moi", label: "…" }` vào `ACCENTS` trong `ui/src/features/appearance/appearance.ts`.
3. Kiểm tra chữ trắng đạt ≥ 4.5:1 ở cả hai đầu và điểm giữa của gradient trước khi merge.

Code: `ui/src/features/appearance/` (`AppearanceStore` + `AppearancePicker`, có test).

## 🧪 Câu chữ cho lỗi (Error copy)

| Tình huống | Câu hiển thị |
|---|---|
| File không phải PDF | "Hiện chỉ hỗ trợ file PDF." |
| File > 20 MB | "File lớn hơn 20 MB. Hãy tách file hoặc nén lại." |
| PDF chỉ có ảnh | "Không đọc được chữ trong file này. Bạn có thể dán nội dung trang cần học." |
| Tạo vòng lặp prerequisite | "Thêm cạnh này sẽ tạo vòng lặp. Hãy bỏ một cạnh trước." |
| Mất mạng | "Mất kết nối. Thay đổi của bạn sẽ được lưu khi có mạng lại." |

## 🤝 Phối hợp với role khác

| Với | Cần gì | Khi nào |
|---|---|---|
| AI (Minh) | Danh sách trường của concept và item để vẽ đúng | Thứ Hai |
| DB&Security (Minh) | Mã lỗi thật của upload (400/413/415, `warning: scanned_pdf`) | Thứ Ba |
| DB&Security (Thịnh) | Định dạng request/response auth | Thứ Ba |
| QA (Đăng) | Checklist test thủ công cho 2 màn hình | Thứ Năm |
| DevOps (Đăng) | Cấu hình Vercel cho `ui/` | Thứ Năm |

## 🖼️ Wireframes (#5)

Low-fidelity (xám trắng) cho 5 màn hình chính, desktop 1440×900 và mobile 390×844, kèm empty / loading / error và luồng “lần đầu sử dụng” (spec mục 4.1).

- **Bản vẽ**: mở [`docs/wireframes/index.html`](../wireframes/index.html) trong trình duyệt. Bốn phần Wireframes, States, Components, Flows tương ứng bốn page dự kiến trên Figma. Ở phần Flows, bấm vào một khung để sang bước tiếp theo.
- **Figma**: kết nối Figma lỗi khi làm task này nên bản vẽ nằm trong repo dạng HTML. Khi có file `Group04 - Study Companion` trên Figma, import các ảnh bên dưới (hoặc trang HTML) vào rồi dán link vào bảng kết quả.
- **Cập nhật ảnh** sau khi sửa `index.html`: `python dev.py ui install` một lần, rồi `node docs/wireframes/capture.mjs`.
- **Duyệt**: ≥ 2 người khác role (ít nhất 1 AI, 1 QA) approve PR này, đi theo luồng 4.1 trong phần Flows mà không bị kẹt ở màn hình nào.

| Màn hình | Mặc định | Trạng thái (mobile) |
|---|---|---|
| S3 Upload | [desktop](../wireframes/img/s3-default-d.png) · [mobile](../wireframes/img/s3-default-m.png) | [empty](../wireframes/img/s3-empty-m.png) · [loading](../wireframes/img/s3-loading-m.png) · [error](../wireframes/img/s3-error-m.png) |
| S4 Concept editor | [desktop](../wireframes/img/s4-default-d.png) · [mobile](../wireframes/img/s4-default-m.png) | [empty](../wireframes/img/s4-empty-m.png) · [loading](../wireframes/img/s4-loading-m.png) · [error](../wireframes/img/s4-error-m.png) |
| S6 Review session | [desktop](../wireframes/img/s6-default-d.png) · [mobile](../wireframes/img/s6-default-m.png) · [sau khi nộp (desktop)](../wireframes/img/s6-submitted-d.png) · [sau khi nộp (mobile)](../wireframes/img/s6-submitted-m.png) | [empty](../wireframes/img/s6-empty-m.png) · [loading](../wireframes/img/s6-loading-m.png) · [error](../wireframes/img/s6-error-m.png) |
| S8 Ask panel | [desktop](../wireframes/img/s8-default-d.png) · [mobile](../wireframes/img/s8-default-m.png) | [empty](../wireframes/img/s8-empty-m.png) · [loading](../wireframes/img/s8-loading-m.png) · [error](../wireframes/img/s8-error-m.png) |
| S10 Companion panel | [desktop](../wireframes/img/s10-default-d.png) · [mobile](../wireframes/img/s10-default-m.png) | [empty](../wireframes/img/s10-empty-m.png) · [loading](../wireframes/img/s10-loading-m.png) · [error](../wireframes/img/s10-error-m.png) |

**Luồng lần đầu sử dụng (4.1)**: S1 Đăng ký → S2 Tạo môn → S3 Upload → S3 đang trích → S4 đang đề xuất → S4 sửa và xác nhận → S5 duyệt câu hỏi → S6 ôn tập → S6 chấm và đánh giá → S7 kết quả → S10 companion chào. S1, S2, S5, S7 chỉ vẽ ở mức đủ để đi hết luồng.

![Luồng lần đầu sử dụng](../wireframes/img/flows.png)

| Desktop | Mobile |
|---|---|
| ![S3 Upload desktop](../wireframes/img/s3-default-d.png) | ![S3 Upload mobile](../wireframes/img/s3-default-m.png) |
| ![S4 Concept editor desktop](../wireframes/img/s4-default-d.png) | ![S4 Concept editor mobile](../wireframes/img/s4-default-m.png) |
| ![S6 Review session desktop](../wireframes/img/s6-default-d.png) | ![S6 Review session mobile](../wireframes/img/s6-default-m.png) |
| ![S8 Ask panel desktop](../wireframes/img/s8-default-d.png) | ![S8 Ask panel mobile](../wireframes/img/s8-default-m.png) |
| ![S10 Companion panel desktop](../wireframes/img/s10-default-d.png) | ![S10 Companion panel mobile](../wireframes/img/s10-default-m.png) |

Mode girlfriend luôn hiện ổ khóa và câu “Chỉ dành cho người dùng 18+ đã xác minh” khi chưa mở; tài khoản K-12 chỉ có Buddy hoặc Mentor. Thành phần dùng lại (nút, citation chip, nhãn “không có nguồn”, Again/Hard/Good/Easy, ô tự luận, thông báo lỗi): [Components](../wireframes/img/components.png).

## 📊 Kết quả tuần 1 (điền khi xong)

| Hạng mục | Link / kết quả |
|---|---|
| Figma | _chưa có_ (bản vẽ tạm: [`docs/wireframes/index.html`](../wireframes/index.html), xem [Wireframes](#-wireframes-5)) |
| Ảnh chụp app shell (desktop, mobile) | _chưa có_ |
| Staging UI | _chưa có_ |

### Hạn chế & Hướng cải thiện
| # | Hạn chế | Hướng cải thiện |
|---|---|---|
| 1 | Dữ liệu concept là mock | Nối API thật của #9 ở tuần 2 |

## 📂 Codebase Guidelines
- Component trong `ui/src/components/`, trang trong `ui/src/pages/`, gọi API chỉ qua `ui/src/api/`.
- Lệnh: `python dev.py ui install | dev | build | test`.
- PR UI bắt buộc có ảnh chụp màn hình desktop và mobile.

## 🌿 Git Workflow & Branching
- Nhánh: `uiux-<name>/<issue>-<task>`, ví dụ `uiux-thinh/5-wireframes`, `uiux-man/7-upload-concepts`.
- Commit: `feat(ui): add upload dropzone`, `style(ui): apply spacing tokens`.
- Xem [docs/guidelines/GIT_WORKFLOW.md](../guidelines/GIT_WORKFLOW.md).
