# docs/

Thư mục tài liệu của dự án: kế hoạch, đặc tả, tiến độ theo phase, bàn giao, ghi chú theo role, quy tắc làm việc và ADR.

| Thư mục | Nội dung |
|---|---|
| [APP_SPECIFICATION.md](APP_SPECIFICATION.md) | Đặc tả chi tiết |
| [roadmap/](roadmap/) | `PLAN.md` (kế hoạch 6 tuần) |
| [progress/](progress/) | Nhiệm vụ và kết quả theo phase |
| [handoff-and-review/](handoff-and-review/) | Tài liệu bàn giao và rà soát |
| [notes/](notes/) | Ghi chú theo role |
| [guidelines/](guidelines/README.md) | Quy tắc nhánh, Pull Request, commit |
| `adr/` | Architecture Decision Records (tạo từ tuần 1, issue #12 và #18) |
| [releases/](releases/) | Ghi chú phát hành |
| [schedule/](schedule/) | Lịch trình trình bày |
| [wireframes/](wireframes/index.html), [screenshots/](screenshots/) | Wireframe và ảnh chụp màn hình |
| [openapi.json](openapi.json) | Hợp đồng API (`python scripts/export_openapi.py`) |

## progress/

- [phase1/](progress/phase1/README.md): nhiệm vụ Phase 1 (tuần 1) theo role: UI/UX, AI, DB & Security, QA/QC, DevOps.
- [phase2/AI.md](progress/phase2/AI.md): parser syllabus, benchmark 10 syllabus; [minh-syllabus-preview.md](progress/phase2/minh-syllabus-preview.md): API preview, đọc offline và kiểm tra nguồn bổ sung cho parser #59.
- [phase3/minh-role-issues.md](progress/phase3/minh-role-issues.md): phần AI và Security & Data: #96, #99, #100, #102, #115; cách chạy và điều kiện nghiệm thu còn lại.

## handoff-and-review/

- [frontend-integration-handoff.md](handoff-and-review/frontend-integration-handoff.md): learning-check API proposal, frontend verification and PR reviewer roles.
- [minh-handoff.md](handoff-and-review/minh-handoff.md): optional scheduling backend and Workspace setup.
- [minh-review.md](handoff-and-review/minh-review.md): scheduling regression review and pending acceptance checks.
- [dang-devops-handoff.md](handoff-and-review/dang-devops-handoff.md): DevOps handoff and implementation report.

## notes/

| Role | Nội dung |
|---|---|
| [uiux/](notes/uiux/) | Getting started, root graph, S3–S5 refactor, issue #56/#57, UI release checklist, frontend integration PR |
| [ai/](notes/ai/README.md) | Chưa có ghi chú riêng; kết quả AI nằm trong `progress/` |
| [db-security/](notes/db-security/README.md) | Chưa có ghi chú riêng; kết quả nằm trong `progress/` và `adr/` |
| [qa/](notes/qa/) | `TEST_PLAN.md`, báo cáo QA hằng tuần trong `reports/` (`python dev.py qa report --week N`) |
| [devops/](notes/devops/DEPLOYMENT.md) | `DEPLOYMENT.md`: Docker Compose, staging, worker |
