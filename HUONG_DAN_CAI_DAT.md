# HƯỚNG DẪN CÀI ĐẶT VÀ SỬ DỤNG HỆ THỐNG MOBILE ROBOT

## 1. Tổng quan hệ thống
Đây là ứng dụng web điều khiển Robot, được viết bằng **Python (Flask)**. Hệ thống bao gồm:
- **Web Controller**: Giao diện điều khiển và xem lịch sử (File: `app.py`, `templates/`).
- **Database**: MongoDB (Lưu trữ lịch sử di chuyển, tốc độ, cảm biến gas).
- **IoT Protocol**: MQTT (Giao tiếp giữa Web và Robot).

> **LƯU Ý QUAN TRỌNG**: Dự án này dùng **Flask**, không phải PHP. Code xử lý nằm ở `app.py`. Việc đổi đuôi file sang `.php` là không thể trừ khi viết lại toàn bộ Server.

---

## 2. Cài đặt trên máy tính (Localhost)

### Yêu cầu
- Cài đặt [Python 3.x](https://www.python.org/downloads/)
- Cài đặt thư viện: Mở terminal `cmd` hoặc `PowerShell` tại thư mục dự án và chạy:
  ```bash
  pip install -r requirements.txt
  ```
  *(Các thư viện chính: `Flask`, `pymongo`, `paho-mqtt`)*

### Chạy ứng dụng
Chạy lệnh sau trong terminal:
```bash
python app.py
```
Sau đó mở trình duyệt: [http://localhost:5000](http://localhost:5000)

**Tài khoản mặc định:**
- User: `admin`
- Password: `123456`

---

## 3. Chỉnh sửa code theo yêu cầu

### Cấu hình Gas và Cảnh báo
Hệ thống đã được cập nhật để xử lý cảm biến Gas từ ESP8266 (giả sử dữ liệu gửi lên qua MQTT có trường `gas`).

**Vị trí chỉnh sửa ngưỡng cảnh báo (400):**
Mở file `templates/history.html` và tìm đoạn code sau (khoảng dòng 90):
```html
{% if row.gas > 400 %}
    <span class="gas-danger">...</span>
{% endif %}
```
Thay số `400` bằng giá trị bạn muốn cảnh báo.

**Vị trí hiển thị Icon/Màu sắc:**
Cũng trong `templates/history.html`, phần CSS (đầu file):
```css
.gas-warning { background-color: #ffe6e6; } /* Màu nền cảnh báo */
.gas-danger { color: #dc3545; } /* Màu chữ cảnh báo */
```

### Cấu hình MQTT & Database
Mở file `app.py`:
- `MQTT_BROKER`: Địa chỉ Broker (mặc định: `broker.hivemq.com`).
- `MONGO_URI`: Địa chỉ MongoDB. Để chạy online trên Render, bạn cần điền chuỗi kết nối Atlas vào biến môi trường `MONGO_URI` trên Render.

---

## 4. Cách đẩy lên Render (Online)
**Có, dự án này hoàn toàn đẩy lên Render được!** Render hỗ trợ Flask rất tốt.

### Bước 1: Chuẩn bị Github
1. Tạo Repo trên GitHub.
2. Đẩy code lên:
   ```bash
   git add .
   git commit -m "Update full features"
   git push origin main
   ```

### Bước 2: Tạo Web Service trên Render
1. Vào [Render Dashboard](https://dashboard.render.com).
2. Tạo **New Web Service**, kết nối tới Git Repo của bạn.
3. Cấu hình:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Vào mục **Environment Variables** (Biến môi trường) thêm:
   - `MONGO_URI`: `mongodb+srv://<user>:<password>@cluster...` (Link DB của bạn)
   - `FLASK_SECRET_KEY`: `bat_ky_chuoi_nao`
5. Bấm **Create Web Service**.

---

## 5. Kết nối với ESP8266 (Arduino)
Trong code Arduino (`.ino`), bạn cần gửi dữ liệu JSON lên topic `robot/telemetry/status` với định dạng:
```json
{
  "speed": 100,
  "mode": "MANUAL",
  "gas": 450
}
```
Khi ESP gửi `gas` > `400`, web sẽ tự hiển thị cảnh báo đỏ trong lịch sử.
