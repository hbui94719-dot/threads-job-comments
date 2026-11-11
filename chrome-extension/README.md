# Bản Chrome — không cần app Meta

Đây là bản chạy trên Chrome của chính bạn, dùng phiên Threads bạn tự đăng nhập. Không dùng token API, mật khẩu trong code hay cookie xuất ra ngoài.

**Đã kiểm thử bằng trang giả lập và API Chrome giả lập. Chưa kiểm thử gửi trên tài khoản Threads thật.** Giao diện Threads thực tế có thể khác; tiện ích sẽ dừng nếu không tìm được đúng tài khoản, khung soạn thảo, nút gửi, ảnh hoặc bình luận đã đăng. Chưa thể bảo đảm chạy qua đêm cho đến khi thử thành công trên máy của bạn.

Môi trường kiểm thử của phiên này bị chính sách quản trị viên chặn nạp tiện ích đã giải nén. Vì vậy chưa xác nhận được bước cài/service worker với Chrome thật; cần kiểm tra khi bạn cài trên máy của mình. Không thay đổi hay vượt chính sách quản trị viên để cài trên máy bị quản lý.

## Cài trên Windows

1. Tải `threads-chrome.zip` do mình gửi và giải nén bằng **Extract All / Giải nén tất cả**. Không cài trực tiếp từ ZIP.
2. Mở Google Chrome, gõ `chrome://extensions` vào thanh địa chỉ.
3. Bật **Developer mode / Chế độ dành cho nhà phát triển** ở góc trên bên phải.
4. Bấm **Load unpacked / Tải tiện ích đã giải nén**. Chọn thư mục có tệp `manifest.json` bên trong.
5. Bấm biểu tượng mảnh ghép của Chrome và ghim **Threads – Tìm việc online**.

Nếu lấy code từ GitHub bằng **Code → Download ZIP**, giải nén rồi chọn thư mục `chrome-extension` bên trong repo.

## Chạy lần đầu

1. Mở Threads trong Chrome, tự đăng nhập và chắc chắn tài khoản còn bình luận được.
2. Bấm biểu tượng tiện ích **ngay trên tab Threads**. Nhập đúng tên tài khoản của bạn, bỏ dấu `@`. Ví dụ hồ sơ là `threads.com/@abc` thì nhập `abc`.
3. Kiểm tra nội dung và ảnh QR. Để số lượng **1**, bấm **Bắt đầu**.
4. Tiện ích sẽ tìm một bài, mở khung trả lời, điền nội dung, gắn ảnh và **tự bấm gửi**. Sau đó kiểm tra bình luận đã xuất hiện và lưu screenshot vào `Downloads/threads-job-comments`.
5. Chỉ sau khi lần thử xác nhận đúng tài khoản, đúng bài và lưu được ảnh, mới tăng số lượng lên mức bạn muốn (tối đa 500) rồi bấm Bắt đầu.

Giữ tab Threads được chọn, cửa sổ Chrome mở, mạng ổn định và **máy không chuyển sang chế độ ngủ**. Không dùng tab đó cho việc khác khi đang chạy. Có thể đóng cửa sổ nhỏ của tiện ích. Mỗi phút xử lý tối đa một bài; 500 bài có thể cần hơn 8 giờ và không cam kết tìm đủ số lượng. Tool chỉ quét kết quả tìm từ khóa `tìm việc online`, `công việc online`, `job online`, không chuyển sang bảng tin. Nó bỏ qua kết quả không chứa cụm từ liên quan và các bài đã có trong lịch sử cục bộ.

## Dừng, lỗi và nhật ký

- Bấm lại biểu tượng tiện ích → **Dừng**. Một thao tác gửi đã được Chrome nhận có thể đã hoàn tất; tool không tự đăng lại.
- Khi Threads yêu cầu đăng nhập, xác minh, báo hạn chế hoặc giao diện khác dự kiến, tool dừng. Không xử lý hoặc vượt xác minh tự động.
- Khi không chắc gửi thành công hoặc chưa lưu được screenshot, tool dừng và giữ bài đó trong lịch sử. Chọn **Tải nhật ký** để xem đường dẫn và kiểm tra trên Threads. Không xóa dữ liệu hoặc cài lại chỉ để thử gửi lại bài chưa rõ kết quả.
- Screenshot phải chứa phần bình luận đúng tài khoản, đúng nội dung và ảnh hiển thị. Nếu không nằm trọn trong màn hình, tool dừng; cần kiểm tra thủ công, không tạo ảnh giả.
- Thông số 500 là trần nội bộ trong 24 giờ trượt, tính cả bài chưa rõ kết quả. Các giới hạn của Threads vẫn có thể thấp hơn. Lịch sử chống trùng giữ 10.000 bài gần nhất và mọi bài chưa rõ kết quả; không chia sẻ giữa máy/profile Chrome khác.
- Khi Chrome khởi động lại hoặc tiện ích cập nhật, tool dừng; bạn tự bấm Bắt đầu lần nữa. Tiện ích không được đăng lên Chrome Web Store, chỉ cài từ thư mục đã giải nén.

## Kiểm thử dành cho người xem code

`node test-background.cjs` kiểm tra ghi giữ chỗ trước khi gửi, không gửi lại khi kết quả không rõ, dừng trước nút gửi và xử lý screenshot lỗi.

`python3 test-page.py` dùng Chromium/Playwright với **toàn bộ trang được giả lập**, không gửi bình luận lên Threads thật. Tệp kiểm thử này không cần chạy để cài tiện ích.
