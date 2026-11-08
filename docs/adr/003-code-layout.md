# ADR 003 — Bố cục code Python hai tầng

- **Trạng thái**: Đã chấp nhận
- **Ngày**: 2026-11-02
- **Liên quan**: Issue #48, đặc tả mục 6.1, ADR 001

## Bối cảnh (Context)

Phase 1 có hai nơi chứa logic:

- `src/app/`: `llm`, `concepts`, `items`, `retrieval`, `db`, không phụ thuộc web.
- `src/assistant/backend/`: route FastAPI, nhưng cũng chứa logic nghiệp vụ (`ingest.py`, `scheduler.py`, `companion.py`) và lớp truy cập dữ liệu (`services.py`).

Phase 2 thêm sáu part mới (đặc tả 6.1: `syllabus`, `roadmap`, `search`, `vetting`, `curator`, cùng `planner` mở rộng). Nếu không chốt ranh giới, logic mới sẽ rơi vào route, khó test và khó tái sử dụng từ CLI (`dev.py`) hay job nền.

## Quyết định (Decision)

### 1. Hai tầng, phụ thuộc một chiều

```text
src/assistant/backend/   tầng web: route, schema, dependency, nối DB
        │  import
        ▼
src/app/<part>/          tầng logic: thuần Python, mỗi part một nhiệm vụ (spec 6.1)
```

| Tầng | Được chứa | Không được chứa |
| --- | --- | --- |
| `src/app/<part>/` | Thuật toán, prompt, dataclass miền, client provider (LLM, HTTP), class có trạng thái riêng của part | `fastapi`, `starlette`, bất kỳ import nào từ `assistant.*`, ORM model của backend, `HTTPException` |
| `src/assistant/backend/` | `routes_*.py` (HTTP), `schemas.py` (Pydantic, OpenAPI), `dependencies.py`, cùng phần nối hạ tầng: `models.py`, `database.py`, `config.py`, `security.py`, `cache.py`, `services.py` | Quyết định nghiệp vụ: xếp lịch, chấm điểm, dựng prompt, đọc PDF |

- **Logic nhận và trả giá trị thuần.** Part trong `app/` nhận dataclass, tuple hoặc `Protocol`, không nhận ORM row hay request. Ví dụ: `app.planner.Planner` nhận `PlanLimits` (một `Protocol`), và `PlanRequest` của API thỏa nó mà không cần chuyển đổi. Kết quả trả về là `Plan`/`PlannedSession`; backend tự đổi sang `PlanOut`.
- **`services.py` là adapter.** Mỗi hàm đọc row, gọi part trong `app/`, ghi kết quả và commit. Ví dụ: `companion_reply` gom dữ kiện vào `CompanionContext`, gọi `Companion.reply`, lưu hai `ChatMessage`.
- **Đối tượng có vòng đời dài được tạo một lần.** `create_app` dựng `Companion(ChatProvider(...))` từ `Settings` và gắn vào `app.state`. Route chỉ lấy ra dùng.

### 2. Vị trí các part sau thay đổi

| Part (spec 6.1) | Thư mục | Trạng thái |
| --- | --- | --- |
| `ingest` | `src/app/ingest/` | Chuyển từ `backend/ingest.py` |
| `planner` | `src/app/planner/` | Chuyển từ `backend/scheduler.py`, tách `intervals.py` (phép toán khoảng) và `engine.py` (class `Planner`) |
| `companion` | `src/app/companion/` | Chuyển từ `backend/companion.py`, tách `persona.py` (prompt, mode, cổng 18+) và `chat.py` (`Companion`, `ChatProvider`, `CompanionContext`) |
| `syllabus`, `roadmap`, `search`, `vetting`, `curator` | `src/app/<part>/` | Package rỗng, làm ở phase 2 |
| `retrieve`, `itemgen`, `llm` | `src/app/retrieval/`, `src/app/items/`, `src/app/llm/` | Giữ tên cũ để không đổi import đang dùng |

Lưu ý tên: `scheduler` trong spec 6.1 là phần chọn câu ôn FSRS, khác với bộ xếp lịch học. Vì vậy bộ xếp lịch cũ được đặt tên `planner`.

### 3. Thực thi (Enforcement)

`tests/test_layers.py` đọc AST mọi file `.py` dưới `src/app/`, kể cả import nằm trong hàm, và fail nếu thấy `fastapi`, `starlette` hoặc `assistant`. Test chạy trong `pytest tests/`, tức là trong job CI `lint-and-sanity-check` và `postgres-integration`, cũng như `python dev.py devops ci`.

## Hệ quả (Consequences)

**Tích cực**

- Part mới ở phase 2 có chỗ đặt rõ ràng; review chỉ cần hỏi "file này có import FastAPI không?".
- Logic test được không cần `TestClient` hay database (xem `tests/test_companion.py`, `tests/test_scheduler.py`).
- CLI và job nền gọi thẳng `app.<part>` mà không kéo theo FastAPI.

**Đánh đổi**

- Thêm một bước chuyển đổi dataclass sang schema ở backend (`PlanOut.model_validate(..., from_attributes=True)`, `ChatOut(...)`).
- Ba file `backend/ingest.py`, `backend/scheduler.py`, `backend/companion.py` được giữ làm **re-export tạm** để import cũ không vỡ. Code trong repo đã chuyển sang import mới; xóa ba file này khi không còn nhánh nào dùng đường dẫn cũ. Riêng `companion.respond` không còn: phần truy vấn DB của nó nay là `services.companion_reply`.

**Việc tiếp theo (ngoài phạm vi #48)**

- `services.py` vẫn ném `HTTPException` cho các kiểm tra quyền sở hữu. Khi một part phase 2 cần dùng lại các kiểm tra này, tách chúng thành exception miền và để route đổi sang mã HTTP.
- ORM model vẫn nằm ở `backend/models.py`. Part trong `app/` không import chúng; nếu một part cần truy vấn riêng, đưa repository vào part đó thay vì import model từ backend.
