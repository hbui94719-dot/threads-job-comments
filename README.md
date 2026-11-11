> **Tình trạng cài đặt:** lịch gửi đang tắt. Cần thiết lập Threads API và secret `THREADS_ACCESS_TOKEN`. Ảnh QR đã được chủ tài khoản đồng ý công khai; ảnh có tại `assets/comment.jpg` và `image_url` đã được cấu hình bằng đường dẫn cố định. Xem `RUN_STATUS.md`.

# Bình luận Threads theo từ khóa — chạy bằng GitHub Actions

Tool dùng nội dung bạn soạn sẵn để trả lời những **bài công khai tìm được qua API Threads**. Từ khóa mặc định: `tìm việc online`, `công việc online`, `job online`. Lịch mặc định chạy mỗi 30 phút; giới hạn tối đa 500 bình luận trong **24 giờ trượt**, tối đa 12 bình luận mỗi lượt. Đây là trần gửi, không phải cam kết tìm đủ 500 bài.

**Bạn cần được Meta duyệt quyền tìm bài công khai trước khi dùng.** Chỉ tạo tài khoản GitHub và thêm mật khẩu Threads sẽ không đủ. App chưa được duyệt `threads_keyword_search` chỉ tìm được bài của tài khoản đã đăng nhập. Tool không cần mật khẩu hoặc cookie Threads. Kết quả API có thể khác thứ tự và nội dung trên thanh tìm kiếm của app.

Tool chỉ chọn bài gốc của người khác trong 72 giờ gần đây theo mặc định, bỏ qua bài trả lời và bài của chính tài khoản chạy. Nội dung bài phải chứa ít nhất một cụm từ khóa sau khi chuẩn hóa chữ hoa/thường, dấu tiếng Việt và dấu câu. Vì vậy kết quả được lọc hẹp hơn danh sách thô mà API trả về.

Bản này có thể gửi **nội dung kèm một ảnh** và chụp ảnh màn hình bình luận sau khi gửi. Đã nhận ảnh mã QR Zalo của bạn và kèm nguyên bản tại `assets/comment.jpg`. Ảnh hiện chỉ nằm trong bộ code, chưa được lưu trữ công khai; `image_url` vẫn là `null`. Chưa thể chạy live khi chưa có URL ảnh tải công khai qua HTTPS và chưa hoàn thành quyền/token Meta. Chưa có bình luận nào được gửi.

## 1. Thiết lập Meta/Threads lần đầu

1. Mở [Meta for Developers](https://developers.facebook.com/) bằng Safari, đăng nhập và hoàn tất đăng ký tài khoản nhà phát triển nếu chưa có. Dùng **Yêu cầu trang web cho máy tính** nếu giao diện iPhone thiếu mục.
2. Trong **My Apps**, tạo app dùng trường hợp **Access the Threads API** nếu tùy chọn này được cung cấp. Hoàn tất thông tin app mà Meta yêu cầu; tên mục có thể thay đổi theo dashboard.
3. Trong phần thiết lập Threads, thêm tài khoản Threads của bạn làm người thử nghiệm khi app còn ở chế độ phát triển. Chấp nhận lời mời thử nghiệm trong phần cài đặt tài khoản Threads theo hướng dẫn của Meta.
4. Cấu hình OAuth/đăng nhập Threads và URL chuyển hướng hợp lệ theo [hướng dẫn bắt đầu của Meta](https://developers.facebook.com/docs/threads/get-started). Nếu dashboard cung cấp chức năng tạo user token, dùng chức năng đó; nếu cần luồng OAuth, [mẫu app chính thức của Meta](https://github.com/fbsamples/threads_api) có mã đăng nhập và đổi token. Không tự gửi App Secret hay token vào chat hoặc tệp trong repo.
5. Các quyền tool cần là `threads_basic`, `threads_keyword_search`, `threads_content_publish`, `threads_manage_replies`. Trong phần **App Review / Permissions and Features**, xin **advanced access** cho các quyền Meta yêu cầu, đặc biệt `threads_keyword_search`. Chuẩn bị thông tin app, mô tả mục đích, video minh họa và các yêu cầu xác minh mà dashboard hiển thị. Meta quyết định việc duyệt; tool không tự cấp hoặc vượt qua quyền này.
6. Sau khi quyền tìm kiếm công khai được duyệt, cấp lại token cho tài khoản của bạn với đủ quyền. Ưu tiên long-lived user token cho lịch chạy. Kiểm tra quyền và thời hạn thực tế bằng công cụ debug token của Meta hoặc mẫu app chính thức. Token có thể hết hạn hoặc bị thu hồi: cần làm mới/thay token trước khi hết hạn. Tool này không tự thay GitHub Secret.

Bạn có thể chuẩn bị repo trong lúc chờ duyệt, nhưng hãy giữ `enabled: false`. Xác nhận yêu cầu duyệt quyền công khai trong [issue của mẫu Meta](https://github.com/fbsamples/threads_api/issues/72); đối chiếu API trong [bộ request Postman chính thức](https://github.com/fbsamples/threads_api/blob/main/postman/threads-api.postman_collection.json).

## 2. Đưa code lên GitHub từ iPhone

Tạo một repo mới, bật tùy chọn thêm README. **Repo private** giúp giữ nội dung mẫu, lịch sử bài đã bình luận và báo cáo trong phạm vi người được cấp quyền. Chi phí Actions và Codespaces phụ thuộc gói GitHub; xem quota/billing của tài khoản trước khi bật lịch.

Đưa các tệp trong thư mục `threads-job-comments` vào **gốc repo**, giữ nguyên thư mục ẩn `.github`. Workflow phải ở đường dẫn `.github/workflows/threads-comments.yml`, không nằm thêm một tầng thư mục bên ngoài.

Nếu Safari không tải được cả thư mục, có thể dùng **GitHub Codespaces** trên trình duyệt:

1. Trong repo mới, mở **Code → Codespaces → Create codespace**. Trên iPhone có thể cần chế độ trang web máy tính. Codespaces cần khả dụng trong tài khoản của bạn.
2. Trong Explorer của Codespaces, dùng **Upload** để tải tệp ZIP `threads-job-comments.zip` vào thư mục repo đang mở.
3. Mở Terminal của Codespaces và chạy các lệnh sau. Tệp ZIP phải có thư mục ngoài cùng tên `threads-job-comments`:

   ```sh
   python3 -m zipfile -e threads-job-comments.zip /tmp/threads-job-comments-import
   cp -R /tmp/threads-job-comments-import/threads-job-comments/. .
   git add .
   git commit -m "Add Threads keyword comment tool"
   git push
   ```

4. Đóng/stop Codespace sau khi hoàn tất; workflow sau đó chạy bằng GitHub Actions, không cần giữ Codespace hay iPhone mở.

## 3. Thêm token và nội dung của bạn

Trong repo, mở **Settings → Secrets and variables → Actions → New repository secret**:

- Tên: `THREADS_ACCESS_TOKEN`.
- Giá trị: user access token Threads được cấp cho đúng tài khoản và đủ quyền ở bước 1.

Không tạo tệp chứa token, không dán token vào `config.json` hay `comments.json`. `GITHUB_TOKEN` được Actions cấp tự động, không cần tạo secret riêng cho nó.

Sửa `comments.json` thành một mảng JSON chứa nội dung thực tế của bạn, ví dụ về định dạng:

```json
[
  "NỘI DUNG BÌNH LUẬN THỨ NHẤT CỦA BẠN",
  "NỘI DUNG BÌNH LUẬN THỨ HAI CỦA BẠN"
]
```

`comments.json` trong bản được chuẩn bị đã chứa nội dung bạn cung cấp; kiểm tra và chỉnh lại trước khi bật. Mảng trên chỉ minh họa định dạng khi thêm hoặc sửa mẫu. Tool luân phiên các nội dung theo danh sách; mỗi bài tối đa một lần trả lời theo lịch sử của tool. Dùng `\n` trong chuỗi JSON nếu cần xuống dòng; dấu `"` bên trong nội dung cần viết thành `\"`.

### Thêm ảnh đính kèm

Ảnh đã nhận nằm tại `assets/comment.jpg`; không cần gửi lại ảnh để chuẩn bị code. Bước còn lại là cung cấp một URL ảnh mà Meta truy cập được.

1. Tải `assets/comment.jpg` lên một dịch vụ lưu trữ ảnh, object storage/CDN hoặc website cung cấp **đường dẫn HTTPS trực tiếp tới tệp ảnh**. Meta phải tải được ảnh mà không cần đăng nhập hay cookie. Một đường dẫn tới trang xem ảnh hoặc đường dẫn ảnh chỉ tồn tại trên iPhone không đáp ứng yêu cầu này. Nếu **bạn chọn dùng repo GitHub công khai**, có thể đưa ảnh vào repo rồi dùng URL `https://raw.githubusercontent.com/OWNER/REPO/COMMIT/assets/comment.jpg`, thay `COMMIT` bằng SHA commit chứa ảnh để URL cố định. Link raw của repo private không cho Meta tải ảnh công khai. Bộ code không tự tạo repo hoặc công khai ảnh/repo cho bạn.
2. Mở đường dẫn trong cửa sổ Safari riêng tư để kiểm tra ảnh tải được khi chưa đăng nhập. Đảm bảo định dạng, kích thước và tỷ lệ ảnh phù hợp [quy định đăng media của Meta](https://developers.facebook.com/docs/threads/posts).
3. Đặt URL đó vào `image_url` trong `config.json`, giữ `require_image: true` và `screenshots: true`. Ví dụ các trường cần bổ sung/chỉnh trong cấu hình hiện có:

   ```json
   {
     "image_url": "https://your-image-host.example/your-photo.jpg",
     "require_image": true,
     "screenshots": true
   }
   ```

   Thay URL ví dụ bằng URL ảnh thực tế. Không thay toàn bộ `config.json` bằng đoạn ba trường này; những trường từ khóa/giới hạn vẫn cần giữ. Tool dùng cùng một ảnh này cho các mẫu bình luận trong đợt chạy.

Trong `config.json`, sửa danh sách `keywords` nếu cần. `enabled` ban đầu là `false`; giữ nguyên để xem trước. Giới hạn 500 được hiểu là 24 giờ trượt, có tính các lượt chạy trước đó, không đặt lại vào nửa đêm.

## 4. Xem trước rồi bật lịch

1. Mở tab **Actions**, chọn workflow **Threads job comments**. Nếu GitHub yêu cầu bật Actions, bật cho repo này.
2. Chọn **Run workflow**, `mode = preview`, giữ `initialize_state` không đánh dấu. Preview tìm bài và lập báo cáo, không gửi bình luận. Lần xem trước đầu tiên không cần nhánh lịch sử.
3. Khi chạy xong, tải artifact `threads-report-...` để xem `report.json`. Kiểm tra đúng tài khoản, bài tìm được và nội dung trước khi bật gửi. Nếu chỉ thấy bài của chính bạn hoặc không có bài công khai, kiểm tra App Review/quyền tìm kiếm.
4. Khi ảnh, nội dung và quyền API đã đủ, sửa `config.json` thành `"enabled": true` trên nhánh mặc định và commit. Sau đó chạy thủ công `mode = live`, **đánh dấu `initialize_state` chỉ ở lần thiết lập live đầu tiên**. Workflow tạo nhánh `bot-state` để lưu lịch sử trước khi gửi.
5. Sau lượt live đầu tiên, kiểm tra `report.json` và ảnh trong thư mục `screenshots` của artifact. Bật lịch ở bước cuối bằng **Settings → Secrets and variables → Actions → Variables → New repository variable**: tên `THREADS_SCHEDULE_ENABLED`, giá trị `true`. Đây là biến thông thường, không phải secret. Khi chưa đặt biến này, các job theo lịch được bỏ qua; bạn vẫn chạy thủ công được.
6. Lịch chạy ở phút **17 và 47 của mỗi giờ UTC**. Lượt chạy tự động chỉ gửi khi biến `THREADS_SCHEDULE_ENABLED` là `true` và `config.enabled` là `true`. Nếu lịch đến trước lúc bạn khởi tạo lịch sử, lượt đó sẽ dừng và yêu cầu khởi tạo thủ công.

GitHub Actions chạy từng lượt, không phải máy chủ chạy liên tục 24/7. Lịch có thể trễ hoặc bị bỏ khi tải cao; repo công khai không có hoạt động trong 60 ngày có thể bị tự tắt lịch. Lịch chỉ dùng workflow trên nhánh mặc định. Xem [quy định lịch chạy của GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Muốn dừng ngay, disable workflow trong Actions; để tạm dừng các lượt tiếp theo mà không khởi động job định kỳ, đặt biến `THREADS_SCHEDULE_ENABLED` về `false`. Cũng có thể đặt `config.enabled` về `false` để dừng gửi.

### Ảnh chụp sau khi gửi

Khi `screenshots: true`, workflow cài Playwright 1.56.0 và Chromium cho lượt live. Tool mở permalink bình luận đã đăng, xác nhận nội dung/tài khoản/ảnh trên trang rồi chụp kết quả thực tế. Artifact có `report.json` và những tệp chụp thành công trong `screenshots/`, giữ 7 ngày theo cấu hình workflow. Việc cài trình duyệt và tải trang có thể làm tăng thời gian chạy/chi phí Actions.

Trình duyệt chụp ảnh không có phiên đăng nhập Threads của bạn. Nếu Threads hiện tường đăng nhập, không tải ảnh hoặc không xác minh được bình luận, báo cáo sẽ đánh dấu `proof_failed` và dừng gửi tiếp. Bình luận đã được API xác nhận vẫn được giữ là đã gửi; **tool không đăng lại để thử lấy screenshot**. Cần mở permalink kiểm tra thủ công trên iPhone. Ảnh chụp lỗi hoặc thiếu ảnh chụp không chứng minh bình luận chưa được đăng.

Biên nhận gửi lưu `proof_status`: `pending` khi đang chờ chụp, `captured` khi đã xác minh/chụp được, `failed` nếu bước chụp lỗi. Khi còn biên nhận `pending` hoặc `failed`, các lượt live tiếp theo có bật screenshot sẽ dừng để chờ bạn kiểm tra. Đối chiếu **reply ID/permalink đã gửi** trên Threads; không đăng lại và không xóa lịch sử gửi chỉ để làm workflow chạy tiếp. Cần xử lý bằng chứng của bình luận cũ trước khi tiếp tục lịch.

## 5. Lịch sử và khôi phục sau lỗi

Nhánh `bot-state` lưu `state/state.json`. **Không xóa nhánh hoặc đặt lại tệp này để chữa lỗi kết nối**: làm vậy sẽ mất lịch sử và có thể bình luận trùng. Workflow dừng nếu không đọc được nhánh, thay vì tự giả định đây là lần đầu. Chỉ tạo lịch sử mới nếu đây thực sự là tài khoản/thiết lập mới chưa gửi gì qua tool.

Trước khi gửi một đợt, tool lưu các bài đã giữ chỗ lên GitHub. Sau mỗi kết quả nó cập nhật lịch sử tại chỗ, rồi đẩy kết quả cuối lên nhánh trạng thái. Những bài chưa hề được thử gửi sẽ được trả lại khỏi giữ chỗ khi kết thúc bình thường. Nếu runner bị ngắt đúng lúc gửi, những bài chưa chắc kết quả vẫn nằm trong `pending` và **không tự gửi lại**. Cần đối chiếu thực tế trên Threads trước khi xử lý các mục này; không xóa hàng loạt `pending` khi chưa rõ bài nào đã được trả lời. Mọi mục `pending` tiếp tục tính vào trần gửi cho đến khi được đối chiếu và xử lý, kể cả sau 24 giờ.

Tool kiểm tra quota trả lời thực tế từ API và dừng khi lỗi quyền, quota hoặc lỗi mạng khiến kết quả không chắc chắn. 500/ngày là mức trần bạn cấu hình; quota Meta còn lại có thể thấp hơn, và bình luận bạn gửi ngoài tool cũng có thể tiêu hao quota Meta.

Chỉ chạy **một bản tool cho một tài khoản** với cùng lịch sử. Hai repo chạy độc lập sẽ không chia sẻ chống trùng hoặc trần 500. Khi cần đổi tài khoản, chuẩn bị một bộ lịch sử riêng; không ghi đè token để tiếp tục dùng lịch sử tài khoản cũ.

## Chạy cục bộ / kiểm tra code

Yêu cầu Python 3.12. Tìm bài/xem trước không cần thư viện ngoài; live có chụp ảnh màn hình cần Playwright và Chromium.

```sh
python3 -m unittest discover -v
python3 bot.py --mode preview --state state/state.json --report report.json
```

Đặt `THREADS_ACCESS_TOKEN` bằng cơ chế biến môi trường/secret của máy chạy. Khi chạy live ngoài Actions, cần cấu hình cơ chế checkpoint bền vững tương ứng; bản workflow đã cung cấp sẵn checkpoint lên nhánh GitHub trước khi gửi.
