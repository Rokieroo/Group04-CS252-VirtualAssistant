# ADR 004 — Catalog nguồn đã xác minh: phạm vi, nguồn được phép và giấy phép

- **Trạng thái**: Đề xuất (cần ≥ 2 thành viên duyệt trước khi merge)
- **Ngày**: 2026-11-05
- **Liên quan**: Issue #93, epic #92 (#95, #96, #98, #101, #115), đặc tả mục 1.3, 7, 11.2–11.4, 12.2, 13.2, UC-05, ADR 003

## Bối cảnh (Context)

UC-05 tìm nguồn học cho từng chặng của roadmap dựng từ syllabus. Provider đầu tiên của UC-05 là "Catalog nội bộ" (spec 11.2), hiện chỉ là `data/catalog/computer_science.yaml` viết tay. Epic #92 thay nó bằng một catalog nguồn đã xác minh, dùng chung giữa các người học, vì ba lý do:

1. **Chạy trước, không tốn quota.** Catalog được hỏi trước web search và YouTube; chặng nào catalog đã đủ nguồn thì không gọi provider trả phí (spec 11.8).
2. **Chất lượng ổn định.** Nguồn trong catalog đã qua kiểm tra (#101) một lần, không phải chấm lại mỗi lần tìm; link chết hay đổi giấy phép được phát hiện bằng kiểm tra định kỳ.
3. **Căn cứ pháp lý rõ ràng.** Mỗi nguồn hiện cho người học phải có giấy phép cho phép hiển thị như ta hiển thị, và cách thu thập phải đúng điều khoản của bên cung cấp.

Các issue sau trong epic cần một quyết định chung để không mỗi người tự diễn giải: schema (#95) cần biết trường nào được lưu, connector (#98) cần biết được lấy gì và lấy thế nào, pipeline xác minh (#101) cần danh sách giấy phép hợp lệ, danh sách trường (#96) cần công thức `authority`, ngân hàng bài tập (#115) cần biết khi nào được lưu nguyên văn.

## Quyết định (Decision)

### 1. Phạm vi: theo nhu cầu của syllabus

- Catalog chỉ nạp nguồn cho **môn đã có syllabus được tải lên**. Thứ tự: CSC10014 trước, rồi 20 syllabus benchmark của #66. Độ phủ đo bằng số chặng của roadmap thật có đủ nguồn (epic #92), không đo bằng số nguồn trong kho.
- **Đại học trước, K-12 từ tuần 4** (theo kế hoạch 6 tuần). Provider K-12 trong bảng mục 3 được khai báo sẵn nhưng connector chỉ chạy khi syllabus K-12 đầu tiên vào hệ thống.
- Danh sách trường uy tín (mục 4) chỉ là **tín hiệu `authority`**, không phải danh sách để crawl.

### 2. Những gì catalog không làm

- Không phải thư viện chung hay công cụ tìm kiếm chung (spec 1.3): không nạp môn mà chưa người học nào cần.
- Không lưu, sao chép hay phát lại nội dung của bên thứ ba: chỉ lưu metadata, link và đoạn trích ≤ 300 ký tự (mục 5).
- Không vượt paywall, trang đăng nhập hay bot challenge (Cloudflare, "Client Challenge"), kể cả khi kỹ thuật làm được. Nguồn sau một lớp chặn như vậy chỉ được thêm tay.
- Không truy cập tự động trang mà điều khoản cấm (Coursera, edX, Khan Academy; mục 7).
- Không hiện nguồn chưa `verified` (safeguard *verify or drop*, spec 13.1).
- Không dùng bảng xếp hạng có bản quyền (QS, THE) làm tín hiệu (mục 4).

### 3. Nguồn được phép

Nguồn chuẩn là [`data/policy/catalog_sources.yaml`](../../data/policy/catalog_sources.yaml): connector (#98) và kiểm tra giấy phép (#101) đọc file này, không chép lại bảng dưới. Bảng là bản tóm tắt tại ngày kiểm tra; trường `evidence` trong YAML là trang chính thức đã đọc, `checked_on` là ngày đọc (2026-11-05).

| Provider | Giấy phép (đã kiểm tra) | Cách lấy | Rate limit | `robots.txt` / điều khoản | Giai đoạn |
| --- | --- | --- | --- | --- | --- |
| `mit_ocw` | CC BY-NC-SA 4.0; nội dung bên thứ ba trong khóa không thuộc giấy phép | Sitemap (`ocw.mit.edu/sitemap.xml`, sitemap riêng mỗi khóa) | Không công bố → 1 req/s/domain | `Allow: /` | 1 (#98) |
| `openstax` | **Theo từng sách**: 80 sách CC BY-NC-SA 4.0, 38 sách CC BY 4.0, 11 sách không ghi (API ngày 2026-11-05) | CMS API, trường `license_name`, `license_version` | Không công bố → 1 req/s | `/books/` được phép với `*` | 1 (#98) |
| `open_yale` | CC BY-NC-SA 3.0 Unported; tài liệu bên thứ ba không thuộc giấy phép trừ khi ghi rõ | Thêm tay (~40 khóa, không có sitemap) | 1 req/s khi xác minh | Cho phép trang khóa học | 1 (#98) |
| `openlearn` | CC BY-NC-SA 4.0 "unless otherwise stated"; ngoại lệ ghi ở phần acknowledgements của từng khóa | Thêm tay | Không truy cập tự động | Cloudflare challenge chặn cả `robots.txt` | Sau |
| `khan_academy` | CC BY-NC-SA cho video và bài tập dùng ngoài site; một số nội dung đối tác là ngoại lệ | Thêm tay | Không truy cập tự động | Hướng dẫn của Khan Academy cấm scraping; có client challenge | Sau |
| `youtube_university` | Theo từng video: `status.license` = `youtube` (giữ mọi quyền) hoặc `creativeCommon` (CC BY 3.0) | YouTube Data API v3, chỉ kênh chính thức của trường trong danh sách chọn tay | 10.000 đơn vị/ngày; `search.list` tối đa 100 lần/ngày | Developer Policies cấm scraping, cấm tải/lưu video; dữ liệu API làm mới ≤ 30 ngày | Sau |
| `nxbgd_sgk` | Giữ mọi quyền (NXB Giáo dục Việt Nam), đọc miễn phí | Thêm tay; nền tảng chính thức là `taphuan.nxbgd.vn` (`hanhtrangso.nxbgd.vn` đã dừng) | 1 req/s khi xác minh | `Disallow:` trống | Tuần 4 (K-12) |
| `moet` | Văn bản quy phạm pháp luật (chương trình GDPT): không thuộc phạm vi bảo hộ quyền tác giả (Điều 15 Luật SHTT) | Thêm tay | 1 req/s khi xác minh | Chặn `*.pdf` và `/content/download/` → PDF xác minh tay | Tuần 4 (K-12) |
| `coursera` | Giữ mọi quyền; chỉ link | Thêm tay sau khi đọc ToS | Không truy cập tự động | Acceptable Use Policy cấm scraping "manual, mechanical, or automated" | Khi cần |
| `edx` | Giữ mọi quyền; chỉ link | Thêm tay sau khi đọc ToS | Không truy cập tự động | Terms 11.6 cấm "spiders, robots, crawlers" | Khi cần |
| `ror` | CC0 (bản dump trên Zenodo, `cc-zero`) | Bản dump có phiên bản trên Zenodo, không gọi API theo từng trường | 1 lần tải mỗi lần dựng | API: 2.000 req/5 phút có `Client-Id`, 50 không có (chưa áp dụng ngày 2026-11-05) | Chỉ authority (#96) |
| `openalex` | CC0 ("Our data is CC0") | API `institutions`, lưu snapshot JSON | 10 req/s; không key: $0,10/ngày dùng chung theo IP; key miễn phí: $1/ngày | — | Chỉ authority (#96) |

Ghi chú khi đối chiếu với giả định ban đầu của issue:

- **OpenStax không còn CC BY cho mọi sách.** Trung tâm trợ giúp của OpenStax nay ghi CC BY-NC-SA; API vẫn trả CC BY 4.0 cho các sách đã phát hành theo giấy phép đó (ví dụ *Statistics*, *Introductory Statistics* bản 1). Connector phải đọc giấy phép **từng sách**; sách không ghi giấy phép vào hàng chờ duyệt, không mặc định.
- **Hành trang số đã dừng.** NXB Giáo dục Việt Nam chuyển SGK điện tử miễn phí sang `taphuan.nxbgd.vn`.
- **Khan Academy** có trong spec 11.2 nhưng thiếu trong issue; được thêm với phương thức thêm tay vì điều khoản cấm scraping.

Thêm một provider mới = một PR sửa `catalog_sources.yaml` và bảng trên, được 2 thành viên duyệt, kèm link trang chính thức đã đọc.

### 4. "Trường uy tín" cho tiêu chí `authority`

`authority` (trọng số 0,20, spec 11.4) lấy từ tier của trường sở hữu nguồn. Danh sách trường do #96 dựng theo công thức sau; chạy lại trên cùng snapshot phải cho cùng kết quả.

**Đầu vào**: snapshot OpenAlex `institutions` (CC0) ghép với bản dump ROR (CC0); ghi phiên bản của cả hai vào file kết quả.

**Điều kiện vào danh sách**: `type = education`, có `ror`, có `homepage_url`, `works_count ≥ 1000`.

**Thứ tự** (tất định):

1. `summary_stats.h_index` giảm dần;
2. `cited_by_count` giảm dần;
3. `id` OpenAlex tăng dần (phá hòa).

**Tier**:

| Tier | Quy tắc | `authority` (= `score.authority(DomainTier(tier))`) |
| ---: | --- | ---: |
| 1 | Hạng 1–500 theo thứ tự trên; hoặc trường Việt Nam trong danh sách chọn tay đạt tier 1; hoặc nguồn K-12 chính thống | 1,0 |
| 2 | Hạng 501–2000; hoặc trường Việt Nam trong danh sách chọn tay đạt tier 2 | 0,7 |
| 3 | Mọi nguồn còn lại | 0,4 |

`DomainTier` trong `app.vetting.policy` đã có giá trị 1, 2, 3 cho `TIER1`, `TIER2`, `OTHER`, nên `institutions.tier` đổi thẳng sang `DomainTier` mà không cần bảng ánh xạ mới.

**Danh sách Việt Nam chọn tay** (#96, mỗi dòng ghi lý do và 2 người duyệt):

- Tier 1: đại học thành viên của ĐHQG Hà Nội và ĐHQG TP.HCM, đại học công lập trực thuộc Bộ GD&ĐT; nguồn K-12 chính thống (Bộ GD&ĐT, NXB Giáo dục Việt Nam) với mã nội bộ `vn-k12:<slug>` thay cho ROR ID.
- Tier 2: trường đại học khác có kết quả kiểm định chất lượng cơ sở giáo dục còn hiệu lực.

Vì sao không dùng thuần h-index cho Việt Nam: trên OpenAlex ngày 2026-11-05, hai trường tư (Duy Tân 245, Tôn Đức Thắng 241) xếp trên ĐHQG TP.HCM (191). h-index đo sản lượng nghiên cứu, không đo chất lượng học liệu; với nhóm trường mà người dùng của ta học trực tiếp, chọn tay theo quy tắc công khai ít sai hơn.

**Nguồn khớp với trường nào**: host của nguồn trùng hoặc là subdomain của một domain trong `domains` của bản ghi ROR hoặc của `homepage_url` (kiểm tra `domain` của #101, chống trang giả danh trường). `authority` của nguồn = tier tốt nhất giữa trường khớp và allowlist tên miền hiện có (`data/policy/allowlist_tier*.txt`, cho OER không thuộc trường nào như `openstax.org`).

### 5. Dữ liệu được lưu và cấm lưu

**Được lưu** (đúng các cột của #95, spec 7):

- Metadata: `canonical_url`, tiêu đề, provider, domain, định dạng, ngôn ngữ, thời lượng, năm, trình độ, mã và tên khóa, trường, tên tác giả/giảng viên **như nguồn công bố** (giấy phép CC bắt buộc ghi công).
- Giấy phép: mã trong `catalog_sources.yaml` (`license`), `is_free`.
- Bằng chứng: `content_hash`, `evidence_quote` ≤ 300 ký tự, khớp nguyên văn text đã tải (safeguard *grounded justification*).
- Provenance: `source_connector`, `ingested_at`, mọi lần kiểm tra trong `resource_verifications` (#95, chỉ thêm).
- Trường: ROR ID, tên, quốc gia, domain, tier, `rank_signal` (h-index, `cited_by_count`, `works_count`, phiên bản snapshot).

**Cấm lưu**:

- Toàn văn trang, HTML, PDF, slide, ảnh, file audio/video; phụ đề hay transcript YouTube (chỉ chủ kênh mới tải được qua API, và Developer Policies cấm lưu bản sao nội dung).
- Đề bài tập nguyên văn khi giấy phép không có `verbatim: true` (mục 6).
- Dữ liệu cá nhân ngoài tên tác giả đã công bố: email, số điện thoại, ảnh giảng viên.
- Bất kỳ dữ liệu nào của người học trong bảng dùng chung (tài liệu riêng ở #114 chỉ chủ sở hữu thấy).
- Dữ liệu lấy được bằng cách vượt đăng nhập, paywall hay bot challenge, hoặc bằng truy cập tự động vào provider có `automated: false`.
- Dữ liệu YouTube API quá 30 ngày chưa làm mới (Developer Policies III.E.4); trùng với hạn `stale` 30 ngày của #101.

**Trích dẫn**: một `evidence_quote` ≤ 300 ký tự cho mỗi cặp nguồn-chặng, lấy nguyên văn. Với nguồn giữ mọi quyền, đây là trích dẫn hợp lý để minh họa lý do chọn nguồn (Luật SHTT, Điều 25 về ngoại lệ không xâm phạm quyền tác giả); cần rà soát pháp lý trước khi mở cho người dùng thật, như spec 13.2 đã ghi cho dữ liệu K-12.

**Hiển thị**: thẻ nguồn luôn ghi đủ tiêu đề, tác giả/trường, link gốc và tên giấy phép có link (yêu cầu ghi công của mọi giấy phép CC), theo mẫu `attribution` của provider. Video YouTube phát bằng player chính thức, giữ nguyên link và ghi công của YouTube.

### 6. Bài tập nguyên văn (#115)

Giữ quy tắc spec 12.2: đề bài chỉ được lưu nguyên văn khi giấy phép có `verbatim: true` (CC0, CC BY, CC BY-SA, văn bản quy phạm pháp luật). Với CC BY-NC-SA (MIT OCW, Open Yale, OpenLearn, phần lớn OpenStax) và nguồn giữ mọi quyền, catalog chỉ lưu link + vị trí (trang, số bài).

Lý do không mở rộng cho CC BY-NC-SA dù sản phẩm phi thương mại (spec 16): định nghĩa "thương mại" khác nhau giữa các bên (Open Yale coi cả việc nhận quảng cáo là thương mại), và điều khoản ShareAlike áp lên tác phẩm phái sinh. Chỉ lưu link giữ ta an toàn nếu sản phẩm đổi mô hình sau này.

### 7. Nguồn chỉ cho phép link

Coursera, edX, Khan Academy (và mọi provider có `automated: false`):

- Admin thêm tay từng khóa sau khi đọc điều khoản; không connector nào chạy.
- Không fetch tự động, kể cả để kiểm tra link: admin mở link và ghi kết quả vào `resource_verifications` với `checked_by` là chính mình.
- `is_free = true` chỉ khi học được nội dung mà không trả phí (ví dụ chế độ audit); khóa chỉ miễn phí phần giới thiệu ghi `is_free = false` và bị lọc như nguồn trả phí (spec 11.3 bước 5).

### 8. Quy trình gỡ khi chủ sở hữu yêu cầu

Hạn chót 48 giờ (spec 13.2).

1. **Tiếp nhận**: chủ sở hữu mở issue theo mẫu [Yêu cầu gỡ nguồn](../../.github/ISSUE_TEMPLATE/takedown.md) (nhãn `takedown`), hoặc liên hệ nhóm qua kênh khác; người nhận tạo issue thay họ để có hồ sơ.
2. **Gỡ ngay** (trong 24 giờ): admin gọi `POST /admin/catalog/resources/{id}:reject` (#101) với lý do `takedown`. Nguồn `rejected` không bao giờ hiện, nên biến mất khỏi mọi chặng; chặng lấy ứng viên kế tiếp đã chấm (spec 11.6). Lý do được ghi vào `resource_verifications` (`check_name = admin`, `checked_by` = id admin). Nguồn thêm tay thì xóa thêm dòng khỏi `data/catalog/*.yaml` bằng PR.
3. **Không nạp lại**: `upsert_records()` (#98) giữ nguyên `rejected`, không đặt lại `pending`.
4. **Gỡ cả site**: nếu yêu cầu gồm toàn bộ domain, PR thêm domain vào `data/policy/blocklist.txt` và bỏ provider khỏi `catalog_sources.yaml`.
5. **Trả lời** trên issue những gì đã gỡ, rồi đóng issue.

### 9. Thực thi (Enforcement)

`tests/test_catalog_sources.py` chạy trong `pytest tests/` (CI `lint-and-sanity-check`, `postgres-integration`, `python dev.py devops ci`) và fail khi:

- provider dùng giấy phép không có trong danh sách, hoặc `per_item` mà không khai báo `item_licenses`;
- `verbatim: true` gán cho giấy phép NonCommercial, NoDerivatives hoặc giữ mọi quyền (spec 12.2);
- provider truy cập tự động thiếu `rate_limit_per_sec`, hoặc provider `automated: false` vẫn khai báo connector (`api`/`sitemap`);
- domain của provider nằm trong blocklist hoặc danh sách paywall;
- thiếu trang căn cứ (`evidence`) hoặc ngày kiểm tra;
- bảng mục 3 của ADR này và file YAML lệch nhau.

Yêu cầu cho các issue sau, chưa có code trong ADR này:

- #101: fetch bị `robots.txt` chặn (`FetchError("robots")`) đưa nguồn vào hàng chờ duyệt, không `rejected`; kiểm tra `license` chỉ chấp nhận mã trong `catalog_sources.yaml`. Đã làm: luật ở `src/app/catalog/verification.py`, job `verify_catalog` (chạy hằng ngày) và API admin ở `src/assistant/backend/catalog_verification.py`; provider `automated: false` không bị fetch mà vào hàng chờ duyệt.
- #98: đọc `method`, `endpoint`, `rate_limit_per_sec` từ YAML; gửi request qua `SafeFetcher` (đã tôn trọng `robots.txt`); không chạy cho provider `automated: false`.
- #96: dựng `institutions` theo mục 4 từ snapshot đã lưu. Đã làm: `scripts/build_institutions.py` dựng `data/catalog/institutions.csv` từ `data/catalog/institution-snapshots/` (dựng lại cho file giống từng byte, `.gitattributes` giữ LF); `python dev.py db seed-institutions` nạp vào DB; `DomainPolicy` đọc registry nên `authority` của mọi nguồn (catalog lẫn web) là tier tốt nhất giữa trường và allowlist. Các dòng chọn tay trong `institutions-vn.json` chỉ vào registry khi có đủ 2 người duyệt; script in ra các dòng còn chờ.

### 10. Phương án đã cân nhắc

| Phương án | Lý do không chọn |
| --- | --- |
| Xếp hạng QS / THE làm `authority` | Dữ liệu có bản quyền, điều khoản không cho tái sử dụng; phương pháp đổi hằng năm nên không tái tạo được |
| Crawl toàn bộ MIT OCW, OpenStax… trước | Trái phạm vi spec 1.3; tốn công xác minh cho nguồn không chặng nào cần |
| Lưu toàn văn để chấm lại nhanh | Vi phạm spec 1.3 và 7; `content_hash` + `evidence_quote` đủ để phát hiện thay đổi |
| Ghi bảng nguồn chỉ trong ADR | Code (#98, #101) phải chép lại bảng, dễ lệch; YAML + test giữ một nguồn sự thật |
| Mở rộng lưu bài tập nguyên văn cho CC BY-NC-SA | Xem mục 6 |

## Hệ quả (Consequences)

**Tích cực**

- #95, #96, #98, #101, #115 có cùng một căn cứ; câu hỏi "nguồn này có được hiện không?" trả lời bằng một mã giấy phép và một file.
- Thêm provider là sửa dữ liệu và qua review, không sửa code.
- Mọi giấy phép và cách thu thập có link trang chính thức và ngày kiểm tra, kiểm toán được.

**Đánh đổi**

- Phần lớn OER (CC BY-NC-SA) chỉ có link cho bài tập; ngân hàng câu hỏi (#115) phụ thuộc nhiều hơn vào tài liệu người học và sách OpenStax CC BY.
- Provider thêm tay (Coursera, edX, Khan Academy, OpenLearn) cần admin kiểm tra link định kỳ thay cho job tự động.
- Giấy phép và điều khoản có thể đổi (OpenStax là ví dụ): cần đọc lại các trang căn cứ mỗi học kỳ và cập nhật `checked_on`.

**Việc tiếp theo (ngoài phạm vi #93)**

- ~~`data/catalog/computer_science.yaml` chưa có trường `license`~~: #98 đã thêm, file được connector `manual_yaml` đọc cùng `data/catalog/sources/manual.yaml`; Open Yale được liệt kê tay ở `data/catalog/sources/open_yale.yaml`.
- Pipeline tìm web hiện tại (UC-05) vẫn fetch mọi domain ứng viên; nên áp quy tắc `automated: false` cho cả pipeline đó (issue riêng).
