# Tình trạng cài đặt

- Code được chuẩn bị cho repo `hbui94719-dot/threads-job-comments`.
- Repo bạn tạo đang công khai. Lịch gửi bình luận đang tắt.
- Nội dung bạn gửi đã được nhập vào `comments.json`.
- Ảnh QR nguyên bản có trong ZIP của cuộc trò chuyện, tại `assets/comment.jpg`.
- Ảnh chưa được tải lên repo công khai: xét duyệt tự động yêu cầu xác nhận riêng về việc công khai đường dẫn tham gia nhóm. Không tải lên ảnh mã hóa hoặc bản thay thế.
- `image_url` vẫn là `null`; tool yêu cầu có ảnh trước khi gửi.
- Cần app Meta được duyệt quyền tìm bài công khai và user access token.
- Chưa đăng bình luận nào, chưa có ảnh chụp xác nhận đăng thật.
- Bộ kiểm thử offline kiểm tra lọc bài, quota, lưu trạng thái, chống trùng và xử lý lỗi chụp màn hình.

Nếu không chụp được bình luận thật, tool giữ lịch sử đã gửi và chặn gửi tiếp. Không đăng lại để thử lấy screenshot.
