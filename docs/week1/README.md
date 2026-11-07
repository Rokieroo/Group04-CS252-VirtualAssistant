# 📍 Tuần 1: Nền móng (Foundation)

Tài liệu này mô tả nhiệm vụ của cả team trong tuần 1: mục tiêu chung, ai làm gì, thứ tự phụ thuộc giữa các issue và lịch từng ngày. Chi tiết của từng role nằm trong file riêng bên dưới.

## 🎯 Mục tiêu tuần
Cuối tuần, trên staging, một sinh viên có thể: **upload file slide CSC10014 Week 1 → xác nhận danh sách concept → nhận 10 câu hỏi, mỗi câu trích dẫn đúng trang slide.**

## 👥 Nhiệm vụ theo role

| Role | Thành viên | Nhiệm vụ chính | Issue | File chi tiết |
|---|---|---|---|---|
| UI/UX | Nguyễn Quốc Thịnh, Lê Phan Đức Mân | Wireframe, app shell Pathly, màn hình Upload + Concept editor | #5, #6, #7 | [UIUX.md](UIUX.md) |
| AI implementation | Trần Quyết Thắng, Võ Gia Minh | Module `llm`, trích concept, sinh câu hỏi có trích dẫn, BM25 | #8, #9, #10, #11 | [AI.md](AI.md) |
| Database & Security | Trần Quyết Thắng, Võ Gia Minh, Nguyễn Quốc Thịnh | Schema + migration, FastAPI + ingest PDF, auth | #12, #13, #14 | [DB_SECURITY.md](DB_SECURITY.md) |
| QA/QC | Lê Hồng Đăng | Test plan, benchmark 20 case, integration test, báo cáo tuần | #15, #16 | [QA_QC.md](QA_QC.md) |
| DevOps | Võ Thành Đạt, Lê Hồng Đăng | Milestone, branch protection, CI, Docker Compose, staging | #17, #18 | [DEVOPS.md](DEVOPS.md) |

> [!IMPORTANT]
> Người phụ trách trong issue là **đề xuất**. PM xác nhận lại trong standup thứ Hai và assign trên GitHub.

## 🔄 Thứ tự phụ thuộc (Dependencies)

```text
#17 milestone, protection, hooks ──► mọi PR khác
#12 schema ──► #13 FastAPI + ingest ──► #11 BM25 ──► #10 sinh câu hỏi
                     │                    ▲
                     ├──► #14 auth        │
                     └──► #18 compose     #8 llm ──► #9 trích concept ──► #10
#5 wireframe ──► #7 upload + concept editor ◄── #6 app shell
#15 test plan + benchmark ──► #16 integration test (sau khi #11 #13 #14 có PR)
```

**Đường găng (critical path):** #12 → #13 → #11 → #10. Nếu #13 trễ quá thứ Tư thì AI dùng dữ liệu `sources` giả lập trong test để không bị chặn.

## 🗓️ Lịch tuần

| Ngày | Cả team | Mốc quan trọng |
|---|---|---|
| Thứ Hai | Standup 15′: xác nhận người phụ trách, cài git hook (`python dev.py devops install-hooks`) | #17 xong phần milestone + label; #12 merge |
| Thứ Ba | Code song song; mỗi người mở PR nháp (draft) sớm | #8 merge; wireframe #5 sẵn để góp ý |
| Thứ Tư | Merge giữa tuần, gỡ vướng | #13 merge (ingest chạy); #5 duyệt |
| Thứ Năm | Ghép nối: UI mock → kiểm tra với API thật; QA chạy integration test | #9, #11, #14 merge; staging có `/health` |
| Thứ Sáu | Demo 15′, báo cáo QA tuần 1, retro 15′, tag `v0.1` | #10 merge; demo trên staging |

## ✅ Definition of Done (áp dụng mọi issue)
- Code nằm trong `main` qua PR có ≥ 1 approve và CI xanh.
- Có test cho code mới; `python dev.py devops ci` pass.
- Tài liệu liên quan trong `docs/` được cập nhật (kết quả đo ghi vào file role tương ứng).
- Không secret, không dữ liệu cá nhân thật.

## 🎬 Kịch bản demo thứ Sáu (5 phút)
1. Mở staging, đăng ký tài khoản mới (năm sinh, cấp học).
2. Tạo môn "CSC10014", upload `CSC10014_2026_Week01_Problem_Framing.pdf`.
3. Xem danh sách concept, đổi tên 1 concept, xác nhận.
4. Hiện 10 câu hỏi được sinh, bấm vào trích dẫn để thấy đúng trang.
5. QA trình bày: số case benchmark, số test, bug còn mở.

## 📚 Tham khảo
- Kế hoạch 6 tuần: [docs/roadmap/PLAN.md](../roadmap/PLAN.md)
- Đặc tả: [docs/APP_SPECIFICATION.md](../APP_SPECIFICATION.md)
- Quy tắc Git: [docs/guidelines/](../guidelines/README.md)
