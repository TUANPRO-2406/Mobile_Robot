import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from pymongo.server_api import ServerApi # Thư viện cần thiết cho Atlas tối ưu
import json
import datetime 
import os
import ssl # Thư viện cần thiết cho TLS

# ----------------------------------------------------
# 1. Cấu hình CSDL MongoDB (CLOUD/RENDER)
# ----------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI") 
DB_NAME = "Mobile_Robot" 
COLLECTION_NAME = "telemetry"

try:
    if "srv" in MONGO_URI:
        mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    else:
        mongo_client = MongoClient(MONGO_URI)
        
    db = mongo_client[DB_NAME]
    telemetry_collection = db[COLLECTION_NAME]
    
    mongo_client.admin.command('ping')
    print("MongoDB connected successfully (CLOUD Optimized).")
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    print("WARNING: Application running without database connection.")
    telemetry_collection = None 

# ----------------------------------------------------
# 2. Cấu hình MQTT
# ----------------------------------------------------
MQTT_BROKER = "broker.hivemq.com" 
# 🚨 ĐÃ SỬA: Cổng MQTTS tiêu chuẩn
MQTT_PORT = 8883 
MQTT_CMD_TOPIC = "robot/command/set" 
MQTT_STATUS_TOPIC = "robot/telemetry/status" 

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') 

mqtt_client = mqtt.Client()

current_state = {
    'speed': 0,
    'mode': 'MANUAL',
    'last_command': 'S'
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

        if msg.topic == MQTT_STATUS_TOPIC:
            
            if telemetry_collection is not None:
                telemetry_record = {
                    "timestamp": datetime.datetime.now(),
                    "speed": data.get('speed', current_state['speed']),
                    "mode": data.get('mode', current_state['mode']),  
                    "direction": current_state['last_command'], 
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
    
    mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
    
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
        mqtt_client.publish(MQTT_CMD_TOPIC, json.dumps({'cmd': 'S', 'spd': 0}))
    else:
        current_state['mode'] = 'MANUAL'
        
    mqtt_client.publish('robot/mode/status', current_state['mode'], qos=0)
    
    return jsonify({'status': 'OK', 'mode': current_state['mode']}), 200

# -----------------
# 5. Khởi động Server
# -----------------
if __name__ == '__main__':
    # 🚨 ĐÃ SỬA: Thêm tùy chọn TLS cho kết nối MQTTS
    mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS) 
    
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    client_id = f'flask-robot-publisher-{datetime.datetime.now().timestamp()}'
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start() 
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)