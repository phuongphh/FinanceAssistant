# Đưa thay đổi lên Dev theo đợt và đề xuất phát hành

Issue là một công việc để coding agent thực hiện. **Đợt Dev** là tập thay đổi
được triển khai và nghiệm thu cùng nhau. **Đợt phát hành** mang một tính năng,
phase hoặc bản sửa lỗi đã nghiệm thu đến người dùng Production.

## Bạn chỉ cần nói với Bé PM

| Khi nào | Câu bạn có thể gửi | PM làm gì |
| --- | --- | --- |
| Đã merge, muốn thử ngay | “Đưa PR #N lên Dev” | Kiểm tra phạm vi, chốt bản, giao Ốp Dev. Nếu cần kéo theo tính năng khác, PM hỏi rõ trước. |
| Chưa muốn cập nhật Dev | “Để sau #N” | Giữ trong danh sách chờ; không bỏ mất công việc, không nhắc lại liên tục. |
| Muốn thử nhiều phần một lần | “Gom các thay đổi đã xong lên Dev” | Liệt kê phần đang chờ, gồm cả phần để sau, chốt thành một đợt rồi xin bạn duyệt một lần. |
| Đồng ý với đợt PM vừa trình | “Duyệt Dev đợt này” | Ghi nhận đúng phiên bản, kiểm thử bản gộp, giao Ốp Dev triển khai. |
| Chưa muốn triển khai đợt vừa trình | “Để sau đợt này” | Hủy đề xuất đang chờ, trả các phần chưa triển khai về danh sách để sau. |
| Đã thử trên bot Dev | “Nghiệm thu đạt đợt này” hoặc nêu lỗi | Lưu kết quả gắn với đúng bản đang chạy. Không tự suy từ việc issue đã đóng. |

Bạn không cần chạy lệnh, đọc log hay nhắn Sen để pull code. Bạn vẫn quyết định
merge PR coding, duyệt đợt Dev và nghiệm thu. “Gom các thay đổi” là yêu cầu chuẩn
bị danh sách, chưa phải đồng ý triển khai mọi nội dung chưa thấy.

PM báo ngắn: **có gì mới, đang chờ gì, bạn cần làm gì**. Chỉ mời thử trên bot Dev
sau khi Ốp Dev xác nhận đúng bản, dịch vụ và kết nối Telegram. Không yêu cầu bạn
thử Production để nghiệm thu bản chưa phát hành.

## Khi nào PM đề xuất Production?

Sau khi nghiệm thu một đợt có giá trị sử dụng. Với phase đã khai báo nhiều phần,
phải nghiệm thu đủ các phần trước; một hotfix có thể phát hành riêng. Bạn cũng
có thể yêu cầu gom nhiều phần đã nghiệm thu vào một lần phát hành.

Monitor chủ động gửi đề xuất chuẩn bị phát hành. Đây chưa phải thông báo “sẵn
sàng lên Production”: PM còn phải đối chiếu bản Production thật, toàn bộ thay
đổi sẽ đi kèm, migration/dữ liệu/quyền truy cập, backup/khôi phục và người vận
hành. Sau khi có đủ bằng chứng, PM trình PR phát hành vào `prod`. Bạn duyệt
Production bằng việc merge PR phát hành theo quy trình hiện hành; không thêm
một vòng phê duyệt Telegram trùng lặp. Merge PR coding vào `main` không thay thế
bước này. Nội dung mới sau lần chốt cần được chốt và nghiệm thu lại.

FinanceAssistant/TaxAssistant/CorporateSAgent: Dev do Ốp Dev trên Mac Mini;
Production do Ốp Pro/pipeline trên VPS. Sản phẩm cá nhân: Ốp Dev phụ trách cả
Dev và Production trên Mac, nhưng vẫn tách phê duyệt và hồ sơ từng môi trường.
Controller hiện được cài thí điểm cho FinanceAssistant; không mặc định các repo
khác đã có cùng cơ chế tự động.

## Cơ chế dành cho PM và Ốp Dev

Đây là phần nội bộ. Không yêu cầu PO gọi các lệnh sau.

`delivery.pm_monitor` dùng cùng một state/lock với `delivery.batches`. Profile
`batch_delivery: true` thay lối duyệt Dev từng PR cũ; quyết định lịch sử được giữ
nguyên. `delivery_v2` lưu queue, batch, phiên bản Dev và đề xuất release. File
state riêng tư, ghi atomic, không phải schema release/deployment v1 đã duyệt
Production. Chỉ phiên PM/DevOps tin cậy được ghi lệnh; issue/comment/log không
phải nguồn phê duyệt. Reference là liên kết kiểm toán, không tự xác thực người dùng.

Wrapper cài trên Mac: `runtime/pm-delivery-monitor/bin/pm-delivery`. Đọc trạng thái
hoặc đưa một lệnh JSON qua `--batch-command /private/path/command.json`:

```json
{"action":"status","repository":"phuongphh/FinanceAssistant"}
```

Lệnh chuẩn bị, không phê duyệt:

```json
{"action":"propose","repository":"phuongphh/FinanceAssistant","all":true,"title":"Tên đợt nghiệm thu"}
```

Thay `all` bằng `prs:[N,M]` để chọn riêng. Controller kiểm PR thực sự merged
vào main của đúng repo, chọn merge SHA mới nhất trong các PR đã chọn, kiểm
first-parent history từ Dev baseline đến candidate. Một app commit chưa nằm
trong danh sách sẽ chặn đề xuất. Docs/control-plane commits vẫn được liệt kê
trong manifest; không tự lấy đầu main đang di chuyển. PM phải kiểm thêm AC và
dependencies ngoài Git. Clone controller riêng là nơi fetch/read, không chạy
app code hoặc sửa checkout ứng dụng đang phục vụ.

Kết quả có `batch_id`, `digest`, `baseline_sha`, `candidate_sha`, `prs`. Lưu chúng
vào handoff. Mọi lệnh sau cần `repository`, `batch_id`, `digest` đúng manifest:

| action | Trường thêm | Điều kiện/kết quả |
| --- | --- | --- |
| `defer` | `pr`, `reference` | Dùng trước propose; giữ item cho lần gom sau. |
| `approve` | `reference` của lời duyệt PO | `awaiting_approval` → `approved`; duyệt lại trả `changed:false`, không spawn thêm. |
| `ci-start` | Không | Tạo branch `delivery/<batch_id>` đúng candidate và dispatch CI hiện có trên GitHub. Không chạy test sản phẩm trên Mac. |
| `ci-verify` | `run_id` | Kiểm workflow CI, event dispatch, branch, SHA, run/job pytest success. Không chấp nhận skip hoặc branch bị đổi. |
| `claim` | `reference` handoff; `observed_baseline_sha` | Ốp Dev đối chiếu bản Dev thực tế trước; chỉ một đợt hoạt động cho repo. |
| `deployed` | `sha`, `reference` receipt; `checks` | Receipt đúng candidate, các check dưới đây đều true; chuyển sang chờ PO nghiệm thu. |
| `accept` / `reject` | `sha`, `reference` lời PO | Chỉ bản Dev đã triển khai đúng SHA. Reject không tạo đề xuất release. |
| `deployment-failed` | `sha` runtime thực tế; `reference` | Ghi thất bại ở bản cũ hoặc candidate; nếu chưa xác định bản chạy thì giữ claim và điều tra. |
| `supersede` | `reference` | Rút đề xuất/chốt bỏ lần thất bại đã đối chiếu. Không hủy deployment đang chạy. Giữ lịch sử, không tái dùng batch ID. |

Checks của `deployed`: `local_health`, `public_health`, `webhook`, `menu`,
`services`, đều boolean true, kèm receipt có SHA runtime/process đã xác minh.
Không chỉ lấy checkout HEAD làm chứng cứ. Ốp Dev dùng readiness checker tunnel
hiện có; restart đúng dịch vụ khi cần nạp bản mới, không restart toàn Mac hoặc
đổi branch pin về main để chạy helper. Không giả lập tin nhắn của PO để test.

PM phải giao **cả chuỗi CI → claim → deploy → receipt** cho Ốp Dev ngay sau duyệt,
không kết thúc handoff ở `ci-start`. Ốp Dev theo dõi GitHub run cho đến khi hoàn
tất trong phiên vận hành, ghi `ci-verify` rồi mới triển khai. Khi CI lỗi hoặc
timeout thì báo blocker; không triển khai hoặc tự lặp dispatch không giới hạn.
Controller này không phải daemon tự deploy và không gọi model định kỳ.

`ci-start` ghi ý định trước khi gọi GitHub. Nếu lỗi giữa chừng, trạng thái vẫn là
`ci_requested`: đối chiếu branch/run đã tạo, tiếp tục bằng run ID hoặc dispatch
thủ công **một lần** sau khi chứng minh chưa có run; không gọi lại mù. Chỉ dùng
CI trên `delivery/<batch_id>`, không dispatch workflow deploy. Một poll monitor
bị gián đoạn không nhân đôi deployment. Telegram có thể lặp nếu process chết
giữa gửi thành công và lưu acknowledgement; không cam kết exactly-once.

Nếu PO từ chối nghiệm thu, giữ evidence lỗi. Sau reconcile/supersede, tạo đợt
sửa mới; phạm vi UAT tự mang theo phần đã triển khai nhưng bị từ chối. Không
đẩy PR đã chạy trở lại danh sách “chưa triển khai”.

## Phase và hồ sơ chuẩn bị Production

Profile có thể khai báo `release_groups:[{"id":"hong-hot-phase-1", "title":
"Hóng hớt — Phase 1", "prs":[1067,1068]}]`. PM/Ốp Dev cập nhật nhóm khi scope
được chốt. Không đoán phase từ trạng thái closed. Khi tất cả members accepted,
controller tạo một đề xuất ổn định cho nhóm, monitor báo qua Telegram PM trong
lượt tiếp theo (mỗi 5 phút khi Mac/Gateway chạy). Feature ngoài nhóm dùng đợt Dev
làm đơn vị đề xuất. Đề xuất nhóm có cả danh sách PR của nhóm, kể cả nghiệm thu
qua nhiều đợt Dev; vẫn phải đối chiếu toàn bộ khác biệt với Production.

`release-readiness` cần `repository`, `release_id`, `sha` đã nghiệm thu,
`production_baseline_sha` thực tế và `reference` của phiên kiểm chứng. `evidence`
phải có reference không rỗng cho đủ sáu mục: `production_baseline`,
`cumulative_scope`, `migration_data_access`, `backup_rollback`,
`artifact_platform`, `executor_ready`. Đây là attestation của PM/DevOps trong
phiên tin cậy, không tự chứng minh nội dung evidence hay quyền Production.
Sau đó monitor báo cần trình PR phát hành. Không có lệnh nào của ledger cấp
Production approval, merge, tự tạo release PR hoặc triển khai VPS.

`import-accepted` chỉ dùng chuyển lịch sử có receipt vận hành và xác nhận PO:
`sha`, `prs`, `title`, `reference`, `deployment_reference`. Chỉ khởi tạo baseline
một lần, xác minh các merge SHA là ancestor của bản đó, giữ nhãn
`historical-owner-confirmed`; không tự tạo Telegram message ID. Lịch sử trước
ledger không được giả thành một đợt vừa được controller triển khai/kiểm thử.
