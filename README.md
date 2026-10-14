# price-watch-bot

Bản MVP lấy các mục sau và gửi thành một tin nhắn Telegram:

- Vàng SJC: giá mua/bán, quy đổi sang đồng/chỉ.
- Cà phê Đắk Lắk: đồng/kg.
- Hồ tiêu Đắk Lắk: đồng/kg.
- Sầu riêng Ri6 và Dona: giá đẹp/xô nếu trang nguồn cung cấp.

Bot không dùng AI. Chương trình dùng thư viện chuẩn Python, lấy dữ liệu mỗi lần chạy và không giữ lại token trong mã nguồn. Giá quá 3 ngày vẫn được hiển thị nếu có, kèm nhãn giá cũ và ngày nguồn. Khi nguồn lỗi hoặc không có giá mới, bot dùng giá có ngày gần nhất đã lưu; nếu chưa từng có giá phù hợp, bot ghi rõ chưa có dữ liệu để hiển thị.

## Cài đặt trên Windows

1. Cài Python 3.11 trở lên.
2. Tạo bot bằng `@BotFather` trong Telegram và nhấn **Start** ở cuộc trò chuyện với bot.
3. Sao chép `.env.example` thành `.env`; điền token do BotFather cấp.
4. Mở PowerShell tại thư mục này và chạy:

   ```powershell
   python .\price_bot.py get-chat-id
   ```

5. Chép chat ID riêng của bạn vào `TELEGRAM_CHAT_ID` trong `.env`.
6. Gửi thử báo cáo:

   ```powershell
   python .\price_bot.py report
   ```

Không gửi token bot trong tin nhắn hoặc đưa file `.env` lên Git.

## Chạy hằng ngày trên GitHub Actions

GitHub Actions chạy workflow trên máy chủ của GitHub, nên máy tính cá nhân không cần bật. Workflow trong `.github/workflows/daily.yml` được đặt mặc định gửi lúc **09:37 mỗi ngày theo giờ Việt Nam**; có thể chạy thử thủ công từ tab **Actions**.

Workflow lưu các giá có ngày nguồn trong GitHub Actions cache để dùng lại khi trang nguồn không tải được hoặc thiếu giá. Cache không chứa token. Nếu cache bị xóa và nguồn vẫn lỗi, báo cáo sẽ ghi rõ chưa có giá cũ để dùng.

1. Tạo một repository **private** trên GitHub.
2. Tải các file trong thư mục này lên repository, gồm cả thư mục `.github/workflows`. Không tải file `.env` lên GitHub.
3. Vào **Settings → Secrets and variables → Actions → New repository secret** và thêm hai secret:
   - `TELEGRAM_BOT_TOKEN`: token lấy từ BotFather.
   - `TELEGRAM_CHAT_ID`: chat ID riêng của bạn.
4. Mở tab **Actions**, chọn **Daily price report**, nhấn **Run workflow** để gửi thử.

Sau khi workflow có trên nhánh mặc định, lịch hằng ngày sẽ tự chạy. Không dán token vào mã nguồn, README, hoặc tin nhắn. Giờ chạy theo lịch có thể bị trễ khi GitHub quá tải.

Để đổi giờ, sửa cron trong `.github/workflows/daily.yml`; ví dụ `"37 8 * * *"` là 08:37 theo giờ Việt Nam.

Nếu chỉ muốn chạy trên máy cá nhân, có thể dùng **Windows Task Scheduler**, nhưng máy cần bật và có Internet tại giờ chạy.

## Nguồn và giới hạn đã biết

- Vàng lấy từ bảng giá trên SJC. Trang SJC niêm yết theo nghìn đồng/lượng; chương trình đổi sang đồng/chỉ bằng phép quy đổi 1 lượng = 10 chỉ.
- Cà phê lấy từ trang Đắk Lắk của Giacaphe.com.
- Hồ tiêu lấy từ bảng giá của Giacaphe.com; trang này ghi nguồn dữ liệu giá là Giatieu.com.
- Sầu riêng lấy Ri6 và Dona (Thái/Monthong) từ trang Giacaphe.com. Trang đã kiểm tra gần đây vẫn hiển thị bài ngày 27/08/2025, nên mục này sẽ bị đánh dấu dữ liệu cũ cho tới khi nguồn cập nhật.
- Cấu trúc HTML của nguồn có thể thay đổi. Giá cũ luôn đi kèm ngày nguồn; chương trình không tự tạo hoặc gán ngày mới cho giá cũ.

Trang Giacaphe.com ghi dữ liệu giá chỉ mang tính tham khảo và có thể thay đổi theo thời điểm, khu vực hoặc đơn vị thu mua. Báo cáo gom các liên kết nguồn ở cuối tin nhắn để dễ đọc; từng dòng giá giữ ngày nguồn tương ứng.
