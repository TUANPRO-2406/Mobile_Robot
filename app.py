import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import json
import datetime 
import os


MONGO_URI = os.environ.get("MONGO_URI") 
DB_NAME = "Mobile_Robot" # Tên CSDL chính xác của bạn
COLLECTION_NAME = "telemetry"

try:
    # 🚨 SỬ DỤNG SERVER_API: Chỉ dùng khi kết nối đến Atlas (chứa 'srv' trong URI)
    if "srv" in MONGO_URI:
        mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    else:
        mongo_client = MongoClient(MONGO_URI)
        
    db = mongo_client[DB_NAME]
    telemetry_collection = db[COLLECTION_NAME]
    
    # Gửi lệnh ping để xác nhận kết nối TCP/IP
    mongo_client.admin.command('ping')
    print("MongoDB connected successfully (CLOUD Optimized).")
except Exception as e:
    # Nếu kết nối thất bại (do lỗi bad auth, hoặc server localhost không chạy)
    print(f"MongoDB connection failed: {e}")
    print("WARNING: Application running without database connection.")
    telemetry_collection = None 

# ----------------------------------------------------
# 2. Cấu hình MQTT
# ----------------------------------------------------
MQTT_BROKER = "broker.hivemq.com" # Broker công cộng (sử dụng được cả Local và Cloud)
MQTT_PORT = 1883
MQTT_CMD_TOPIC = "robot/command/set" # Topic Flask PUBLISH (ESP SUBSCRIBE)
MQTT_STATUS_TOPIC = "robot/telemetry/status" # Topic ESP PUBLISH (Flask SUBSCRIBE)

app = Flask(__name__)
# Đọc SECRET_KEY từ biến môi trường Render
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') 

# Khởi tạo MQTT Client với API V2 (Loại bỏ cảnh báo DeprecationWarning)
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

current_state = {
    'speed': 0,
    'mode': 'MANUAL',
    'last_command': 'S' # Lệnh cuối cùng
}

# ----------------------------------------------------
# 3. Xử lý sự kiện MQTT (Ghi CSDL)
# ----------------------------------------------------
def on_connect(client, userdata, flags, rc):
    """Callback khi kết nối thành công: Đăng ký Topic."""
    print(f"MQTT Connected with result code {rc}")
    client.subscribe(MQTT_STATUS_TOPIC) 

def on_message(client, userdata, msg):
    """Callback khi nhận được dữ liệu trạng thái từ ESP."""
    global current_state
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)

        # Ghi dữ liệu vào MongoDB chỉ khi nhận được phản hồi từ ESP
        if msg.topic == MQTT_STATUS_TOPIC:
            
            if telemetry_collection is not None:
                telemetry_record = {
                    "timestamp": datetime.datetime.now(),
                    "speed": data.get('speed', current_state['speed']),
                    "mode": data.get('mode', current_state['mode']),  
                    "direction": current_state['last_command'], # Lệnh cuối cùng đã được thực thi
                    "raw_data": data                                   
                }
                telemetry_collection.insert_one(telemetry_record)
                print("MongoDB <== Data inserted.")
            else:
                print("MongoDB is not connected. Data not saved.")

            if 'speed' in data:
                current_state['speed'] = data['speed']
            if 'mode' in data:
                current_state['mode'] = data['mode']
            
    except Exception as e:
        print(f"Error processing message or inserting to MongoDB: {e}")

# ----------------------------------------------------
# 4. Định tuyến và MQTT Publishing (Gửi lệnh từ Web)
# ----------------------------------------------------
@app.route('/')
def index():
    """Trang chủ hiển thị giao diện điều khiển."""
    return render_template('index.html')

@app.route('/command', methods=['POST'])
def receive_command():
    """Nhận lệnh từ Web Client và PUBLISH qua MQTT."""
    data = request.get_json()
    command = data.get('command', 'S')
    
    mqtt_payload = json.dumps({
        'cmd': command,
        'spd': current_state['speed'],
    })
    
    # PUBLISH lệnh đến Topic mà ESP đang lắng nghe
    mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
    
    # Cập nhật trạng thái lệnh cuối cùng (Quan trọng cho việc ghi CSDL)
    current_state['last_command'] = command
    print(f"Flask ==> PUBLISHED: {command} to {MQTT_CMD_TOPIC}")
    
    return jsonify({
        'status': 'OK', 
        'message': f'Published {command}',
        'mode': current_state['mode'] 
    }), 200

@app.route('/speed/<int:value>', methods=['POST'])
def set_speed(value):
    """Cập nhật tốc độ và PUBLISH lệnh DỪNG với tốc độ mới."""
    global current_state
    if 0 <= value <= 255:
        current_state['speed'] = value
        
        # PUBLISH lệnh dừng để đảm bảo robot cập nhật tốc độ
        mqtt_payload = json.dumps({
            'cmd': 'S', 
            'spd': value,
        })
        mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
        
        return jsonify({'status': 'OK', 'speed': value, 'mode': current_state['mode']}), 200
        
    return jsonify({'status': 'Error', 'message': 'Invalid speed value'}), 400

@app.route('/mode', methods=['POST'])
def toggle_mode():
    """Chuyển đổi chế độ và PUBLISH lệnh DỪNG nếu chuyển sang AUTO."""
    global current_state
    if current_state['mode'] == 'MANUAL':
        current_state['mode'] = 'AUTO'
        # Dừng xe khi chuyển sang chế độ Tự động
        mqtt_client.publish(MQTT_CMD_TOPIC, json.dumps({'cmd': 'S', 'spd': 0}))
    else:
        current_state['mode'] = 'MANUAL'
        
    mqtt_client.publish('robot/mode/status', current_state['mode'], qos=0)
    
    return jsonify({'status': 'OK', 'mode': current_state['mode']}), 200

# -----------------
# 5. Khởi động Server
# -----------------
if __name__ == '__main__':
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    # Kết nối MQTT Broker
    client_id = f'flask-robot-publisher-{datetime.datetime.now().timestamp()}'
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start() 
    
    # Chạy Flask App (Sẽ được thay thế bằng Gunicorn trên Render)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)