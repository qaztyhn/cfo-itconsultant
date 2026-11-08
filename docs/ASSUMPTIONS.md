# Assumptions (ASM-xxx)

## Sổ quyết định đã chốt (cập nhật 2026-11-09)

**Mục đích:** đây là nơi tập trung ghi nhận **tất cả assumption/quyết định nghiệp vụ đã được chủ dự án hoặc nhóm có thẩm quyền xác nhận**, không chỉ những chỗ còn mơ hồ. Giữ nguyên mã `ASM-xxx` cũ; các quyết định sản phẩm liên chủ đề dùng mã `DEC-xxx` để tránh trùng với ASM do Dev đề xuất (như ASM-008 ở PR #55).

**Nguồn và mức độ hiệu lực:** quyết định đã duyệt được ghi ở đây là **ràng buộc về nghiệp vụ**; `05`/`06`/`04` và `09` vẫn phải được đồng bộ bằng PR được review. Ghi vào sổ **không có nghĩa code, migration hay kiểm thử đã hoàn thành**. Không tự đổi API/DDL chỉ vì có một đoạn giải thích trong sổ. Nếu có mâu thuẫn, dừng thay đổi liên quan và mở PR đồng bộ đặc tả.

| ID | Quyết định được xác nhận | Ngày | Bằng chứng / chi tiết | Tình trạng triển khai |
|---|---|---|---|---|
| [ASM-001](#asm-001--cột-chung-created_at--updated_at-cho-mọi-bảng-cfo) | Cột metadata chung cho 57 bảng CFO, không áp dụng `src_*`; log bất biến | 06/11 | Xem mục ASM-001 | Đã chốt quy tắc; cần test theo migration |
| [ASM-002](#asm-002--diễn-giải-seed-tham-chiếu-0008_seed_reference) | Seed tham chiếu tách seed demo; GPS migration mặc định tắt, không seed mật khẩu | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Đã duyệt hướng; kiểm tra seed/test |
| [ASM-003](#asm-003--chi-tiết-xác-thực-chưa-có-trong-06-mục-4) | Login tối đa 5 lần/60 giây/IP cho demo một instance; 429; 204 logout; hạn chế lộ thông tin | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Đã duyệt hướng; cần xác minh code |
| [ASM-005](#asm-005--quy-tắc-xác-nhận--từ-chối-ánh-xạ-và-phạm-vi-đơn-cfo) | Chỉ đơn **100% SKU confirmed** dùng CFO; thiếu SKU dùng quy trình cũ | 07/11 | [PR #49](https://github.com/qaztyhn/cfo-itconsultant/pull/49) | Nghiệp vụ đã duyệt; routing code còn phụ thuộc Q14 |
| [ASM-006](#asm-006--quy-tắc-ghi-nhân-sự-chưa-ghi-trong-06-mục-13) | Chuyển/nghỉ việc có người thay quản lý; khóa tài khoản, giữ lịch sử và audit | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Nghiệp vụ đã duyệt; mã audit đề xuất ở Q13 |
| [ASM-007](#asm-007--quy-tắc-điểm-danh-chưa-ghi-trong-06-mục-13) | Warehouse Manager quyết định lịch người–ca; `expected_staff` **chỉ để so sánh** | 07/11 | [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50) | Cần lịch chính thức, migration/API |
| [DEC-SALES-001](#dec-sales-001--sales-xác-nhận-có-điều-kiện-và-sync-now) | Sales dùng CFO riêng, sync-now; chỉ confirm phương án chuẩn an toàn | 07/11 | [PR #43](https://github.com/qaztyhn/cfo-itconsultant/pull/43) | Docs đã merge, code theo milestone |
| [DEC-ROUTING-001](#dec-routing-001--sales-kiểm-cfo-trước-khi-điều-phối-thủ-công) | Sales phải kiểm CFO trước khi điều phối tay; luồng CFO/legacy không tự đảo | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) | Quy tắc duyệt; chi tiết Q14 vẫn chờ migration/API |
| [DEC-ROUTING-002](#dec-routing-002--chỉ-người-kiểm-tra-mới-ghi-quyết-định-phân-luồng) | Polling chỉ đồng bộ dữ liệu nguồn; quyết định `cfo/legacy` chỉ ghi khi Sales Sync & check hoặc Dispatcher kiểm tra được ủy quyền; đã ghi không tự đổi; điều phối tay trước khi kiểm = ngoại lệ có lý do + audit; đã `cfo` thì chuyển Dispatcher | 07/11 | Chủ dự án chốt trong phiên làm việc 07/11 (trả lời câu hỏi ở [PR #59](https://github.com/qaztyhn/cfo-itconsultant/pull/59)) | DB ràng buộc ở migration 0011; ingestion/sync-now do Dev 2 |
| [DEC-ORS-001](#dec-ors-001--thời-hạn-cache-ước-lượng-tuyến-ors) | Fallback ORS có TTL 60 phút mặc định theo market; quá hạn phải thử ORS lại, gắn nhãn tuyến ước lượng | 07/11 | Chủ dự án xác nhận sau review [PR #67](https://github.com/qaztyhn/cfo-itconsultant/pull/67) | Code TTL trong #67 đã vào `main`; theo dõi tích hợp/hiển thị nhãn fallback |
| [DEC-SHIFTS-001](#dec-shifts-001--q12-lịch-làm-chính-thức-của-kho-và-tài-xế) | Q12a–d: 1 ca/người/ngày, manager chính/phó có quyền, hồi tố có lý do, thiếu lịch thì 0 công suất | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) | Quy tắc duyệt; bảng/API đề xuất cần review |
| [DEC-AUDIT-001](#dec-audit-001--q13-mã-nhật-ký-nhân-sự) | Q13 chấp thuận 3 mã audit mới và quy tắc hồi tố | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) | Chờ cập nhật contract/code |
| [DEC-DRIVER-001](#dec-driver-001--khung-giờ-làm-nghỉ-và-giới-hạn-lái-xe) | Kiểm ca tài xế và nhân viên kho; nghỉ mặc định 11h; lái xe/nghỉ theo phạm vi pháp luật | 07/11 | [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53), [PR #54](https://github.com/qaztyhn/cfo-itconsultant/pull/54) | Quy tắc MVP đã duyệt; engine/schema cần nghiệm thu |
| [DEC-DEV2-D7-001](#dec-dev2-d7-001--d7-dữ-liệu-xe-và-lịch-sử-tài-xế-synthetic-cho-demo) | D7-A–E: seed xe/tài xế synthetic có thông số và lịch sử 56 ngày; giữ nghỉ 11h; phân biệt giờ làm/lái; thiếu dữ liệu thì fail-closed; Dev 1+2 test chung | 08/11 | Chủ dự án xác nhận “tôi đồng ý” sau đề xuất D7-A–E (08/11/2026) | Quyết định **đã duyệt**, seed/engine integration và acceptance tests **chưa triển khai** |
| [DEC-NOTIFY-001](#dec-notify-001--giới-hạn-email-thử-nghiệm-và-ngăn-gửi-trùng) | Email MVP chỉ qua Mailpit hoặc staging kiểm soát với địa chỉ demo; chưa gửi khách thật khi thiếu chống trùng/đối soát | 07/11 | Chủ dự án xác nhận sau review [PR #69](https://github.com/qaztyhn/cfo-itconsultant/pull/69) | Quyết định đã duyệt; #68–#70 đã lên `main` (#74); chặn người nhận staging bằng code trong PR `fix/notify-staging-recipient-guard` (chờ review); chống trùng/đối soát chưa có |
| [DEC-HOLD-001](#dec-hold-001--hết-hạn-hold-phải-lập-kế-hoạch-mới) | Hold hết hạn ⇒ phương án cũ không được duyệt lại; giải phóng giữ chỗ; người dùng chọn Plan Again để tạo planning_run mới trên **cùng order**, kiểm tra đầy đủ và giữ chỗ lại | 08/11 | Chủ dự án chốt trong phiên review PR #78 (08/11/2026) | Cần đồng bộ T14/T15/T16, job hết hạn, API/UI và regression tests; PR #78 chưa thể tuyên bố E2E |
| [DEC-SRC-001](#dec-src-001--source-contract-src-q1q10) | Phê duyệt hướng giải quyết SRC-Q1–Q10 cho hệ thống nguồn: snapshot, API ghi, lỗi, lifecycle, phân trang, tăng dần, lịch nhận, tồn kho, local/global SKU | 08/11 | Chủ dự án xác nhận trong phiên làm việc 08/11; [proposal](proposals/M1_SOURCE_CONTRACT.md) | Đã duyệt nguyên tắc; 05/06, migration, contract test và code chưa cập nhật trong quyết định này |
| [DEC-SRC-D1-001](#dec-src-d1-001--chốt-chi-tiết-d1-a-d-source-contract) | D1-A–D: list API phân trang và sync; POS DRAFT/validate/submit/edit/cancel với version và 422/409; replan suggestion sau khi đã duyệt; lịch nhận/stock batch. **Riêng Q10 về pool đã được DEC-SRC-Q10-SKU-001 thay thế** | 08/11 | Chủ dự án “ĐƯỢC ĐỒNG Ý” với toàn bộ D1-A–D, [chi tiết](decisions/DEC_SRC_D1_APPROVED_20261108.md) | **Đã duyệt hợp đồng chi tiết**; migration/Source API/adapter/tests vẫn chưa triển khai đầy đủ |
| [DEC-SRC-Q10-SKU-001](#dec-src-q10-sku-001--mỗi-sku-một-đơn-vị-tồn-kho-chuẩn-không-physical-stock-pool) | **Q10 thay thế quy tắc pool cũ:** mỗi SKU một đơn vị tồn chuẩn, mỗi batch/kho/SKU một dòng; đơn bán quy cách khác quy đổi về SKU; không tạo/gom `physical_stock_pool_id` | 08/11 | Chủ dự án yêu cầu “THAY ĐỔI PR 101 THEO YÊU CẦU CỦA TÔI” sau khi xác nhận “1 mã sản phẩm phải lưu đơn vị giống nhau”; [PR #101](https://github.com/qaztyhn/cfo-itconsultant/pull/101) | **Đã duyệt nghiệp vụ Q10 mới;** Q9 giữ nguyên; schema/API/adapter/tests chờ triển khai |
| [DEC-CFO-STOCK-SCOPE-001](#dec-cfo-stock-scope-001--phạm-vi-sku-đồng-bộ-tồn-kho-cfo-được-chốt-trước) | Chọn B: chỉ đồng bộ SKU trong phạm vi CFO đã xác định trước; SKU chưa mapping trong phạm vi làm batch cập nhật CFO không hợp lệ | 08/11 | Chủ dự án chốt trong hội thoại 08/11/2026 | Đã duyệt nghiệp vụ; scope, ingestion, tests còn cần triển khai |
| [DEC-CFO-STOCK-INDEPENDENCE-001](#dec-cfo-stock-independence-001--chỉ-cộng-nhiều-sku-cùng-global-product-khi-tồn-kho-độc-lập-đã-xác-minh) | Chọn A: chỉ cộng nhiều SKU cùng global product sau khi xác minh lượng tồn độc lập; chưa xác minh thì từ chối | 08/11 | Chủ dự án chốt trong hội thoại 08/11/2026 | Đã duyệt nghiệp vụ; bằng chứng xác minh, normalization, tests còn cần triển khai |
| [DEC-SRC-Q9-ERROR-001](#dec-src-q9-error-001--duyệt-503-stock_unavailable-của-source-api) | Q9: `GET /stock` khi **không có batch nào đã publish hoàn chỉnh** trả `503 STOCK_UNAVAILABLE` theo phong bì lỗi chuẩn Source, không coi tồn=0 | 08/11 | Chủ dự án xác nhận “ĐƯỢC. CẬP NHẬT 101 PR ĐI” sau khi được đề xuất chọn A `503 STOCK_UNAVAILABLE` | **Owner-approved mã lỗi Source API**; OpenAPI/code/tests chờ triển khai trong PR kỹ thuật |
| [DEC-DEV1-D1-01](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Hủy chuyển kho dùng TRANSFER_CANCELLED, actor/lý do/ts/before/after; không dùng TRANSFER_APPROVED | 08/11 | Chủ dự án “ĐỒNG Ý” ngày 08/11/2026; PR #127, [biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Audit contract duyệt; code/tests pending |
| [DEC-DEV1-D1-02](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | TRANSFER_CONFIRMED chỉ kho nguồn; TRANSFER_RECEIVED riêng cho kho đích | 08/11 | Chủ dự án “ĐỒNG Ý” ngày 08/11/2026; PR #127, [biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Audit contract duyệt; code/tests pending |
| [DEC-DEV1-D1-03](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Admin có thẩm quyền quản trị scope SKU theo market/pilot, version/hiệu lực/audit, không suy từ mapping | 08/11 | Chủ dự án “ĐỒNG Ý” ngày 08/11/2026; PR #121, [biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Policy duyệt; DDL/API/tests chờ review |
| [DEC-DEV1-D1-04](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Warehouse Manager cung cấp chứng cứ độc lập từ kho/WMS; admin có thẩm quyền duyệt, lưu evidence/approver/version/hiệu lực/audit; thiếu thì chặn | 08/11 | Chủ dự án “ĐỒNG Ý” ngày 08/11/2026; PR #120, [biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md) | Policy duyệt; DDL/API/tests chờ review |
| [DEC-DEV2-D2-001](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md#d2--dec-dev2-d2-001-approved) | D2 CSV UTF-8/schema versioned, stable rows, idempotent hash, lỗi/retry có kiểm soát | 08/11 | Chủ dự án: “d2 ... tôi đồng ý với bạn” | Approved policy; adapter/schema/tests pending |
| [DEC-DEV2-D3-001](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md#d3--dec-dev2-d3-001-approved-policy-dto-implementation-details-need-contract-tests) | D3 GPS 30 phút, offline có điều kiện, chỉ trong ca/chuyến, Dispatcher chỉ xem tài xế/chuyến được phân công; xoá GPS ngay sau trip/shift | 08/11 | Chủ dự án nêu 4 lựa chọn GPS cụ thể | Approved policy; GPS DTO/DB/cleanup/tests pending |
| [DEC-DEV2-D4-001](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md#d4--dec-dev2-d4-001-approved) | D4 thông báo theo template + biến allowlist, không được free-text | 08/11 | Chủ dự án: “Chọn cơ chế template có biến thay thế, không cho phép free-text tùy ý” | Approved; templates/API/tests pending |
| [DEC-GDPR-001](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md#d5--dec-dev2-d5-001-approved-policy-for-synthetic-mvp-real-data-legal-gate-remains) | D5 phải GDPR by design; policy giờ có số cụ thể, chưa chứng minh tuân thủ GDPR thực tế | 08/11 | Chủ dự án: “D5 tôi muốn tuân thủ gdpr” | Approved direction; legal assessment outstanding (PR #86 has overlapping draft) |
| [DEC-DEV2-D5-001](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md#d5--dec-dev2-d5-001-approved-policy-for-synthetic-mvp-real-data-legal-gate-remains) | D5 mốc 90/365/30/90 ngày theo loại, ngoại lệ tài xế/kế toán; **GPS xoá khi trip kết thúc**, không giữ 30 ngày | 08/11 | Chủ dự án: “d2, d5 tôi đồng ý với bạn”; GPS điều chỉnh D3 | Owner-approved product policy, legal/implementation pending; no production GDPR claim |

| [DEC-OWNER-20261109](#dec-owner-20261109--27-quyết-định-liên-workstream-đã-duyệt-ngày-09112026) | 27 quyết định chốt: S1–S5, T18-1–3, D7-1–4, G1–G5, N1–N5, M6-1, API-1–2, KPI-1–2 | 09/11 | Owner xác nhận rõ ràng 09/11; [biên bản](decisions/OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md) | **Approved contract; code/migration/E2E pending** |

**Không nằm trong bảng đã duyệt:** [ASM-004](#asm-004--mã-lỗi-cho-lỗi-kỹ-thuật-ngoài-danh-sách-06-mục-11) đang được file này ghi **chờ phê duyệt hợp đồng**; không ngầm chuyển sang “đã chốt”. ASM-008 của Dev 3 trong PR #55 cũng là **đề xuất chưa duyệt**. Câu hỏi hoặc phương án do Dev tự nêu không mặc nhiên trở thành quyết định đã chốt.

### Cách ghi nhận quyết định mới — bắt buộc

1. **Chỉ sau khi có xác nhận rõ ràng từ owner/nhóm có thẩm quyền**, bổ sung/sửa một mục tại **`docs/ASSUMPTIONS.md`** trong PR hiện tại hoặc PR tài liệu riêng. Không ghi “đã chốt” cho suy đoán, bình luận chưa được chấp thuận, hoặc PR chưa review.
2. Mỗi bản ghi phải có **mã duy nhất, ngày, người/phạm vi phê duyệt, câu chốt nguyên nghĩa, trường hợp biên, nguồn (URL PR/comment), tài liệu/code bị ảnh hưởng, tình trạng triển khai**. Nếu thay đổi quyết định cũ, ghi **superseded by** và giữ lịch sử, không xóa.
3. **Cùng PR** cập nhật các hợp đồng `01`–`09` liên quan và `docs/CHANGELOG.md` khi thay đổi API/DDL/quyền/bất biến; thêm migration và test khi triển khai code. Không được âm thầm code chỉ từ đề xuất.
4. Trước khi tạo PR Dev phải **đọc sổ và kiểm tra quyết định mới nhất**; PR description và checklist phải có dòng “Assumptions: reviewed / new decision IDs / none”. Reviewer từ chối merge nếu PR làm trái quyết định chốt hoặc thiếu ghi nhận.
5. Khi chủ dự án chốt thêm trong **cuộc trò chuyện**, trợ lý cập nhật file qua GitHub ngay **nếu có quyền công cụ tại lượt đó**; nếu không có quyền thì soạn bản vá/prompt để Dev cập nhật. **Không có tiến trình tự chạy/giám sát GitHub liên tục**, nên không thể tự cập nhật file khi không có tương tác.

---

## ASM-009 — Dữ liệu tham chiếu demo độc lập của Dev 2

- **Ngày:** 2026-11-07.
- **Lịch sử mã:** trước đây dùng ASM-008 trên nhánh Dev 2; đổi sang ASM-009 để không trùng
  ASM-008 của Dev 3 được sổ quyết định nhánh `docs/approved-assumptions-register-20261107`
  tham chiếu tới PR #55. Nội dung giả định kỹ thuật không đổi; không phê duyệt đề xuất của Dev 3.
- **Trạng thái:** giả định kỹ thuật cho dữ liệu tổng hợp; không sửa hợp đồng `05`/`06`.
- **Bối cảnh:** `08` §5.1–5.5 quy định số lượng/khoảng giá trị, nhưng không cho đủ giá trị từng bản ghi.
- **Lựa chọn:** random seed `20261104`; 7/5 người ở hai ca, 11 công nhân và 2 trưởng ca mỗi kho;
  cửa hàng dùng tọa độ gần đúng quanh ba kho. Xe chưa có sức chứa cụ thể trong `08` dùng giá trị demo
  được khai báo tập trung trong `seed/fleet.py`; dữ liệu này chưa chứng minh các kết quả kịch bản §5.6.
- **Sản phẩm:** đủ 100 SKU, phân bổ N1–N6 và 3 SKU pending đúng §5.2; các giá trị chưa được tài liệu cho
  dùng giá/khối lượng/thể tích tổng hợp. GTIN thuộc dải tổng hợp, có check digit, khớp local/global;
  đây là fixtures tham chiếu, chưa phải seed định lượng cho các kịch bản engine.
- **Nguồn:** 40 khách tổng hợp (30 doanh nghiệp, 10 consumer), mỗi khách 2 địa chỉ quanh ba vùng,
  email chỉ thuộc miền `.test`, không tạo số điện thoại thật. Chưa seed giờ nhận vì schema nguồn
  hiện thiếu trường này; SRC-Q8 đã được duyệt hướng bổ sung lịch nguồn và giờ nhận theo địa chỉ (DEC-SRC-001), nhưng schema/seed chưa triển khai.
- **Catalog nguồn:** đóng gói độc lập 100 SKU trong `source_system/seed/se`; test đối chiếu mọi trường
  sản phẩm với seed CFO để phát hiện lệch fixture. Không import ứng dụng CFO lúc chạy nguồn, không đọc
  dữ liệu vận hành CFO để ghi ngược; không đổi trạng thái mapping, không seed tồn kho/đơn kịch bản.
- **Roster kho tổng hợp (sau migration 0009/0010):** danh sách đích danh W02/W04–W09 vào ca sớm,
  W03/W10–W14 vào ca muộn của từng kho; không lấy số người từ `expected_staff`. Đây là fixture demo
  được gán cho manager demo đang có quyền, có lý do và audit `SHIFT_CHANGED`, không phải job tự xếp lịch.
  Giữ nguyên mọi lịch/điểm danh/lịch hủy đã có; không tự tạo attendance, lịch tài xế hay driving history.
- **Tính lặp lại:** chỉ thêm dữ liệu thiếu; bảo toàn mật khẩu, trạng thái khóa, cấu hình, phân công,
  ánh xạ sản phẩm và các bản ghi đã tồn tại. Mâu thuẫn định danh tài khoản/nhân viên/xe làm rollback.
  Không bật GPS hoặc sửa DPIA khi chạy seed tham chiếu; bật GPS demo vẫn là bước cấu hình có kiểm soát.
- **Ảnh hưởng:** `make seed-reference` / `seed-reference-docker` chạy tập con này; `make seed` vẫn là
  seed đầy đủ riêng và không được báo PASS khi generator kịch bản chưa có.

> Ghi nhận cách diễn giải/giả định theo `09_AI_Coding_Rules.md` mục 14. Mục ở đây **không** thay thế phê duyệt
> thay đổi hợp đồng: thay đổi `05`/`06` vẫn phải sửa tài liệu + migration + `CHANGELOG` trong cùng PR.

## ASM-001 — Cột chung `created_at` / `updated_at` cho mọi bảng CFO

- **Ngày:** 2026-11-06
- **Trạng thái:** đã chốt bởi nhóm (không có ngoại lệ). Chỉ ghi nhận cách diễn giải; không sửa `05`.
- **Bối cảnh:** `05` mục 1 quy định cột chung `created_at timestamptz NOT NULL DEFAULT now()` và
  `updated_at timestamptz NOT NULL DEFAULT now()` (trigger `set_updated_at`) "có ở mọi bảng nghiệp vụ",
  nhưng DDL chi tiết không lặp lại hai cột này cho từng bảng.
- **Diễn giải đã chốt:**
  1. "Bảng nghiệp vụ" = **toàn bộ 57 bảng CFO** có `CREATE TABLE` trong `05` (schema `ref`, `hr`, `stg`, `ops`,
     `plan`, `audit`); không áp dụng cho bảng `src_*` của hệ thống nguồn giả lập.
  2. Không thêm trùng cột đã có trong DDL: `ref.market` đã có cả hai cột; `ops.idempotency_key` đã có
     `created_at` nên chỉ thêm `updated_at`.
  3. Trigger `set_updated_at` (BEFORE UPDATE) được tạo và gắn cho mọi bảng có cột `updated_at` ở migration
     `0007_audit_views_triggers`.
- **Không thay đổi bất biến:** `audit.decision_log` và `ops.milestone_event` vẫn bị trigger `forbid_mutation`
  chặn UPDATE/DELETE; POD cũ vẫn không được UPDATE (`09` bất biến 13, 22). `updated_at` chỉ là siêu dữ liệu
  kỹ thuật: **không** phải dấu vết audit (audit nằm ở `audit.decision_log`) và **không** ngăn việc sửa dữ liệu;
  các quy tắc cấm cập nhật vẫn phải được thực thi riêng.
- **Mốc nghiệp vụ khác `created_at`:** các cột như `contacted_at`, `completed_at`, `computed_at`, `received_at`,
  `occurred_at`, `ts`, `as_of`, `synced_at` là thời điểm nghiệp vụ (hoặc của nguồn); `created_at` là thời điểm
  ghi bản ghi vào CFO. Hai loại không mặc nhiên trùng nghĩa và đều được giữ nguyên.
- **Ảnh hưởng:** migration `0002`–`0007`; model SQLAlchemy (M1) cần khai báo hai cột; test PostgreSQL kiểm tra
  kiểu, `NOT NULL`, giá trị mặc định (T2) và trigger cập nhật thời gian cùng các thao tác bị cấm (T4).

## ASM-002 — Diễn giải seed tham chiếu `0008_seed_reference`

- **Ngày:** 2026-11-06
- **Trạng thái:** **chủ dự án chấp thuận hướng ASM-002 ngày 07/11/2026** cho MVP. Các chi tiết seed được giữ như danh sách bên dưới; test/migration vẫn phải xác minh trước khi coi là đã chạy.
- **Bối cảnh:** `05` mục 11 liệt kê dữ liệu cần seed (market SE, N1–N6, special_flag, position, order_transition)
  nhưng không ghi đủ giá trị cho mọi cột.
- **Diễn giải:**
  1. **Vai trò "system"** trong bảng chuyển trạng thái (`05` mục 6; `app/domain/transitions.py`) không thuộc enum
     `ref.user_role`, nên `ops.order_transition.allowed_roles` lưu **mảng rỗng** cho các chuyển do hệ thống
     thực hiện. Không thêm giá trị enum mới.
  2. **`PLANNED → APPROVED`**: `requires_reason = false` (khớp `transitions.ALLOWED`); lý do chỉ bắt buộc khi
     chọn phương án khác hoặc lập tay, và được kiểm ở service qua `ALT_SELECTED` / `MANUAL_PLAN_CREATED`
     (`09` bất biến 14).
  3. **`ref.market` SE**: `gps_enabled = false`, `shadow_mode = false` (mặc định của `05`). `08` mục 5.1 yêu cầu
     `gps_enabled = true` **cho demo**; việc bật thuộc seed demo (`seed/generate_data.py`, Dev 2), không bật
     trong migration vì GPS là quyết định nhạy cảm cần DPIA (`04` mục 9, `09` mục 14.4).
     `source_api_key_ref = 'SOURCE_SE_API_KEY'` (tên biến môi trường, không phải bí mật); `source_base_url` để
     trống (cấu hình theo môi trường). `config` = `MarketConfig` mặc định `04` mục 8 cộng
     `routing.allow_fallback = true` (`06` Phụ lục A).
  4. **`handling_group.min_crew`**: N2 ghi "1–2" → seed `1` (cận dưới; cột "chỉ hiển thị, chưa ép buộc").
     `description` lấy nguyên văn cột "Mô tả" của `05` mục 11.
  5. **`hr.position`**: `name` tiếng Anh theo mã; `grp`: kho → `warehouse`; DRIVER, DISPATCHER → `transport`;
     STORE_MANAGER, SALES_* → `store`; CUSTOMER_SERVICE, IT_INTEGRATION, BUSINESS_OWNER, PROJECT_LEAD → `central`.
     `default_roles`: quản lý/phó/trưởng ca kho → `warehouse`; WAREHOUSE_OPERATOR, FORKLIFT_OPERATOR → rỗng
     (không có tài khoản, `09` bất biến 18); STORE_MANAGER, SALES_* → `sales`; còn lại theo tên vai trò.
     `default_kpi_scopes` đúng chú thích `05` mục 4.
  6. **Không seed** tài khoản, nhân viên, mật khẩu, ngày lễ hay dữ liệu demo trong migration (`08` mục 5 —
     `seed/generate_data.py`, Dev 2; `09` bất biến 25).
- **Ảnh hưởng:** `0008_seed_reference`; test `test_migration_0006_0008.py` đối chiếu seed `order_transition` với
  `transitions.ALLOWED` và `MarketConfig()`.

## ASM-003 — Chi tiết xác thực chưa có trong `06` mục 4

- **Ngày:** 2026-11-06
- **Trạng thái:** **chủ dự án chấp thuận hướng ASM-003 ngày 07/11/2026** cho MVP. Giới hạn login 5 lượt/phút/IP chỉ là giới hạn demo một instance; triển khai nhiều instance phải dùng shared rate limiter, không tuyên bố đây là phòng chống brute-force hoàn chỉnh.
- **Diễn giải:**
  1. **Giới hạn tần suất login:** tính **mọi lần thử** (đúng hoặc sai) theo **IP client**, cửa sổ trượt 60 giây,
     tối đa 5 lần; lần thứ 6 → `429`. Bộ đếm in-memory theo tiến trình (MVP một instance), dùng đồng hồ đơn điệu
     nên không bị ảnh hưởng bởi `APP_NOW`.
  2. **Mã lỗi khi `429`:** `06` chỉ quy định HTTP 429, không có mã nghiệp vụ riêng; dùng mã có sẵn `AUTH_INVALID`
     với thông báo "Too many login attempts. Try again in a minute." (không thêm mã lỗi mới — `09` mục 13).
     Frontend phân biệt theo HTTP status (`03` màn Sign in).
  3. **`POST /auth/logout`:** cần token hợp lệ; trả `204 No Content` (06 không quy định thân phản hồi).
  4. **Email đăng nhập** so khớp không phân biệt hoa thường; sai email, sai mật khẩu, tài khoản khóa hoặc nhân viên
     `terminated` đều trả cùng `401 AUTH_INVALID` "Invalid email or password." (không lộ tài khoản tồn tại).
  5. **Tài khoản hệ thống** (không có `employee_id`): `name`, `market` = `null`, `location_ids` = `[]`, `locale` = `en`.
  6. **`location_ids`** = địa điểm của các phân công đang hiệu lực hôm nay theo múi giờ market.
  7. **Hồ sơ đọc lại từ DB mỗi request** (vai trò, `kpi_scopes`, `is_active`, trạng thái nhân viên) để thỏa
     US-EMP-03 AC4; claims trong token chỉ để client hiển thị.

## ASM-004 — Mã lỗi cho lỗi kỹ thuật ngoài danh sách `06` mục 1.1

- **Ngày:** 2026-11-06
- **Trạng thái:** đã chuyển thành **đề xuất thay đổi hợp đồng** `06` v1.2.1 + `CHANGELOG` trong PR #8, **chờ nhóm
  duyệt**. Mục ASM này chỉ ghi bối cảnh; không thay thế phê duyệt. PR #8 không được merge trước khi duyệt.
- **Bối cảnh:** `06` mục 1.1 bắt buộc mọi lỗi theo định dạng `{error: {code, message, details, correlation_id}}`
  nhưng danh sách mã chỉ gồm mã nghiệp vụ; HTTP 500/503 và một số 4xx kỹ thuật không có mã.
- **Diễn giải đang triển khai:**
  1. Lỗi không bắt (500) → `code = "INTERNAL_ERROR"`, thông báo cố định "Internal server error.", không stack
     trace, không thông điệp gốc (có thể chứa chuỗi kết nối hoặc PII). Đây là **mã mới** chưa có trong `06`; nếu
     nhóm đồng ý cần bổ sung vào `06` mục 1.1 + `CHANGELOG`, nếu không thì chọn mã khác.
  2. Lỗi Pydantic → `422 VALIDATION_ERROR`, `details.errors` chỉ gồm `loc`, `type`, `msg` (không trả lại giá trị
     đầu vào). HTTPException: 401 → `AUTH_INVALID`, 403 → `FORBIDDEN`, 404 → `NOT_FOUND`, 4xx khác (400, 405…)
     → `VALIDATION_ERROR`.
  3. `GET /health` khi DB lỗi trả `503` với thân health (`status = "error"`, `db = "unavailable"`), không dùng
     định dạng lỗi, để công cụ uptime/smoke đọc được (06 mục 15).

## ASM-005 — Quy tắc xác nhận / từ chối ánh xạ và phạm vi đơn CFO

- **Ngày:** 2026-11-07
- **Trạng thái:** chủ dự án chốt **quy tắc phân luồng** ngày 2026-11-07: đơn có bất kỳ SKU chưa mapping confirmed không dùng CFO, tiếp tục quy trình cũ. Quy tắc xử lý task xác nhận/từ chối chi tiết bên dưới vẫn cần rà soát và được triển khai bằng PR code riêng.
- **Quyết định phạm vi:** ban đầu IT xác nhận khoảng 100 SKU để phục vụ pilot, sau đó mở rộng dần. Mỗi đơn chỉ đủ điều kiện **đưa vào luồng điều phối CFO nếu 100% SKU của đơn đã mapping confirmed**; số 100 là phạm vi danh mục pilot, không phải giới hạn cố định. Nếu thiếu dù chỉ một SKU, **toàn bộ đơn tiếp tục theo quy trình xử lý cũ**, không chờ IT trong CFO, không giữ chỗ, không lập kế hoạch và không được CFO duyệt/xác nhận.
- **Bối cảnh phần mapping:** `06` mục 12/12.1 và US-PRD-02/03 chưa mô tả đủ trạng thái task xác nhận/từ chối, ai ghi `mapped_by` và lý do từ chối được trình bày ở đâu.
- **Diễn giải:**
  1. Chỉ `admin` **có hồ sơ nhân viên** được xác nhận/từ chối: `ck_se_confirmed` bắt buộc `mapped_by`
     (FK `hr.employee`). Admin hệ thống không có nhân viên → `403 FORBIDDEN`.
  2. Sau xác nhận hoặc từ chối, `mapping_task.status = done`, `resolved_by` = nhân viên, `resolved_at` = clock.
  3. Task đã `done` **không từ chối lại** được (`422 VALIDATION_ERROR`, `details.field = status`). SKU đã
     `confirmed` không từ chối được (`details.field = mapping_status`), vì đơn đã lập kế hoạch đang dùng ánh xạ đó.
  4. Task đã từ chối **vẫn xác nhận được** (nguồn có thể bổ sung dữ liệu sản phẩm); thay đổi được ghi
     `MAPPING_CONFIRMED` với trước/sau.
  5. IT ghi lý do từ chối trong `decision_log MAPPING_REJECTED` và trên mapping task/SKU cho đội IT. **Không** gắn đơn chưa mapping vào hàng đợi Dispatcher để chờ xử lý; đơn đó tiếp tục quy trình cũ. Cách hiển thị chi tiết lý do từ chối tại IT cần chốt trong contract API.
  6. `blocked_order_count` hiện là trường legacy gắn với đơn `BLOCKED_UNMAPPED_SKU`; với quyết định mới **không được dùng làm hàng đợi chờ đơn CFO**. Dev phải đề xuất cách thể hiện số SKU/tần suất đơn không đủ điều kiện nếu cần KPI, không tự tái sử dụng trường này như số đơn đang chờ lập kế hoạch.
  7. SKU chưa có trong `product_<cc>` không xác nhận được (`details.field = local_sku`): cần đồng bộ sản phẩm
     trước, vì các cột tên/đơn vị bán là NOT NULL.
- **Quy tắc chống trùng và ranh giới:** phân luồng phải xảy ra **trước khi CFO tạo planning run/hold hoặc cam kết nguồn lực**. Dữ liệu POS/WMS/ERP giữ nguyên, CFO chỉ GET; việc xử lý theo quy trình cũ vẫn do hệ thống/quy trình hiện tại đảm nhiệm. Việc IT mapping sau này **không tự chuyển** đơn đã đi quy trình cũ vào CFO. Cần cơ chế bền vững để nhận diện đơn đã được xử lý ở luồng cũ và ngăn hai luồng xử lý cùng một đơn; chưa có hợp đồng dữ liệu đầy đủ cho cơ chế này, Dev phải đề xuất ở PR triển khai và kiểm tra khả năng API POS cung cấp trạng thái/owner luồng.
- **Chưa thay đổi triển khai:** logic hiện có `BLOCKED_UNMAPPED_SKU → SUBMITTED` và `mapping_service.confirm()` còn khác quyết định mới. Không dùng `HANDLED_EXTERNALLY` đã bỏ ở v1.2. Không được cho agent tự đưa đơn cũ về CFO bằng logic mở khóa hiện tại.
- **Còn cần nhóm rà soát:** chi tiết các mục 1, 3, 4 và thiết kế trạng thái/quyền sở hữu luồng để bảo vệ một đơn chỉ có một hệ thống điều phối.

## ASM-006 — Quy tắc ghi nhân sự chưa ghi trong `06` mục 13

- **Ngày:** 2026-11-07
- **Trạng thái:** **chủ dự án chấp thuận nguyên tắc ASM-006 ngày 07/11/2026**, có điều chỉnh bắt buộc: thay đổi nhân sự/quản lý/owner phải có audit, sửa dữ liệu quá khứ cần quyền + lý do. Các tình huống biên và schema/API cần test, chưa phải code đã hoàn thành.
- **Bối cảnh:** `06` mục 13 cho đường dẫn và thân của `POST /employees/{id}/assignments`, `POST …/terminate`,
  `PUT /locations/{id}/managers`, `PATCH /locations/{id}/owner` nhưng không nêu phản hồi và một số quy tắc biên.
- **Diễn giải:**
  1. **Phản hồi:** trả lại tài nguyên theo schema đọc đã duyệt `06` v1.3 mục 13.1 (`EmployeeOut` / `LocationOut`,
     góc nhìn admin). Thân `PATCH …/owner` là `{ "owner_employee_id": <id> }` (tên cột `05`).
  2. **Chuyển công tác:** thao tác thường cho phép `start_date` ≥ hôm nay (múi giờ market) và ≥ `hire_date`, phải sau ngày bắt đầu phân công đang mở; phân công cũ đóng `end_date = start_date − 1`. Cùng địa điểm, khác market, nơi đã đóng → `422`. **Điều chỉnh hồi tố** chỉ admin có quyền, kèm lý do bắt buộc, ghi log trước/sau trong cùng transaction; không âm thầm ghi đè lịch sử hoặc tạo hai phân công chồng ngày.
  3. **Quản lý không được chuyển hoặc nghỉ khi còn giữ vai trò quản lý** (hiện tại hoặc tương lai) tại địa điểm cũ:
     `422` (`details.field = employee_id`). Admin thay quản lý trước, để không địa điểm nào mất quản lý chính ngầm.
  4. **Nghỉ việc:** `status = terminated`, `employee.end_date` = hôm nay, phân công còn hiệu lực sau hôm nay
     đóng ở hôm nay, `app_user.is_active = false`. Nhân viên có phân công bắt đầu trong tương lai → `422`.
     Không xóa bản ghi.
  5. **Đổi quản lý:** bản ghi đang mở của cấp đổi người → `valid_to = max(valid_from, hôm nay) − 1`. Bản ghi bắt
     đầu từ hôm nay trở đi trở thành "không bao giờ hiệu lực" nhưng vẫn giữ lịch sử. Người mới có
     `valid_from` = hôm nay. Cấp không đổi người giữ nguyên bản ghi. `deputy_employee_id` vắng / `null` → đóng phó
     hiện tại.
  6. **Owner mặc định** (US-EMP-01 AC4): khi đổi quản lý chính, owner trống hoặc đang là quản lý chính cũ → chuyển
     sang quản lý chính mới. Owner do admin gán riêng được giữ.
  7. **Bắt buộc ghi lịch sử.** Ghi `audit.decision_log` trong cùng transaction với các thao tác đổi phân công/chuyển công tác (`EMPLOYEE_ASSIGNMENT_CHANGED` đã có trong `04` mục 10), thay quản lý/owner, nghỉ việc và điều chỉnh hồi tố. Phải có `actor`, `before`, `after`, `correlation_id`; điều chỉnh hồi tố bắt buộc có lý do. Đối với các nghiệp vụ chưa có mã action chuẩn (đổi owner/quản lý/nghỉ việc), Dev đề xuất bổ sung mã vào `04`/`06`, test và CHANGELOG trước khi triển khai; **không bỏ audit**.
- **Đã chốt:** quản lý phải có người thay hợp lệ trước khi chuyển/nghỉ; tài khoản người nghỉ bị khóa và lịch sử không bị xóa; owner admin gán riêng được giữ. **Điều chỉnh hồi tố** được phép cho admin với lý do và log. **Chờ thiết kế kỹ thuật:** action codes còn thiếu, kiểm tra các ràng buộc ngày hiệu lực và test thao tác atomic.

## ASM-007 — Quy tắc điểm danh chưa ghi trong `06` mục 13

- **Ngày:** 2026-11-07
- **Trạng thái:** **chủ dự án chấp thuận ASM-007 với điều chỉnh Q11 ngày 07/11/2026**. Warehouse Manager là người tạo/sửa lịch làm chính thức của từng người, CFO không được tự xếp/đổi ca dựa theo `expected_staff`. Chỉnh điểm danh/lịch phải ghi lịch sử; sửa ngày quá khứ bắt buộc có quyền và lý do.
- **Diễn giải** cho `PUT /warehouses/{id}/attendance` (tầng service `hr_service.set_attendance`):
  1. **Roster** trong ngày được tạo từ **lịch phân ca chính thức do Warehouse Manager lưu**, sau khi kiểm nhân viên đang được phân công tại kho và chưa nghỉ việc. `hr.attendance` ghi điểm danh thực tế trên các lịch đó. Service không tự tạo lịch mới từ số lượng `expected_staff`; nhân viên không nằm trong lịch chính thức → `422` và yêu cầu quản lý cập nhật lịch trước. 
     **Schema hiện có chưa tách lịch phân ca cá nhân khỏi attendance**: Dev 1 phải đề xuất bổ sung cấu trúc dữ liệu (vd. `hr.employee_shift_schedule`) và migration trong PR code riêng, không âm thầm biến điểm danh thành nguồn phân ca.
  2. `all_present` đặt mọi dòng của roster **trừ `leave`** thành `present` bằng một câu UPDATE, rồi `items` ghi đè.
     Trạng thái hợp lệ trong `items`: `present`, `absent`, `leave` (`planned` chỉ do job sinh).
  3. **Warehouse Manager** có phân công quản lý hợp lệ tại đúng kho lập/sửa lịch phân ca. Điểm danh thực tế do tài khoản warehouse được phép của chính kho đó ghi theo phân quyền hiện hành; admin/dispatcher chỉ đọc điểm danh thường, không được tự phân ca thay Warehouse Manager. Ngoài kho → `404`, không đủ quyền → `403`. Cần chốt rõ guard theo chức danh ở API trước khi code.
  4. Mỗi lần ghi điểm danh phải có `ATTENDANCE_CHANGED` với before/after, changed employee IDs (không PII). Mỗi lần Warehouse Manager lập/đổi lịch nhân viên phải ghi `SHIFT_CHANGED`, actor, trước/sau, ngày hiệu lực. Mọi ghi log trong **cùng transaction** với thay đổi.
  5. Lịch phân ca chính thức cho tương lai do Warehouse Manager lập/sửa; điểm danh ghi đúng ngày làm, người được ủy quyền ở kho có thể ghi `present`/`absent`/`leave`. **Sửa dữ liệu quá khứ** chỉ với quyền hợp lệ, lý do bắt buộc và log, không sửa âm thầm. Việc `all_present` chỉ tác động những người có trong lịch ca chính thức, không tự thêm/đổi ca.
- **Q11 đã chốt:** `expected_staff` ở `shift_template` chỉ là **số lượng kế hoạch để so sánh**, không phải quota tự phân ca; không tự chia đều, không đưa nhân viên dư vào ca cuối. `attendance_gen` chỉ được tạo dòng `planned` từ **lịch người–ca đã được Warehouse Manager xác nhận**, không được tự suy lịch. Thiếu lịch chính thức → báo thiếu dữ liệu/công suất chưa xác minh, không làm giả danh sách nhân viên. **PR #37** đã được Dev 1 báo cập nhật Q11 theo ASM-007 trong comment, nhưng vẫn phải review/rebase trước khi merge; không áp dụng lại Q11=B cũ.

## DEC-SALES-001 — Sales xác nhận có điều kiện và sync-now

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #43 đã merge](https://github.com/qaztyhn/cfo-itconsultant/pull/43).
- Sales vẫn submit đơn trên POS; **CFO là ứng dụng độc lập, chỉ đọc POS/WMS/ERP**, không ghi ngược và không gộp database. Sales có `Sync now` để yêu cầu CFO đọc đơn ngay, polling 5 phút làm dự phòng.
- CFO **không tự phê duyệt**. Sales của đúng cửa hàng được **chủ động** confirm duy nhất phương án **rank 1 tiêu chuẩn**: cả 5 gate pass, reserve safe, **một xe**, nguồn mới và hold còn hạn; không ngoại lệ/transfer/manual/replan/đổi ngày. Dùng chung `ApprovalService` để kiểm tra lại và lock trước commit; trường hợp khác thuộc Dispatcher.
- FIFO là **thứ tự hiển thị** `submitted_at,id`, không ép mọi đơn được thực thi FIFO; không lấn nguồn lực đã `committed` cho đơn cũ. Đơn cũ chưa duyệt gây tranh chấp nguồn lực phải chuyển Dispatcher.
- **Triển khai:** [`docs/DECISION_SALES_CONFIRMATION.md`](DECISION_SALES_CONFIRMATION.md) là tài liệu chi tiết; phê duyệt nghiệp vụ **không đồng nghĩa** API/UI đã chạy end-to-end.

## DEC-ROUTING-001 — Sales kiểm CFO trước khi điều phối thủ công

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53 Q14](https://github.com/qaztyhn/cfo-itconsultant/pull/53), [ASM-005/PR #49](https://github.com/qaztyhn/cfo-itconsultant/pull/49).
- Quy trình: **(1)** Sales nhập/submit đơn POS → **(2)** Sales bắt buộc kiểm trạng thái tại CFO (`Sync & check routing`) **trước khi bắt đầu điều phối thủ công** → **(3)** toàn bộ SKU confirmed thì dùng CFO, có ít nhất một SKU chưa confirmed thì **toàn bộ đơn** dùng quy trình thủ công cũ.
- Quy tắc được duyệt của **Q14 = phương án A**: mỗi đơn nguồn chỉ có một quyết định phân luồng đã lưu (`cfo` hoặc `legacy`), không tự chuyển luồng theo bản cập nhật mapping về sau. `legacy` không có plan, hold, approve trong CFO. Dữ liệu chưa đủ/CFO hoặc nguồn không truy cập được = **unresolved**, **không được mặc định thành legacy hoặc xác nhận giao**.
- Quy trình cũ được nhân viên **điều phối thủ công**, không có hệ thống tự động điều phối cạnh tranh. Vì CFO không ghi ngược POS, bảng routing nội bộ **không tự ngăn** nhân viên đã thực hiện thủ công; cần bước xác nhận bàn giao/audit và cơ chế chống xử lý trùng trước rollout.
- **Thiết kế Dev đề xuất, chưa được xem là DDL/API đã duyệt:** bảng `ops.order_routing`, `routing-ack` với lựa chọn `legacy_acknowledged` / `manual_started`, routing từ polling, cách xử lý đơn cũ. Xem [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) và yêu cầu review implementation. **Chưa có quyết định cho phép tự động chuyển sang quy trình cũ khi CFO lỗi**; phải hỏi owner nếu muốn làm ngoại lệ.

## DEC-ROUTING-002 — Chỉ người kiểm tra mới ghi quyết định phân luồng

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án, trong phiên làm việc. Đây là câu trả lời cho câu hỏi "manual_started và quyết định bất biến" nêu ở [PR #59](https://github.com/qaztyhn/cfo-itconsultant/pull/59): **chọn phương án A, có điều chỉnh**.
- **Câu chốt (nguyên nghĩa):**
  > Polling chỉ đồng bộ dữ liệu nguồn, không được ghi quyết định phân luồng cuối cùng cfo/legacy. Quyết định chỉ được lưu khi Sales thực hiện Sync & check routing trên CFO hoặc Dispatcher thực hiện kiểm tra được ủy quyền, dựa trên dữ liệu nguồn mới nhất và trạng thái mapping tại thời điểm đó. Một khi đã ghi quyết định thì không tự chuyển luồng. Nếu Sales đã bắt đầu điều phối thủ công trước khi kiểm CFO, phải ghi nhận ngoại lệ có lý do và audit; nếu đã có quyết định cfo thì không được tự đổi sang legacy, phải chuyển Dispatcher xử lý để tránh double fulfilment.
- **Trường hợp biên:**
  1. **Polling** (job 5 phút):
     - chỉ đồng bộ và lưu dữ liệu nguồn;
     - cập nhật theo version các đơn **đã** có quyết định `cfo`;
     - **không** ghi `ops.order_routing`;
     - **không** tạo `customer_order` cho đơn chưa có quyết định;
     - không tạo plan/hold.
  2. **Sales Sync & check** hoặc **Dispatcher kiểm tra được ủy quyền**:
     - CFO đọc lại nguồn ngay lúc đó và đánh giá mapping tại thời điểm đó.
     - Đủ dữ liệu → ghi một quyết định duy nhất kèm người và vai trò (`decided_by_user_id`, `decided_by_role` ∈ sales/dispatcher) và ghi `ROUTING_DECIDED`.
     - Thiếu dữ liệu → `unresolved`, không ghi gì.
  3. **Sales đã điều phối tay trước khi kiểm, chưa có quyết định:**
     - ghi `legacy` với `reason_code = manual_started`, `reason_text` bắt buộc;
     - ghi audit `ROUTING_MANUAL_START_RECORDED`.
  4. **Sales báo đã điều phối tay nhưng đơn đã có quyết định `cfo`:**
     - **không** đổi luồng;
     - ghi audit `ROUTING_MANUAL_CONFLICT_ESCALATED` (lý do bắt buộc);
     - tạo alert `ROUTING_MANUAL_CONFLICT` cho Dispatcher.
     - Dispatcher xử lý bằng các luồng có sẵn (hủy/giữ kế hoạch CFO, liên hệ cửa hàng), để tránh giao trùng.
  5. **Đơn đã có `legacy`:** mapping về sau không kéo đơn vào CFO.
- **Thay thế (superseded):** phần "polling được phép quyết định cfo/legacy, nhưng không tự tạo hold" trong [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) / DEC-ROUTING-001 và câu "`manual_started` … kể cả khi đủ SKU" của `06` §5.0.2 cũ, khi đơn đã có quyết định `cfo`.
- **Ảnh hưởng:**
  - `06` §5.0.2, `05` (`ops.order_routing`), `04` §10 (mã hành động), `CHANGELOG`;
  - migration `0011_routing_decided_by_check` và test PostgreSQL;
  - Dev 2: ingestion/polling và `sync-now`; Dev 3: màn Sync & check và nút báo điều phối tay.
- **Tình trạng triển khai:**
  - Đã có ràng buộc DB (0011): không có quyết định thiếu người/vai trò; `manual_started` cần lý do; quyết định bất biến.
  - Service/API của `sync-now`, `routing-ack` và escalation **chưa code**.

## DEC-SHIFTS-001 — Q12 lịch làm chính thức của kho và tài xế

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53 Q12](https://github.com/qaztyhn/cfo-itconsultant/pull/53), [PR #50](https://github.com/qaztyhn/cfo-itconsultant/pull/50).
- **Q12a = A:** tối đa **1 ca chính thức/người/ngày** cho MVP. Ca có thể kéo qua ngày hôm sau; khi đánh giá xung đột phải kiểm cả khoảng thời gian, không chỉ ngày bắt đầu.
- **Q12b = A:** Warehouse Manager chính hoặc phó đang hiệu lực, có `can_approve=true`, được lập/cập nhật lịch chính thức cho nhân viên kho và **tài xế thuộc kho**. Dispatcher/admin chỉ đọc lịch theo đề xuất nghiệp vụ hiện tại; quyền ghi phải kiểm ở server theo kho.
- **Q12c = A:** quản lý được phép sửa lịch quá khứ với **lý do bắt buộc** và audit actor + before/after trong cùng transaction; không xóa lịch sử.
- **Q12d = A:** thiếu lịch chính thức thì `schedule_verified=false`, công suất xác minh = **0**; không tự tạo người dựa trên `expected_staff`.
- Lịch điểm danh thực tế tách lịch phân ca; `expected_staff` chỉ là **mục tiêu để so sánh**, không phải quota, không cho auto-assign/dồn nhân viên dư vào ca cuối. `attendance_gen` chỉ sao lịch do Manager xác nhận.
- **Thiết kế Dev đề xuất cần review:** một bảng `hr.employee_shift_schedule` cho kho và tài xế, ca tùy chỉnh, nghỉ giữa ca, API `shift-schedule`, lịch sử hủy/thay ca, quyền chi tiết, xử lý ca qua nửa đêm. Tham khảo [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53). Không tự coi schema đề xuất là migration đã chạy.

## DEC-AUDIT-001 — Q13 mã nhật ký nhân sự

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53 Q13](https://github.com/qaztyhn/cfo-itconsultant/pull/53), ASM-006.
- Chấp thuận các action codes: `LOCATION_MANAGER_CHANGED`, `LOCATION_OWNER_CHANGED`, `EMPLOYEE_TERMINATED`; chuyển công tác dùng `EMPLOYEE_ASSIGNMENT_CHANGED` đã có.
- Chỉnh hồi tố phân công phải là admin có quyền, `reason_code=retroactive`, có `reason_text`, không tạo hai phân công hiệu lực trùng khoảng. Mọi thay đổi nhân sự/quản lý/owner/termination phải được audit actor, before/after, correlation ID trong cùng transaction.
- **Triển khai:** bổ sung code chuẩn vào `04`/`06` và actions, migration/test khi thích hợp; không coi đã có đầy đủ code chỉ vì owner đồng ý mã.

## DEC-DRIVER-001 — Khung giờ làm, nghỉ và giới hạn lái xe

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án; [PR #53](https://github.com/qaztyhn/cfo-itconsultant/pull/53) và [PR #54](https://github.com/qaztyhn/cfo-itconsultant/pull/54), bao gồm phê duyệt đề xuất cho 5 nước Bắc Âu (SE, DK, NO, FI, IS).
- **Bất biến lập kế hoạch:** thời gian chuẩn bị/lên hàng phải nằm trong **ca kho chính thức có công suất**, và **toàn bộ ca nhiệm vụ tài xế** phù hợp lịch làm **chính thức của chính tài xế đó** (lên hàng/chờ, chạy xe, dỡ hàng, quay lại kho khi thuộc chuyến). Kiểm tra lịch bận đã nhận, bằng lái, giờ nghỉ và ca qua nửa đêm; **không mặc định 24/7**. Thiếu lịch hoặc lịch sử liên quan → không đưa ra phương án có thể duyệt một cách tự động.
- **Mốc mặc định của MVP:** nghỉ hằng ngày giữa các ca **11 giờ liên tục** (tài xế; nhân viên kho dùng mặc định thận trọng, tùy luật và thỏa ước). Nghỉ rút ngắn **9 giờ bị tắt khi tự động lập kế hoạch MVP**. Không có “override” tùy tiện vượt quy tắc an toàn.
- **Với vận tải thuộc phạm vi Quy định (EC) 561/2006 / quy định EEA tương ứng:** phải phân biệt **giờ lái xe** khỏi **tổng giờ làm/nhiệm vụ**; giới hạn thường dùng **9 giờ lái/ngày**, trường hợp đủ điều kiện có thể **10 giờ tối đa hai lần/tuần**; sau không quá **4 giờ 30 phút lái liên tục** phải có **45 phút nghỉ**, hoặc chia **15 phút rồi 30 phút**. Ngoại lệ 9 giờ nghỉ hằng ngày (nếu hợp lệ, không quá 3 lần giữa hai kỳ nghỉ hằng tuần) và các ngoại lệ khác **không tự kích hoạt trong MVP**; việc áp dụng phải kiểm tra phạm vi, nghỉ tuần, lái tuần/2 tuần, dữ liệu lịch sử.
- **Phạm vi là theo quốc gia + xe + loại hình vận tải** (nội địa/quốc tế/cabotage, trọng lượng được phép gồm rơ-moóc, ngoại lệ), **không áp dụng rập khuôn cho mọi xe và tài xế**. Các nước Bắc Âu cùng hệ thống EU/EEA liên quan nhưng có khác biệt thi hành/thỏa ước. Mốc cấu hình pilot **không phải chứng nhận tuân thủ pháp luật**; phải rà soát với bộ phận pháp lý/vận hành từng nước trước khi triển khai thật.
- Engine phải kiểm tra **thời gian làm nhiệm vụ** và **thời gian lái thực** riêng biệt; `driver_max_hours_day=9` trong code hiện tại **không được tự diễn giải** là đủ kiểm tra quy tắc lái xe của EU/EEA. Ca và dữ liệu nghỉ thiếu phải hiển thị lý do không thể duyệt, không chỉ coi là “không có tài xế”.
- **Triển khai:** Dev 1 phối hợp lịch chính thức Q12, sửa engine/kiểm thử trong PR #54; tài liệu/DB/API, seed driver, dữ liệu lịch sử chuyến và phạm vi áp dụng vẫn cần PR triển khai và test. Nguồn kiểm tra phạm vi: [European Commission — driving time and rest periods](https://transport.ec.europa.eu/transport-modes/road/social-provisions/driving-time-and-rest-periods_en), [EUR-Lex — Regulation 561/2006](https://eur-lex.europa.eu/eli/reg/2006/561/oj).

## DEC-DEV2-D7-001 — D7: Dữ liệu xe và lịch sử tài xế synthetic cho demo

- **Ngày phê duyệt:** 2026-11-08. **Người duyệt:** chủ dự án, trả lời “tôi đồng ý” với **D7-A đến D7-E** trong cuộc trò chuyện dự án sau khi xem [đề xuất D7 trong PR #84](https://github.com/qaztyhn/cfo-itconsultant/pull/84). Đây là quyết định riêng của **D7**, không duyệt D1–D6 hoặc D8 trong cùng bảng Dev 2. **Trạng thái:** approved (chính sách demo), implementation/test còn chờ.
- **D7-A — Fixture synthetic:** Dev 2 được tạo dữ liệu demo cho khoảng 8–10 xe và 10 tài xế của pilot SE; ghi rõ nguồn `synthetic_demo`, loại xe, `capacity_kg` (khối lượng hàng chở được), `max_permissible_mass_kg` (khối lượng tối đa được phép), bằng yêu cầu, phạm vi `regulation_561_scope` (`in_scope|out_of_scope|unknown`) và bối cảnh nước/loại vận tải/rơ-moóc/ngoại lệ nếu áp dụng. **Không suy ra khối lượng tối đa được phép từ tải trọng hàng**, và không tự coi mọi van là ngoài phạm vi. Giá trị được seed phải nhất quán về mặt vật lý; sửa ví dụ cũ “van 3,5 t chở 3.500 kg” tại `08` §5.3. Thiếu căn cứ phân loại thì để `unknown`.
- **D7-B — 11 giờ nghỉ:** kế thừa `DEC-DRIVER-001`: mặc định nghỉ hằng ngày **11 giờ liên tục**; không tự kích hoạt ngoại lệ nghỉ 9 giờ trong MVP. Không có override để bỏ qua safety gate.
- **D7-C — Tách giờ làm/lái:** tách `duty_start/end` (toàn nhiệm vụ, gồm lên hàng/chờ/dỡ/quay về) với `driving_min` và lịch sử lái/nghỉ; kiểm ca tài xế theo lịch chính thức (đồng thời ca/công suất kho riêng), giấy phép, lịch bận, phạm vi quy định và các giới hạn liên quan khi `in_scope`. Cấu hình theo market, không hard-code cho mọi nước.
- **D7-D — Thiếu dữ liệu thì fail-closed:** thiếu ca tài xế, thiếu lịch sử làm việc/nghỉ bắt buộc, giấy phép, khối lượng được phép hoặc thiếu thông tin phân loại phạm vi sẽ không cho phép tự động đưa ra phương án **có thể duyệt**. Trả lý do cụ thể (như `DRIVER_HISTORY_MISSING`, `VEHICLE_SCOPE_UNKNOWN`, `DRIVER_REST_INSUFFICIENT`) để UI phân biệt với đơn thuần hết tài xế. Không biến `unknown` thành `out_of_scope`.
- **D7-E — Bộ test chung Dev 1 / Dev 2:** Dev 2 tạo fixture **56 ngày lịch sử synthetic** của từng tài xế (bao gồm thời gian làm, lái, nghỉ và trạng thái completeness) cùng ca chính thức tương lai; Dev 1 sử dụng để kiểm tra engine và T14/T16. Tối thiểu: trường hợp hợp lệ, nghỉ chưa đủ 11 giờ, vượt giới hạn lái, thiếu lịch sử, ca tài xế vắng, bằng hết hạn, xe `unknown`, bối cảnh vận tải/rơ-moóc thay đổi phạm vi, ca qua nửa đêm. Seed phải có ngày/giờ/timezone nhất quán, có thể chạy lại idempotent, không ghi đè lịch/điểm danh do người quản lý xác nhận.
- **Ranh giới:** chỉ phê duyệt **dữ liệu synthetic và chính sách fail-closed của MVP**, **không chứng nhận tuân thủ pháp luật** cho vận tải thực tế ở Thụy Điển hay nước Bắc Âu khác. Trước vận hành thật phải xác minh dữ liệu xe/tài xế và pháp luật áp dụng, bao gồm ngoại lệ theo nước, xe và loại hình vận tải; không suy đoán từ nhãn loại xe. Không mở rộng đặc quyền phân ca: vẫn theo `ASM-007`/`DEC-SHIFTS-001`.
- **Phân công:** Dev 2 seed/fixture và test PostgreSQL; Dev 1 review DTO/migration nếu phải bổ sung dữ liệu, tích hợp Planner/Approval và test golden scenarios; Dev 3 hiển thị lý do không thể duyệt nếu thiếu ca/lịch sử/xe. Chỉ đánh dấu hoàn thành sau khi có PR code, CI và kiểm thử E2E; PR này chỉ đồng bộ tài liệu.

## DEC-ORS-001 — Thời hạn cache ước lượng tuyến ORS

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án sau review [PR #67](https://github.com/qaztyhn/cfo-itconsultant/pull/67), cũng bao gồm sửa lỗi từ #65.
- **Quyết định:** chấp nhận `MarketConfig.routing.fallback_retry_min = 60` **phút** mặc định trong MVP, giá trị phải > 0 và có thể cấu hình riêng theo market. Tuyến `fallback` là **ước lượng**, phải được nhận diện/gắn nhãn rõ khi sử dụng hoặc trình bày, không được thể hiện như dữ liệu ORS thực tế.
- **Điều kiện:** chỉ áp dụng fallback khi `routing.allow_fallback = true`. Khi bản ghi fallback còn trong 60 phút thì cho phép dùng lại; hết hạn phải thử gọi ORS để thay bằng tuyến `ors` nếu khả dụng. Nếu ORS tiếp tục lỗi và thị trường cho phép fallback, có thể dùng lại ước lượng với thời điểm tính mới để hạn chế retry liên tục. Nếu fallback bị tắt, không được âm thầm dùng lại tuyến fallback đã cache.
- **Tình huống biên:** không kéo dài fallback vô thời hạn chỉ vì ORS đang lỗi; giá trị mặc định 60 phút là chính sách kỹ thuật MVP, **không bảo đảm độ chính xác ETA**. Việc cung cấp ETA hứa hẹn cho khách phải tính đến chất lượng nguồn ước lượng.
- **Nguồn triển khai:** `backend/app/providers/route_cache.py`, `backend/app/core/config.py`, `backend/tests/integration/test_dev2_route_cache.py`; `docs/06_API_Specification.md` Phụ lục A; [PR #67](https://github.com/qaztyhn/cfo-itconsultant/pull/67).
- **Tình trạng:** cơ chế TTL đã merge qua #67 vào `main`; cần tiếp tục kiểm tra các nơi hiển thị/tính ETA để bảo toàn nhãn `fallback`.

## DEC-NOTIFY-001 — Giới hạn email thử nghiệm và ngăn gửi trùng

- **Ngày chốt:** 2026-11-07. **Duyệt bởi:** chủ dự án sau review chuỗi [PR #68](https://github.com/qaztyhn/cfo-itconsultant/pull/68)–[PR #70](https://github.com/qaztyhn/cfo-itconsultant/pull/70), đặc biệt [PR #69](https://github.com/qaztyhn/cfo-itconsultant/pull/69).
- **Quyết định:** MVP **không được gửi email đến khách hàng thật** trước khi có cơ chế chống gửi trùng và đối soát. Gửi email thử nghiệm chỉ qua **Mailpit/localhost**, hoặc SMTP **staging được kiểm soát với người nhận là địa chỉ demo/synthetic**; không coi việc bật `shadow_mode = false` là đủ cấp quyền gửi thật.
- **Ràng buộc code bắt buộc:** không chỉ ghi trong tài liệu. Cần kiểm tra và chặn người nhận không thuộc tập email thử nghiệm được phép ở staging, hoặc khóa hoàn toàn SMTP bên ngoài cho đến khi có cơ chế an toàn. Phải có kiểm thử xác nhận email khách thật bị từ chối trước khi gọi transport.
- **Rủi ro hiện tại:** outbox theo cơ chế **at-least-once**: SMTP có thể chấp nhận email trước khi transaction DB lưu `sent` thành công. Nếu commit thất bại hoặc timeout, lần retry có thể gửi **trùng**; `FOR UPDATE SKIP LOCKED` chỉ chống worker cùng gửi đồng thời, không giải quyết trường hợp này.
- **Trước khi gửi thật:** cần thiết kế và review riêng việc claim trạng thái trước gửi, định danh/dedupe ổn định, đối soát kết quả nhà cung cấp, xử lý trạng thái không chắc chắn và regression test mô phỏng SMTP thành công nhưng DB commit thất bại. Không tự mặc định hệ thống bảo đảm exactly-once.
- **Tài liệu/code liên quan:** `backend/app/providers/email_smtp.py`, `backend/app/services/notification_delivery.py`, [PR #69](https://github.com/qaztyhn/cfo-itconsultant/pull/69), `docs/05_Database_Design.md` và `docs/06_API_Specification.md` nếu sau này thay đổi giao kèo notification.
- **Tình trạng:** quyết định nghiệp vụ **đã chốt**. Code #68–#70 đã lên `main` qua #74. Chặn người nhận staging: `SmtpEmailProvider` với host ngoài Mailpit/localhost chỉ chấp nhận đúng một địa chỉ thuộc `SMTP_ALLOWED_RECIPIENT_DOMAINS` (mặc định `test`, rỗng → từ chối khởi tạo); địa chỉ khác bị từ chối **trước khi mở kết nối SMTP**, dòng notification chuyển `suppressed` với `suppressed_reason = recipient_not_allowed`, ghi `NOTIFICATION_SUPPRESSED`, không tính là lần thử và không retry (PR `fix/notify-staging-recipient-guard`, chờ review). **Chống trùng/đối soát vẫn chưa có**; chưa cho phép gửi email khách thật. Không đưa miền email thật (ví dụ miền của khách) vào danh sách cho phép.


## DEC-SRC-001 — Source contract SRC-Q1–Q10

- **Ngày chốt:** 2026-11-08. **Duyệt bởi:** chủ dự án trong cuộc trò chuyện 2026-11-08 sau khi xem bảng SRC-Q1–Q10 tại [M1_SOURCE_CONTRACT.md](proposals/M1_SOURCE_CONTRACT.md); xác nhận “đc tôi đồng ý”.
- **Phạm vi:** contract **hệ thống nguồn giả lập/POS và adapter đọc vào CFO**. Không thay đổi nguyên tắc CFO chỉ đọc từ nguồn, không thay thế POS cũ. Quyết định này **không** phải xác nhận rằng code, API hay migration đã triển khai.
- **SRC-Q1 — Snapshot:** lưu trong đơn bản chụp `address, lat, lon`, tên/điện thoại/email liên hệ; `receiving_restrictions` và `special_requirements` nullable. Thay đổi hồ sơ khách/địa chỉ sau đó không tự ghi đè bản chụp đơn cũ.
- **SRC-Q2 — Ghi đơn:** `POST/PUT` nhận `customer_id, address_id`, liên hệ, ngày/khung giờ, mã sales/store, yêu cầu đặc biệt, dòng hàng; server tự snapshot địa chỉ/toạ độ từ địa chỉ được chọn, không tin toạ độ client; từ chối field lạ.
- **SRC-Q3 — Response:** `POST` trả `201`; `PUT/validate/submit/cancel` trả `200`, dùng cùng order representation. Tiền dạng string, số lượng numeric, thời điểm có timezone; schema chi tiết còn phải đặc tả.
- **SRC-Q4 — Validation errors:** `422 VALIDATION_ERROR`, `details.errors` có đường dẫn field và reason ổn định; tuyệt đối không phản chiếu dữ liệu cá nhân. Dev 2 và Dev 3 chốt danh sách reason/path trong contract.
- **SRC-Q5 — Lifecycle:** `DRAFT → VALIDATED → SUBMITTED_FOR_PLANNING`; chỉnh sửa đơn đã validate đưa về `DRAFT`; submit kiểm tra lại trong transaction/row lock; xử lý version/cancel/retry theo proposal, cần contract test. Chỉnh sửa/hủy sau khi đã đồng bộ và sau duyệt CFO phải xét tương tác với `ORDER_CHANGED_AFTER_APPROVAL`, không tự suy đoán.
- **SRC-Q6 — Pagination:** danh sách nguồn dùng `{items,page,page_size,total}`, `page=1`, `page_size=50`, max `500`, header `X-Total-Count`; endpoint snapshot `/stock` giữ `{as_of,items}`. Danh sách endpoint thuộc phạm vi phải được liệt kê đầy đủ trong `06`.
- **SRC-Q7 — Đồng bộ gia tăng:** điều kiện `updated_at >= updated_since`, thứ tự tăng ổn định theo timestamp rồi natural key: đơn dùng `id`, sản phẩm dùng `sku`, thực thể khóa ghép dùng toàn bộ key; adapter upsert/idempotent để không bỏ sót bản ghi trùng timestamp.
- **SRC-Q8 — Lịch nhận:** chọn hướng **bổ sung** cấu hình lịch làm việc theo source instance/market và giờ nhận theo địa chỉ; không tự đoán ngày nghỉ, ngày lễ hay 24/7. Lịch nhận phải được kiểm tra cùng với quy tắc ca nhân viên kho và tài xế đã duyệt tại DEC-SHIFTS-001 / DEC-DRIVER-001 khi lập kế hoạch. Lịch/giờ nhận ở nguồn và ca kho/tài xế trong CFO là các dữ liệu khác nhau.
- **SRC-Q9 — Stock batch:** mỗi snapshot tồn kho là một batch nhất quán với một `as_of`, bao gồm cả snapshot rỗng; không dùng timestamp từng dòng làm thay thế batch marker. Storage/seed/transaction và ý nghĩa snapshot rỗng cần đặc tả kỹ trước triển khai.
- **SRC-Q10 — Mô hình SKU (chỉnh sửa bởi `DEC-SRC-Q10-SKU-001`):** mỗi SKU có **một đơn vị tồn kho chuẩn, cố định** từ danh mục sản phẩm. Mỗi batch/warehouse/SKU chỉ được có một dòng tồn kho; không tạo thêm dòng tồn riêng chỉ để biểu diễn pallet/bao khác nhau của cùng SKU. Quy đổi đơn bán khác về đơn vị SKU, rồi dùng `units_to_base` đổi sang đơn vị cơ sở cho CFO. **Không xây `physical_stock_pool_id` và không tự suy đoán nhiều SKU có cùng tồn**; các SKU khác nhau ánh xạ một global product chỉ được cộng khi đã xác minh là các lượng tồn độc lập; chưa rõ thì fail closed. Quy tắc pool trong quyết định cũ bị thay thế riêng ở Q10.

**Chi tiết D1-A–D đã được chốt 08/11/2026 bằng `DEC-SRC-D1-001`** ([quy tắc chi tiết](decisions/DEC_SRC_D1_APPROVED_20261108.md)): DRAFT required/nullable, tiền và số lượng, date mode, validation 422/409, giá 0, special requirements text không đáng tin làm safety gate; sửa/hủy sau submit, tự gợi ý lịch mới khi CFO đã APPROVED nhưng chưa DISPATCHED (Dispatcher mới được duyệt); phân trang/sync; lịch nhận có dữ liệu rõ; published stock batch kể cả rỗng; Q10 đã **đổi sang SKU đơn vị cố định và khóa `(batch,warehouse,SKU)`**, không dùng physical stock pool theo `DEC-SRC-Q10-SKU-001`. Đây là **phê duyệt hợp đồng nghiệp vụ**, không tự chứng minh database/API/adapter đã được code; Dev 1/2/3 phải bổ sung DDL, OpenAPI, migration, tests và sửa transition hợp lệ qua review.

**Phụ thuộc triển khai:** Dev 2 soạn/sửa schema nguồn tại `05`, OpenAPI/source contract tại `06`, upgrade/seed bảo toàn dữ liệu, backend source, adapter, test giao kèo nhiều instance; Dev 1 review DTO/ingestion và normalize stock; Dev 3 review POS request/response và lỗi. PR triển khai phải cập nhật `05`/`06`/`CHANGELOG`, migration và kiểm thử cùng nhau theo `09`; không tự mở rộng scope của DEC-ROUTING-002 / ASM-005 (đơn SKU chưa confirmed vẫn ở luồng cũ, không tự chuyển về CFO).

## DEC-HOLD-001 — Hết hạn hold phải lập kế hoạch mới

- **Ngày chốt:** 2026-11-08. **Phê duyệt:** chủ dự án, trong cuộc trò chuyện khi review [PR #78](https://github.com/qaztyhn/cfo-itconsultant/pull/78).
- **Ý quyết định:** “Hết hold thì trả về trạng thái bình thường. Nếu muốn lặp lại thì lại kiểm tra lại một lần nữa, như một đơn khác.” Diễn giải để triển khai: *đơn nguồn/CFO vẫn là một `customer_order` duy nhất*, không sao chép order và không tạo fulfillment trùng; chỉ **lần chạy kế hoạch** mới (`planning_run` mới, candidate/hold mới) được coi như lập kế hoạch một đơn chưa giữ nguồn lực.
- **Khi hold hết hạn (không có approval):** `held → expired`, `proposed → expired`, tất cả nguồn lực quay về khả dụng. Nếu order vẫn `PLANNED` **do chính run hết hạn** và không có run/plan được duyệt hoặc giữ chỗ mới hơn, đưa order về trạng thái chờ lập kế hoạch `SUBMITTED` bằng chuyển trạng thái/audit hợp lệ; không ghi đè order đã chuyển sang run/plan khác.
- **Không duyệt hồi sinh:** Dispatcher lẫn Sales **đều không** thể gọi Approve trên plan/`planning_run` đã hết hạn, **kể cả nguồn lực vẫn còn**. Trả `409 HOLD_EXPIRED` và hướng dẫn chạy lại. Quy tắc cũ trong `04` §7 mục 3 (“Dispatcher có thể Approve plan hết hạn sau khi kiểm tra lại”) bị **thay thế** bởi DEC-HOLD-001.
- **Plan Again:** là hành động riêng do người dùng yêu cầu, tạo `planning_run` mới cho **cùng** `order_id`. Đọc lại dữ liệu nguồn/phiên bản/mapping/route, hàng, lịch chính thức của kho, công suất, xe/tài xế, ca và giờ nghỉ, tuân thủ 5 gate; tạo tối đa ba phương án với hold TTL mới chỉ khi đạt. Không tự nối dài, tái sử dụng hoặc “approve lại” plan expired; quyết định phân luồng `cfo/legacy` đã chốt vẫn bất biến theo DEC-ROUTING-002.
- **Tình huống biên:** timeout job chạy trễ cũng không biến hold quá hạn thành hợp lệ; retry Plan Again phải idempotent/concurrency-safe để không tạo nhiều run/hold do double click; job timeout không được đưa về `SUBMITTED` một order đã có plan/run mới hoặc đã phê duyệt. Không tự gửi CONFIRMED khi hold hết hạn/chạy lại.
- **Phạm vi áp dụng:** hold của **phương án chưa duyệt**; không tự giải phóng reservation đã `committed` của kế hoạch đã duyệt. Không thay thế cơ chế `replan_suggestion` dành riêng cho **đơn đã duyệt**.
- **Theo dõi triển khai:** `backend/app/services/reservation_service.py`, `backend/app/jobs/hold_expiry.py`, T14 `planning_service`, T16 `approval_service`, frontend trạng thái/Plan Again, `docs/04_Tech_Stack_and_Architecture.md` §7, `docs/05_Database_Design.md` §7, `docs/06_API_Specification.md` §6. Chưa có thay đổi code trong PR tài liệu này; yêu cầu test timeout→reset→new run→new hold, từ chối approve plan expired, và race với run/approval mới.

## DEC-DEV2-D2-001 — CSV fallback schema/retry

- **Ngày chốt:** 2026-11-08. **Phê duyệt:** chủ dự án xác nhận “d2 ... tôi đồng ý với bạn” sau khi nhận đề xuất D2. CSV là phương án dự phòng *read-only* từ POS/source sang CFO, không ghi lại POS và không trực tiếp tạo approval/plan.
- **Chốt:** UTF-8 (BOM được chấp nhận), CSV chuẩn có header/schema version, dấu phẩy phân cách, dấu chấm thập phân, ngày ISO 8601 có timezone khi là timestamp, tiền hai chữ số thập phân. Đơn và dòng hàng là các bảng CSV liên kết; file hash SHA-256 theo market/entity/schema, `ok` trùng hash bỏ qua, `failed` retry có run mới, `partial` IT xác nhận để retry, `running` không chạy trùng; upsert idempotent, reject lỗi rõ, không cộng trùng tồn kho. Migration/index phải hỗ trợ retry file partial. Contract và test chi tiết tại [tài liệu quyết định](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md).

## DEC-DEV2-D3-001 — GPS riêng chuyến và ca làm, xóa ngay khi kết thúc

- **Ngày chốt:** 2026-11-08. **Phê duyệt:** chủ dự án chọn “30ph”, “có” (offline), “đến khi hoàn thành đơn, chừng nào đi giao đơn tiếp theo mới cần bật gps”, “chỉ tài xế được phân công, trong thời gian làm việc, ngoài giờ thì không được”.
- **Chu kỳ:** thu điểm mỗi **30 phút** khi `market.gps_enabled`, trip `on_road`, tài xế thuộc chuyến và ca chính thức còn hiệu lực. Trước/sau chuyến, ngoài ca, nghỉ việc hoặc không có phân công => không thu, không hiển thị, không tự bật lại. GPS **không dùng để giám sát giờ làm/nghỉ của nhân viên**.
- **Offline:** Driver PWA có hàng đợi cục bộ chỉ cho điểm của chuyến/ca hợp lệ; khi kết nối lại server kiểm quyền và thời gian ghi, chỉ nhận nếu chuyến *vẫn* `on_road`. Trip hoàn thành hoặc ca kết thúc khi offline => xóa queue trên thiết bị khi có thể, mọi retry sau đó bị server từ chối; không tạo dữ liệu GPS sau ca.
- **Ai xem:** chỉ **Dispatcher được phân công trực tiếp** cho chuyến đang hoạt động, và chỉ **trong giờ làm chính thức của tài xế**; không còn quyền chỉ vì cùng market/role `dispatcher`. Nếu thiếu cơ chế gắn Dispatcher–trip thì Dev 1/2 phải đặc tả/migration/authorization trước khi mở API; **fail closed**, không mở rộng quyền toàn market. Driver chỉ gửi cho chuyến mình qua JWT, `driver_id` phải suy từ auth, không tin ID giả mạo do client gửi. Customer/CS/Sales/warehouse/admin/viewer tuyệt đối không được xem tọa độ.
- **Retention:** sửa quy tắc cũ `gps.retention_days=30` / xóa 30 ngày sau trip: **raw GPS phải dừng thu và được xóa khi chuyến giao liên quan kết thúc hoặc ca hợp lệ chấm dứt (tùy mốc đến trước)**; xử lý multi-stop khi chuyến thực sự kết thúc, không xóa vì một stop đã giao. Trên DB, thiết bị và cache không còn vị trí cho chuyến đó sau cleanup. Backup có vòng đời riêng và cần quy trình GDPR; không hứa xóa vật lý ngay khỏi immutable backup của bên cung cấp. Lịch sử lái/giờ làm `driver_duty_log` là loại dữ liệu khác, không xóa theo GPS.
- **Triển khai:** Dev 2 viết payload/response/location history theo trip+driver, kiểm assignment, max batch và rate/retention settings; Dev 1 review RBAC, trip terminal triggers, các trạng thái lệch ca/trip; Dev 3 đóng phiên theo UI và xoá IndexedDB queue khi kết thúc. Các chi tiết hạn mức API còn được review ở PR code; tham khảo [quy tắc kỹ thuật và test](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md). Theo [IMY về GPS nhân viên](https://www.imy.se/verksamhet/dataskydd/dataskydd-pa-olika-omraden/arbetsliv/kontroll-och-overvakning-av-anstallda/).

## DEC-DEV2-D4-001 — Notification bằng template, không free-text

- **Ngày chốt:** 2026-11-08. **Phê duyệt:** chủ dự án: “Chọn cơ chế template có biến thay thế, không cho phép free-text tùy ý. Các biến chỉ được lấy từ dữ liệu đã được cho phép”.
- **Chốt:** `CONFIRMED`, `DISPATCHED`, `DELIVERED`, `FAILED`, `DELAY` là mẫu do server render. Các placeholder chỉ từ mã đơn công khai, trạng thái/ETA/khung đã duyệt và câu mẫu hợp lệ; không dùng GPS, tọa độ, tên tài xế, tên người nhận, nội dung nhập tự do, ghi chú CS hay điểm số nội bộ. Dispatcher chỉ có thể chỉnh ETA đã validate và chọn lý do/câu template có sẵn; DELAY vẫn draft → Dispatcher Send/Discard. Cấm body/subject tự do ở API và UI, validate server-side; code cần cập nhật `03/06` và test chống injection. Giữ DEC-NOTIFY-001: không email khách thật.
- **Giới hạn:** quy tắc thử gửi lại 5/15 phút là đề xuất kỹ thuật riêng, **không tự gắn owner-approved** chỉ vì owner duyệt template; các giới hạn retry/max attempts/giờ yên lặng cũ vẫn có hiệu lực đến khi có contract review.

## DEC-GDPR-001 — D5 phải tuân thủ GDPR by design

- **Ngày chốt:** 2026-11-08. **Phê duyệt:** chủ dự án: “D5 tôi muốn tuân thủ gdpr”. Đây là **mục tiêu compliance** đã duyệt, không phải bằng chứng hệ thống đã đạt GDPR hay mọi mốc ngày đều là quy định luật.
- **Chốt:** lawful basis/purpose, minh bạch, minimization, ROPA/DSAR, DPIA/GPS theo điều kiện, quyền truy cập, lưu theo loại dữ liệu, legal holds, DPAs/chuyển dữ liệu ngoài EEA và đánh giá chủ thể xử lý. Khi dùng dữ liệu thật cần legal/privacy sign-off; staging synthetic-only đến khi đạt. PR #86 đã đề xuất cùng mã này nhưng chưa merge; phải đối chiếu để không ghi trùng. <https://www.imy.se/en/frequently-asked-questions/how-long-can-we-keep-personal-data/>.

## DEC-DEV2-D5-001 — D5 mốc retention cho MVP, GPS override

- **Ngày chốt:** 2026-11-08. **Phê duyệt:** chủ dự án “d2, d5 tôi đồng ý với bạn” với bảng thời hạn trong [PR #87](https://github.com/qaztyhn/cfo-itconsultant/pull/87), đồng thời điều chỉnh D3: **GPS không giữ 30 ngày sau chuyến**, xóa khi trip kết thúc/ca nghỉ.
- **Chốt sản phẩm (đã duyệt):** customer contact/CS content **90 ngày** sau case/đơn cuối cùng đóng; đơn điều phối không phải chứng từ kế toán **365 ngày** sau `DELIVERED/CANCELLED`; dữ liệu tài khoản/địa chỉ nhân viên không thuộc nghĩa vụ khác **90 ngày** sau nghỉ việc và không còn active/legal hold; lịch ca/attendance không thuộc trường hợp luật khác **24 tháng** sau ca; log kỹ thuật **30 ngày**, bảo mật **90 ngày**, staging backup tối đa **30 ngày**. GPS: **xóa ngay khi trip kết thúc/ca chính thức hết hiệu lực**. Hồ sơ tachograph thực sự áp dụng giữ **ít nhất 12 tháng**; hồ sơ giờ làm tài xế thuộc phạm vi giữ **ít nhất 24 tháng**; chứng từ kế toán Thụy Điển giữ đến **31/12 của năm thứ bảy sau năm dương lịch mà năm tài chính kết thúc**, không áp dụng 7 năm cho mọi bản ghi CFO. Audit/milestone bất biến: **24 tháng chỉ là mốc review**, không tự động xóa/sửa. DSAR thông thường **1 tháng**, thông báo breach thuộc diện phải báo **72 giờ**. Lưu theo mốc `anchor`, bản ghi chung và legal hold, có dry-run policy.
- **Giới hạn:** đây là con số **chính sách vận hành đã được owner chốt**, **không** có nghĩa mọi thời hạn tự động đạt GDPR. Với dữ liệu thật, kiểm lại luật Thụy Điển, mục đích/basis, nghĩa vụ thuế/lao động và quyền của chủ thể; mục đích chấm dứt sớm hơn phải xóa sớm hơn khi không còn căn cứ, nghĩa vụ dài hơn phải archive riêng hạn chế truy cập. Xem bảng chi tiết và test tại [approved decisions](decisions/DEV2_D2_D3_D4_D5_APPROVED_20261108.md). Không triển khai job xóa dữ liệu thật trước legal review.

**D6:** chủ dự án “D6 TÔI SẼ TỔ CHỨC RIÊNG SAU”, **deferred / không phê duyệt triển khai cloud**. **D8:** chỉ yêu cầu đề xuất lịch chạy hợp lý theo Thụy Điển, **chưa phê duyệt**; xem [D8 proposal](proposals/D8_SCHEDULER_SWEDEN_PROPOSAL_20261108.md).

## DEC-SRC-D1-001 — Chốt chi tiết D1-A–D Source Contract

- **Ngày phê duyệt:** 2026-11-08. **Chủ dự án** trả lời nguyên văn “ĐƯỢC ĐỒNG Ý” đối với đề xuất tổng hợp D1-A, D1-B, D1-C và D1-D từ [PR #84](https://github.com/qaztyhn/cfo-itconsultant/pull/84). Quyết định này **hoàn thiện các chi tiết còn mở của DEC-SRC-001**, không đổi tính chất CFO chỉ đọc hệ thống nguồn và không duyệt các nhóm D6/D8.
- **D1-A — danh sách:** GET `/orders`, `/customers`, `/products`, `/inbound`, `/fleet/calendar`, `/addresses` trả `{items,page,page_size,total}` và header `X-Total-Count`, page=1/page_size=50/max500, sort `(updated_at, natural_key)`, `updated_since >=`. GET `/orders` mặc định trạng thái `SUBMITTED_FOR_PLANNING`, phải cho truy vấn `CANCELLED` để adapter nhận hủy. `/stock` là batch `{as_of,items}`, **không phân trang**. Checkpoint per-feed bền vững, bảo đảm retry/idempotency và không bỏ qua timestamp bằng nhau.
- **D1-B — ghi/validate:** POST tạo `DRAFT` version 1; persisted DRAFT cần `customer_id,address_id,store_code,date_mode`. Validate yêu cầu liên hệ (tên và ít nhất phone/email), địa chỉ thuộc khách có tọa độ, SKU tồn tại ở POS, line_no không trùng, qty dương ≤3 số thập phân và `unit_price` chuỗi decimal **không âm**, đúng 2 số thập phân (**giá 0 hợp lệ**). Date mode `exact/range/latest` với `date_from/date_to` tương ứng, giờ nhận `HH:MM` hợp lệ, không mặc định 24/7. Không tin địa chỉ/tọa độ client, snapshot từ server và chỉ refresh khi người dùng đổi. `special_requirements`/ `receiving_restrictions` text tùy chọn **không** tự chứng minh an toàn/thiết bị xe; cần Dispatcher nếu chưa thể hiện bằng trường có cấu trúc. Trả `422 VALIDATION_ERROR` `details.errors[{loc,type,msg}]`, không phản chiếu PII; SKU nguồn có nhưng CFO chưa mapping **không phải lỗi POS**, xử lý theo ASM-005/DEC-ROUTING-002. GET/POST/PUT/validate/submit/cancel dùng chung order DTO, POST 201, các write khác 200.
- **D1-C — lifecycle:** DRAFT→VALIDATED→SUBMITTED_FOR_PLANNING, chỉnh VALIDATED quay DRAFT; PUT full replacement sau submit **được phép nhưng phải validate lại toàn đơn**, tăng `source_version`, so khớp `expected_version` bằng transaction/row lock, sai → `409 VERSION_CONFLICT` (mã source mới). Cancel từ DRAFT/VALIDATED/SUBMITTED với version và reason, trạng thái terminal `CANCELLED`, idempotent retry, không tái submit; adapter poll `CANCELLED` và xử lý trạng thái qua chuyển hợp lệ/audit. **Trước khi CFO duyệt:** đóng/release hold an toàn theo state machine. **Sau khi CFO đã duyệt, trước DISPATCHED:** tạo `ORDER_CHANGED_AFTER_APPROVAL`, **tự chạy `replan_suggestion` và kiểm lại toàn bộ 5 gate**, không tự hold/approve hay bỏ plan đã cam kết; Dispatcher duyệt đổi phương án trong transaction hoặc giữ kế hoạch cũ kèm lý do. **Sau DISPATCHED:** chỉ alert và Dispatcher can thiệp; không tự hủy/thay chuyến đang chạy, không xóa fulfillment history. Đơn source `CANCELLED` sau CFO đã duyệt không tự tạo giao hàng mới; Dispatcher xem xét việc hủy. CFO không ghi ngược POS.
- **D1-D — Q8/9/10:** lịch ngày làm việc/ngày lễ theo market instance và khung giờ nhận từng địa chỉ được seed/cấu hình rõ; thiếu calendar thì fail closed. Stock snapshot phải publish đầy đủ **cùng một batch `as_of`**, kể cả zero-row có completeness marker; chưa có batch không có nghĩa tồn=0. Tồn kho **Q10 cập nhật theo `DEC-SRC-Q10-SKU-001`**: mỗi SKU có một đơn vị chuẩn; một bản ghi duy nhất cho `(batch_id, warehouse_code, sku)`; quy đổi đơn vị khi bán và dùng `units_to_base` khi đưa về CFO, không tạo pool hay tự gom SKU theo số lượng bằng nhau. Mẫu dữ liệu đa-SKU cùng global product chưa chứng minh độc lập phải fail closed; không last-row-wins/cộng mù. Dev 1 + Dev 2 phải review migration/adapter và regression tests.
- **Phân công & trạng thái:** chi tiết đầy đủ trong [DEC_SRC_D1_APPROVED_20261108.md](decisions/DEC_SRC_D1_APPROVED_20261108.md). **Đã duyệt quyết định, chưa hoàn thành code.** Dev 2 triển khai nguồn/adapter, Dev 1 review & xử lý replan/stock/state machine, Dev 3 POS. D6 vẫn owner tổ chức riêng; D8 chỉ đang được đề xuất.

## DEC-SRC-Q9-ERROR-001 — Duyệt 503 STOCK_UNAVAILABLE của Source API

- **Ngày phê duyệt:** 2026-11-08. **Chủ dự án** phản hồi “ĐƯỢC. CẬP NHẬT 101 PR ĐI” sau khi được đề xuất **phương án A**: khi Source/WMS **không có batch tồn kho được publish hoàn chỉnh** thì `GET /api/v1/stock` trả **HTTP 503**, `error.code = "STOCK_UNAVAILABLE"`, không trả `items=[]` và không suy thành tồn kho bằng 0.
- **Phạm vi:** mã lỗi **chỉ dành cho Source API**. Dùng phong bì lỗi chuẩn `{ "error": { "code": "STOCK_UNAVAILABLE", "message": "Stock snapshot is unavailable.", "details": {}, "correlation_id": "<opaque>" } }`, trả header `X-Correlation-ID` và vẫn yêu cầu xác thực Source API. Không rò rỉ thông tin nội bộ hoặc PII.
- **Trường hợp:** chưa từng có published batch hoặc chỉ có batch `loading`/`failed` → **503**; batch hoàn chỉnh được publish có `items=[]` → **200** và là tồn bằng 0 trong phạm vi snapshot. Nếu bản publish cũ vẫn có nhưng batch mới lỗi, chỉ cho đọc **bản đã publish mới nhất** với `as_of` thực; CFO tự đánh giá freshness, không tự đổi thành dữ liệu mới.
- **Tác động CFO:** giữ snapshot cũ chỉ để tham chiếu khi đồng bộ thất bại; báo lỗi đồng bộ/alert và áp dụng fail-closed ở planning nếu tồn kho cũ/không khả dụng. Không thay tồn kho bằng 0, không giả mạo `as_of`. Chu kỳ polling 5 phút và ngưỡng stale 15 phút **không đổi** theo cấu hình đã có.
- **Trạng thái:** **đã duyệt mã lỗi và HTTP status**; PR #101 chỉ cập nhật **tài liệu**. Dev 2 cần triển khai handler/schema/OpenAPI + tests ở Source; Dev 1 cần xử lý HTTP 503 ở adapter, stale/availability gate và regression tests. Các chi tiết tên bảng/migration/field `batch_id`-`item_count` vẫn qua review kỹ thuật, không vì mã lỗi đã duyệt mà coi Q9 code hoàn thành. Quyết định Q10 fixed-unit SKU `DEC-SRC-Q10-SKU-001` giữ nguyên.

## DEC-SRC-Q10-SKU-001 — Mỗi SKU một đơn vị tồn kho chuẩn, không Physical Stock Pool

- **Ngày chốt:** 2026-11-08. **Chủ dự án** khẳng định “1 mã sản phẩm phải lưu đơn vị giống nhau” và yêu cầu **thay đổi PR #101 theo yêu cầu đó**. Đây là quyết định nghiệp vụ **thay thế riêng** giả định alias/shared physical stock pool của SRC-Q10 trong `DEC-SRC-D1-001`; **không đảo ngược Q9** về published full batch, không sửa Q1–Q8.
- **Đơn vị SKU:** một SKU có duy nhất **đơn vị tồn kho được khai báo ổn định** trong danh mục Source (`sale_unit` / stock unit). `on_hand` và `reserved` của SKU ở mọi kho và batch dùng đúng đơn vị đó; thay đơn vị phải có SKU mới hoặc chuyển đổi dữ liệu được kiểm soát, không ngầm diễn giải lại tồn/hợp đồng lịch sử.
- **Khóa hàng tồn:** đúng một dòng trên **`(batch_id, warehouse_code, sku)`**; bản ghi trùng trong batch là **lỗi batch**, không cộng, ghi đè hoặc suy ra pool. Trong từng kho, cùng SKU có một số lượng tồn được xác nhận cho thời điểm batch; giữa các kho là lượng tồn khác nhau.
- **Đơn bán khác quy cách:** ví dụ tồn `CEM-25` tính bằng **bao**, 5 pallet × 20 bao chỉ là **100 bao** của `CEM-25`, không thêm dòng 5 pallet tồn kho. Chuẩn hóa số lượng đơn hàng về đơn vị SKU, rồi `units_to_base` khi CFO cần đổi sang đơn vị cơ sở.
- **Không dùng pool:** **bỏ `physical_stock_pool_id`**, không tạo nhóm alias cùng tồn, không dùng phép quy đổi số lượng để suy luận hai mã SKU đang chỉ vào cùng hàng. Khi nhiều SKU khác nhau mapping một `global_product_id`, chỉ cộng nếu đã có xác nhận đáng tin cậy rằng tồn vật lý **độc lập**; nếu chưa rõ thì chặn/quarantine lượng tồn liên quan và không công bố snapshot CFO thiếu một phần như hoàn chỉnh.
- **Q9 giữ nguyên:** published batch atomic, complete empty batch nghĩa 0 trong phạm vi batch, chưa có published batch nghĩa unknown/unavailable; dữ liệu lỗi phải fail closed, không lấy `min(as_of)` của từng dòng. `503 STOCK_UNAVAILABLE` **đã được owner duyệt riêng bằng `DEC-SRC-Q9-ERROR-001`**; chỉ áp dụng Source API khi **không có published complete batch**, không có nghĩa tồn=0. Các chi tiết DTO/migration ở [PR #101](https://github.com/qaztyhn/cfo-itconsultant/pull/101) vẫn cần Dev 1/2 review và triển khai.
- **Phân công:** Dev 2 xem lại Source `src_stock` PK/UNIQUE, sản phẩm đơn vị chuẩn, migration/batch/seed; Dev 1 xem lại Source→CFO SKU mapping, conversion, stale stock và không công bố dữ liệu một phần; cả hai cần thống nhất `05`/`06` + OpenAPI/tests trước code; không xây pool theo đề xuất cũ. PR #101 **docs-only**, không có nghĩa đã triển khai.
- **Quyết định chốt tiếp 08/11:** DEC-CFO-STOCK-SCOPE-001 xác định phạm vi SKU CFO trước khi xử lý batch; DEC-CFO-STOCK-INDEPENDENCE-001 chỉ cho phép cộng SKU cùng global product sau khi đã xác minh độc lập. Hai quyết định bổ sung phía CFO, không thay Q9/Q10 của Source.

## DEC-CFO-STOCK-SCOPE-001 — Phạm vi SKU đồng bộ tồn kho CFO được chốt trước

- **Ngày và người phê duyệt:** 2026-11-08, chủ dự án. **Chốt nguyên văn:** “SKU chưa mapping: phương án B. Chỉ đồng bộ phạm vi SKU CFO đã xác định trước; SKU chưa mapping trong phạm vi này làm batch không hợp lệ”.
- **Phạm vi áp dụng:** phạm vi SKU của CFO/pilot phải được xác định rõ **trước** kỳ/lần đồng bộ. CFO chỉ chuẩn hóa và ghi tồn kho SKU thuộc phạm vi được duyệt. SKU nằm **ngoài** phạm vi không bị xử lý như SKU lỗi mapping của CFO và không làm hỏng cập nhật tồn kho CFO chỉ vì chưa mapping. Không được tự định nghĩa phạm vi bằng cách loại các SKU mapping lỗi trong chính batch đang xử lý.
- **Điều kiện fail closed:** chỉ cần **một SKU trong phạm vi** chưa mapping confirmed, mapping không nhất quán hoặc thiếu dữ liệu bắt buộc, phải từ chối **toàn bộ lần ghi snapshot tồn kho CFO thuộc phạm vi/batch đó**, không âm thầm bỏ dòng lỗi, không công bố snapshot thiếu hàng như hoàn chỉnh. Giữ lịch sử để audit; dữ liệu stale/unknown không dùng để cam kết giao.
- **Ranh giới Source:** Source vẫn phải xuất bản toàn bộ batch hoàn chỉnh theo Q9/Q10 và đáp ứng các quy tắc published-empty/503 đã duyệt; phạm vi CFO là quy tắc **tiêu thụ phía CFO**, không phải quyền bỏ dòng trong batch Source, không sửa Source API hay HTTP 503 STOCK_UNAVAILABLE. Snapshot CFO rỗng trong phạm vi pilot không chứng minh toàn bộ Source không còn hàng.
- **Phân luồng đơn giữ nguyên:** ASM-005 và DEC-ROUTING-002 tiếp tục áp dụng: đơn chỉ vào CFO khi tất cả SKU trong đơn đã mapping confirmed và Sales/Dispatcher ghi quyết định routing; SKU mới mapping về sau không tự đưa đơn legacy trở lại CFO.
- **Bổ sung đã duyệt DEC-DEV1-D1-03:** quản trị viên có thẩm quyền quản lý/phê duyệt scope theo market/pilot với version, hiệu lực và audit; không được suy scope từ mapping. **Chưa chốt kỹ thuật**: bảng/field/API, ủy quyền chi tiết, binding batch_id/as_of, tính đầy đủ, migration và tests; Dev 1/2 phải review trước code.
- **Trạng thái:** owner-approved policy, **chưa triển khai/kiểm thử E2E**. T07 và Dev 1/2 phải cập nhật 05/06/09, chuẩn hóa/ghi tồn kho CFO và kiểm thử: SKU ngoài phạm vi không chặn; SKU trong phạm vi chưa mapping chặn trọn lần ghi; tuyệt đối không có partial write.

## DEC-CFO-STOCK-INDEPENDENCE-001 — Chỉ cộng nhiều SKU cùng global product khi tồn kho độc lập đã xác minh

- **Ngày và người phê duyệt:** 2026-11-08, chủ dự án. **Chốt nguyên văn:** “Nhiều SKU cùng global product: phương án A. Chỉ được cộng khi xác minh tồn kho độc lập; chưa xác minh thì từ chối”.
- **Quy tắc:** khi nhiều SKU nguồn **cùng kho** mapping vào cùng một global_product_id, chỉ được cộng on_hand và reserved sau khi **xác minh đáng tin cậy rằng số lượng từng SKU là tồn vật lý độc lập, không chồng lấn/đếm trùng**. Mapping từng SKU phải confirmed và lượng tồn phải được quy đổi **một lần** sang đơn vị cơ sở theo đơn vị tồn chuẩn cố định SKU (DEC-SRC-Q10-SKU-001). Không suy ra độc lập từ SKU khác mã, cùng sản phẩm hay tỷ lệ quy đổi.
- **Khi thiếu/không chắc bằng chứng:** fail closed cho lần chuẩn hóa và ghi snapshot CFO liên quan; không cộng, không lấy giá trị max, không last-row-wins, không coi dữ liệu thiếu là tồn 0 và không publish snapshot partial như hoàn chỉnh. Nếu xác minh có chồng lấn thì **không cộng** và phải làm rõ mapping/nguồn trước khi sử dụng; không quay lại physical_stock_pool_id.
- **Ranh giới:** batch Source theo SKU vẫn có thể hợp lệ; lỗi chỉ phát sinh tại gate mapping/aggregation của CFO. Không thay quyết định Q9 về published batch và HTTP 503; không cộng tồn giữa các kho.
- **Bổ sung đã duyệt DEC-DEV1-D1-04:** Warehouse Manager cung cấp chứng cứ từ kho/WMS; quản trị viên có thẩm quyền phê duyệt; lưu evidence, approver, version, hiệu lực, audit; thiếu xác minh thì fail closed. **Chưa chốt kỹ thuật**: tiêu chí/provenance, bảng/field/API, thu hồi khi mapping/Source thay đổi và transaction tests; Dev 1/2 phải review.
- **Trạng thái:** owner-approved policy, **chưa triển khai/kiểm thử E2E**. Hàm chuẩn hóa hiện tại đang từ chối tất cả trường hợp nhiều SKU cùng kho cùng global product; cần cho phép **chỉ** trường hợp đã xác minh độc lập, có test dữ liệu độc lập được cộng sau quy đổi và mọi ca chưa xác minh/chồng lấn đều không ghi một phần.

## DEC-DEV1-D1-01 — TRANSFER_CANCELLED khi hủy chuyển kho

- **Phê duyệt:** 2026-11-08, chủ dự án “ĐỒNG Ý — Có. Ghi người thực hiện, lý do, thời điểm, trạng thái trước/sau. Không dùng TRANSFER_APPROVED cho hành động hủy.”
- **Ràng buộc:** `POST /transfers/{id}/cancel` ghi `TRANSFER_CANCELLED` trong `audit.decision_log` cùng transaction với chuyển trạng thái, actor, reason bắt buộc, ts, before/after; không được dùng `TRANSFER_APPROVED`. Ngoài trạng thái hợp lệ/không có contract hoàn nguyên WMS thì fail-closed.
- **Nguồn:** [biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md) và [PR #127](https://github.com/qaztyhn/cfo-itconsultant/pull/127). Docs approved; code/migration/tests còn chờ.

## DEC-DEV1-D1-02 — TRANSFER_RECEIVED cho kho đích

- **Phê duyệt:** 2026-11-08, chủ dự án “ĐỒNG Ý — Tạo TRANSFER_RECEIVED riêng. CONFIRMED dành cho kho nguồn xác nhận xuất; RECEIVED dành cho kho đích nhận.”
- **Ràng buộc:** kho nguồn `confirm-source` ghi `TRANSFER_CONFIRMED`; kho đích `receive` ghi `TRANSFER_RECEIVED` với actor, ts, before/after, trong cùng transaction với receipt. Không tái dùng `TRANSFER_CONFIRMED`/snapshot stage để biểu diễn nhận hàng. Scope kho và idempotency bắt buộc.
- **Nguồn:** [biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md) và [PR #127](https://github.com/qaztyhn/cfo-itconsultant/pull/127). Code/tests chưa hoàn tất.

## DEC-DEV1-D1-03 — Scope SKU có admin thẩm quyền, version và audit

- **Phê duyệt:** 2026-11-08, chủ dự án “ĐỒNG Ý — Quản trị viên có thẩm quyền quản lý phạm vi theo market/pilot, có version, ngày hiệu lực và audit. Không tự suy phạm vi từ mapping.”
- **Ràng buộc:** quản trị viên có thẩm quyền theo market/pilot được quản lý/phê duyệt scope CFO trước lần sync; lưu version, effective time, actor/approver, before/after audit và lịch sử; không suy từ mappings/Source batch. SKU ngoài scope không chặn, trong scope mapping sai thì chặn toàn batch. Giữ DEC-CFO-STOCK-SCOPE-001.
- **Chờ kỹ thuật:** nơi lưu/field/endpoint/chi tiết quyền và binding effective version với batch chưa chốt; Dev 1/2 review. [Biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md); [PR #121](https://github.com/qaztyhn/cfo-itconsultant/pull/121).

## DEC-DEV1-D1-04 — Bằng chứng tồn độc lập do Warehouse Manager cung cấp và admin duyệt

- **Phê duyệt:** 2026-11-08, chủ dự án “ĐỒNG Ý — Warehouse Manager cung cấp bằng chứng từ kho/WMS; quản trị viên có thẩm quyền phê duyệt. Lưu bằng chứng, người duyệt, phiên bản và hiệu lực; thiếu xác minh thì chặn.”
- **Ràng buộc:** chứng cứ warehouse/SKU/global-product từ kho/WMS do Warehouse Manager cung cấp, admin có thẩm quyền phê duyệt; lưu evidence/provenance, approver, version, hiệu lực và audit trước/sau. Thiếu/hết hiệu lực/chồng lấn => fail closed, không cộng/ghi snapshot CFO một phần; giữ DEC-CFO-STOCK-INDEPENDENCE-001.
- **Chờ kỹ thuật:** schema/route, tiêu chí thu hồi khi mapping/stock thay đổi và E2E; Dev 1/2 review. [Biên bản](decisions/DEV1_D1_01_04_APPROVED_20261108.md); [PR #120](https://github.com/qaztyhn/cfo-itconsultant/pull/120).

## ASM-008 — Giả định giao diện M0 (Dev 3; đề xuất chưa duyệt)

- **Ngày đề xuất:** 2026-11-07; **trạng thái:** đề xuất kỹ thuật UX của Dev 3, **không phải quyết định owner đã duyệt**. Mọi quyền ở frontend chỉ hỗ trợ hiển thị; backend vẫn là nơi kiểm tra RBAC.
- **ASM-B/C:** người dùng nhiều vai trò được gộp menu; thứ tự màn hình đầu tiên admin → dispatcher → warehouse → driver → customer_service → sales → revenue_all → ops. Sales bắt đầu tại `/store/orders`. Cần nghiệm thu thực tế theo quyền nhiều vai trò trước khi xem là quy tắc sản phẩm chính thức.
- **ASM-D/E:** KPI vận hành theo admin hoặc `ops`, Revenue toàn thị trường theo admin hoặc `revenue_all`. Revenue tại địa điểm owner cần tín hiệu `owned_location_ids` (vị trí có `location.owner_employee_id = user.employee_id`); frontend hỗ trợ trường này dạng **optional** và chỉ hiện khi backend thực sự trả. Dev 1 chưa xuất trường trong `UserOut` / `GET /auth/me`; không tự suy owner từ `roles` hoặc `location_ids`.
- **ASM-F:** badge Plan review lấy `awaiting_approval` từ `GET /orders/counts`, không hiển thị số 0 giả khi chưa có dữ liệu.
- **ASM-G:** New order của Sales mở POS riêng qua `VITE_POS_URL`, giá trị local ví dụ `http://localhost:8100`; cổng/URL triển khai phải do Dev 2 xác nhận, không hard-code vào production.
- **ASM-H:** Customer Service Contact log hiện là placeholder, không được báo là đã hoàn thành nghiệp vụ.
- **ASM-I:** trạng thái chip dùng token thiết kế mặc định; đơn legacy `BLOCKED_UNMAPPED_SKU` phải nằm ngoài các endpoint CFO orders/counts/detail theo DEC-ROUTING-002.
- **Auth/Locations đã có code:** `GET /auth/me` trả cùng `UserOut` như login; `GET /locations` trả `{items:[{id,code,name,type}]}` có phân trang; frontend đọc các trang và filter scope. Kiểm E2E với backend thật vẫn cần bằng chứng.
- **Môi trường:** `VITE_APP_ENV` không đặt → mặc định **production-safe**, không hiện thẻ demo; chỉ bật demo bằng cấu hình môi trường có chủ đích. Mô tả cũ “không đặt → demo” đã được sửa trong frontend và phải coi là superseded.
- **Demo accounts:** UI hiện 7 thẻ không bao gồm Project Lead như `03` mục 5.0. M0 seed chỉ có 5 account; `wm.got`, `driver1`, `cs` cần đúng seed M1 mới đăng nhập thật. Chỉ điền email, không hard-code mật khẩu.
- **Q11:** tiếp tục tuân theo ASM-007/DEC-SHIFTS-001; không cấp ca chỉ dựa vào `expected_staff`.
- **Phạm vi:** `frontend/src/app`, `frontend/src/api`, `Sidebar`, `ScopePicker`, `DemoBanner`, `SignIn`; Dev 1 cần chuẩn hóa `owned_location_ids`, Dev 2 cần xác nhận POS URL/seed, Dev 3 cần smoke test backend thật. Mục này chỉ ghi nhận hiện trạng và phụ thuộc kỹ thuật, **chưa chốt owner assumptions mới**.

## DEC-OWNER-20261109 — 27 quyết định liên workstream đã duyệt ngày 09/11/2026

- **Người phê duyệt/ngày:** Chủ dự án ITConsultant, 2026-11-09, xác nhận toàn bộ 27 mã S/T18/D7/G/N/M6/API/KPI trong cuộc trò chuyện. **Bản ghi chi tiết và biên giới triển khai:** [OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md](decisions/OWNER_CROSS_WORKSTREAM_APPROVED_20261109.md).
- **S1–S5 (stock):** S1 — Admin phải có grant rõ và đang hiệu lực theo market. S2 — người tạo scope khác người duyệt; Warehouse Manager nộp evidence WMS và admin có quyền, khác người nộp, phê duyệt. S3 — scope market-wide trong pilot SE, version có hiệu lực sau duyệt, batch dùng version theo `as_of`, có binding lưu lại. S4 — mỗi warehouse × in-scope SKU phải có dòng thật trong batch đầy đủ, thiếu ⇒ unknown và từ chối cả CFO stock write (0 phải được gửi tường minh). S5 — evidence độc lập tối đa **30 ngày pilot**, gia hạn bằng version được duyệt mới; mapping/unit/conversion/scope đổi ⇒ tự thu hồi, WMS anomaly cần review.
- **T18-1–3:** T18-1 — không cộng thêm inbound vào stock available khi chưa có chứng cứ nội dung WMS đã phản ánh đúng lượng chuyển; chỉ `snapshot.as_of` là chưa đủ, Warehouse Manager xác nhận nhận hàng theo nghiệp vụ. T18-2 — lead-time default theo market chỉ dùng khi được cấu hình/phê duyệt và lưu provenance, thiếu thì fail closed. T18-3 — không cho hủy/reversal sau `source_confirmed` trước khi có contract riêng.
- **D7-1–4:** D7-1 — dữ liệu HR/tachograph thực phải do người đủ thẩm quyền vận tải/compliance kiểm chứng; synthetic chỉ demo. D7-2 — bằng chứng cho **56 ngày lịch**, ngày nghỉ có chứng cứ khác ngày unknown, kiểm lại khi lập kế hoạch/duyệt/dispatch. D7-3 — nghỉ liên tục mặc định **11h**, tách duty/driving/rest và ca chính thức. D7-4 — thiếu bằng lái, permissible mass, phạm vi Regulation 561/bối cảnh xe/rơ-moóc ⇒ không cho tự duyệt/giao, không suy từ nhãn xe.
- **G1–G5:** G1 — admin/supervisor có quyền theo market phân **một Dispatcher chính/trip**, bàn giao có audit. G2 — chỉ đúng Dispatcher được giao xem GPS khi assignment+trip+ca còn hợp lệ. G3 — thông báo/ack từng tài xế theo notice version và phải có privacy/legal/DPIA sign-off để dùng dữ liệu thật. G4 — device mỗi **30 phút**, upload **≤100 điểm/batch** trong ca/chuyến, xóa GPS sau trip hoặc hết ca (đến trước), không giữ 30 ngày. G5 — simulator có danh tính producer và synthetic provenance riêng.
- **N1–N5:** N1 — Dispatcher có quyền duyệt DELAY window, đổi ngày phải có thỏa thuận khách hợp lệ. N2 — start/end/version/approver/effective time rõ, không suy từ ETA instant. N3 — pin template version + typed allowlist variables, không free-text. N4 — event/risk/queued notification/outbox cùng caller DB transaction; gửi bên ngoài sau commit. N5 — giữ retry cap hiện có, chỉ Mailpit/test recipients.
- **M6-1:** Thành công POD unique **theo `trip_stop`** chứ không toàn `order`; phải migration bỏ unique index theo order đang có.
- **API-1/2:** Gate dùng `checks.*.passed` (không phải `pass`); rejected candidates flat `warehouse_id, vehicle_code, failed_check, code, detail`. UI đã merge #136 sửa trong **PR mới**.
- **KPI-1/2:** **10 KPI keys** đã xuất hiện trong JSON; 2 diagnostics chưa có công thức/nguồn tin cậy trả `null`, không giả 0; cohort theo ngày approved/giao/work_date theo market timezone.
- **Tình trạng:** **Đã phê duyệt nghiệp vụ**, còn phải update schema/API/engine/frontend, migration, PostgreSQL E2E, pháp lý/GDPR và PR review. Không mặc nhiên cho phép live GPS hay bỏ fail-closed, **không auto-merge PR code**.

