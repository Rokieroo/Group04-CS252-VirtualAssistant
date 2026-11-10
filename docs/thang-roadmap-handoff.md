# AI Implementation Handoff & Issue #60 Completion Report (Tran Quyet Thang)

- **Assignee:** Trần Quyết Thắng (`tranquyetthang27`)
- **Role:** AI Implementation (`ai`)
- **Responsible Issue:** #60 (`[AI] Roadmap Builder: biến syllabus thành lộ trình học tập hoàn chỉnh`)
- **Working Branch:** `ai-thang/60-roadmap-builder`
- **Target Branch:** `main`

---

## 1. Deliverables Summary

| File Location | Component | Purpose & Implementation Details |
| --- | --- | --- |
| `src/app/roadmap/prompts/prereq_v1.txt` | **Prerequisite Prompt** | System prompt yêu cầu LLM xác định quan hệ kiến thức tiên quyết trực tiếp giữa các chủ đề trong syllabus. Trả về JSON chuẩn schema (`parent_slug`, `child_slug`, `confidence`, `reason`). Phân cấp confidence rõ ràng (≥0.9: curriculum chuẩn; 0.6–0.8: phụ thuộc mạnh; <0.6: phỏng đoán). |
| `src/app/roadmap/graph.py` | **Graph Algorithms** | Cài đặt thuật toán sắp xếp tô-pô **Kahn's algorithm** (`topological_sort`) cho thứ tự học tất định; thuật toán **Tarjan's strongly connected components (SCC)** (`find_cycles`) phát hiện chính xác các cạnh chu trình phụ thuộc nội bộ SCC (loại bỏ cạnh cầu/DAG). Hỗ trợ đa dạng shape: `NodeSpec`, tuple `(parent, child)`, dict, `Edge`. |
| `src/app/roadmap/duration.py` | **Duration Allocation** | Hàm tính thời lượng tự học theo spec 10.2: tổng thời gian chuẩn `số_tín_chỉ × 120 phút`/tuần; phân bổ động theo độ khó (1–3) và mức Bloom (`remember` < `understand` < `apply` < `analyze` < `evaluate` < `create`); tự động cộng **+20%** thời lượng ôn tập cho các chặng rơi vào tuần liền kề trước mốc kiểm tra (`milestone`). |
| `src/app/roadmap/builder.py` | **Roadmap Builder Core** | Tiếp nhận danh sách chủ đề qua `normalize_topics` (Issue #50) tạo node `topic`; phân giải mốc thi tạo node `milestone` với trường `covers`; sinh cạnh `soft` theo tiến trình tuần và cạnh `strict` từ LLM (`confidence >= 0.6`); tự động bẻ gãy cycle qua `_repair_cycles`; bảo đảm **toàn vẹn thời gian** (`topic.due_at <= milestone.due_at`). |
| `src/app/roadmap/nodes.py` | **Node Specification** | Bổ sung các trường metadata `slug`, `difficulty`, `bloom_level` vào `NodeSpec` phục vụ builder mà vẫn tương thích ngược với các caller cũ. |
| `src/app/roadmap/__init__.py` | **Package Interface** | Re-export đầy đủ các hằng số và hàm công khai; chuẩn hóa `__all__` theo chuẩn isort/ruff. |
| `tests/test_roadmap.py` | **Test Suite & Evaluation** | Bộ 10 test case bao phủ toàn bộ spec: test Cycle Detection (A->B->C->A), test Milestone Covers & time integrity, test phân bổ thời lượng (+20% review week), và benchmark đánh giá trên 5 syllabus mẫu thực tế đạt **86.96%** đồng thuận (yêu cầu ≥ 80%). |

---

## 2. Verification Results

Chạy toàn bộ quy trình kiểm thử và kiểm tra chất lượng theo quy định dự án:

```powershell
.\.venv\Scripts\python.exe dev.py devops branch
# [ OK ] Tên nhánh hợp lệ: ai-thang/60-roadmap-builder

.\.venv\Scripts\python.exe dev.py devops ci
```

**Kết quả thực tế trên môi trường:**
- **Ruff linter:** `All checks passed!` (0 lỗi, tuân thủ PEP 8 và convention dự án).
- **Pytest:** `348 passed in 66.99s` (100% test suites trong repository đều passed, trong đó có 10 tests mới của `tests/test_roadmap.py`).
- **Secret scan:** `[ OK ] Không thấy secret trong các file git đang theo dõi.`
- **Benchmark validation:** `[ OK ] 20 case hợp lệ trong benchmark.jsonl`
- **Tổng kết:** `[ OK ] CI cục bộ đã pass.`

---

## 3. AI-Assisted Development Disclosure

Quá trình hoàn thiện Issue #60 tuân thủ chính sách AI disclosure của nhóm:
- **Nội dung AI hỗ trợ:** Khởi tạo prompt `prereq_v1.txt`, triển khai thuật toán Tarjan SCC / Kahn topo sort, tinh chỉnh thuật toán chia thời lượng largest-remainder, và sinh 5 mẫu syllabus benchmark cho bài test đánh giá.
- **Con người kiểm chứng:** Trực tiếp review mã nguồn, sửa lỗi lọc cạnh liên SCC trong `find_cycles`, đồng bộ chuẩn hóa kiểu dữ liệu Python 3.11+ / ruff rules, chạy toàn bộ CI cục bộ và nghiệm thu các chỉ số kiểm thử.
