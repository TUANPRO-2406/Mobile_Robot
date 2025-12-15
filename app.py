import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import json
import datetime 
import os
import ssl 

# ----------------------------------------------------
# 1. Cấu hình CSDL MongoDB (CLOUD/RENDER)
# ----------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/") 
DB_NAME = "Mobile_Robot" # Dùng tên CSDL mà bạn đang dùng (Mobile_Robot)
# 🚨 COLLECTION CHO DỮ LIỆU ĐIỀU KHIỂN (Status/ACK)
TELEMETRY_COLLECTION_NAME = "telemetry" 
# 🚨 COLLECTION MỚI CHO DỮ LIỆU CẢM BIẾN (Gas, RPMs)
SENSOR_COLLECTION_NAME = "sensor"

try:
    if "srv" in MONGO_URI:
        mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    else:
        mongo_client = MongoClient(MONGO_URI)
        
    db = mongo_client[DB_NAME]
    
    # Khởi tạo cả hai Collections
    telemetry_collection = db[TELEMETRY_COLLECTION_NAME]
    sensor_collection = db[SENSOR_COLLECTION_NAME]
    
    mongo_client.admin.command('ping')
    print("MongoDB connected successfully (CLOUD Optimized).")
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    print("WARNING: Application running without database connection.")
    telemetry_collection = None 
    sensor_collection = None

# ----------------------------------------------------
# 2. Cấu hình MQTT (CHIA TOPIC)
# ----------------------------------------------------
MQTT_BROKER = "6400101a95264b8e8819d8992ed8be4e.s1.eu.hivemq.cloud" 
MQTT_PORT = 8883 # Cổng MQTTS (Bảo mật)
MQTT_CMD_TOPIC = "robot/command/set" 

# 🚨 TOPIC PHẢN HỒI ĐIỀU KHIỂN (Status/ACK)
MQTT_CONTROL_ACK_TOPIC = "robot/telemetry/status" 
# 🚨 TOPIC DỮ LIỆU CẢM BIẾN (Data)
MQTT_DATA_TOPIC = "robot/telemetry/data" 

# Đọc User và Pass từ Biến môi trường (BẮT BUỘC cho HiveMQ Cloud)
MQTT_USERNAME = os.environ.get('MQTT_USER', '')
MQTT_PASSWORD = os.environ.get('MQTT_PASS', '')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_local') 

# Khởi tạo client, sử dụng API V2 (vì thư viện đã được nâng cấp)
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

current_state = {
    'speed': 0,
    'mode': 'MANUAL',
    'last_command': 'S'
}

# ----------------------------------------------------
# 3. Logic Kết nối MQTT (Khởi tạo NỘI BỘ Worker)
# ----------------------------------------------------

# Chữ ký hàm API V2: on_connect(client, userdata, flags, rc, properties)
def on_connect(client, userdata, flags, rc, properties):
    """Callback khi kết nối thành công: Đăng ký cả hai Topic."""
    print(f"MQTT Connected successfully with result code {rc}")
    
    # 🚨 ĐĂNG KÝ CẢ HAI TOPIC TỪ ESP
    client.subscribe(MQTT_CONTROL_ACK_TOPIC) 
    client.subscribe(MQTT_DATA_TOPIC) 
    print(f"Subscribed to: {MQTT_CONTROL_ACK_TOPIC} and {MQTT_DATA_TOPIC}")

# Chữ ký hàm API V2: on_message(client, userdata, msg, properties)
def on_message(client, userdata, msg, properties):
    """Callback khi nhận được dữ liệu từ một trong hai Topic."""
    global current_state
    
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        
        # 🚨 ĐIỀU CHỈNH LOGIC DỰA TRÊN TOPIC 🚨
        
        if msg.topic == MQTT_CONTROL_ACK_TOPIC:
            # Dữ liệu Điều khiển/Trạng thái (Status, Speed) -> Collection 'telemetry'
            
            if telemetry_collection is not None:
                telemetry_record = {
                    "timestamp": datetime.datetime.now(),
                    "speed": data.get('speed', current_state['speed']),
                    "mode": data.get('mode', current_state['mode']),  
                    "direction": data.get('direction', current_state['last_command']), # Lấy hướng từ ESP
                    "raw_data": data                                   
                }
                telemetry_collection.insert_one(telemetry_record)
                print("MongoDB <== Control ACK inserted into TELEMETRY.")

            # Cập nhật trạng thái cục bộ
            if 'speed' in data:
                current_state['speed'] = data['speed']
            if 'mode' in data:
                current_state['mode'] = data['mode']
            
        elif msg.topic == MQTT_DATA_TOPIC:
            # Dữ liệu Cảm biến (RPM, Gas) -> Collection 'sensor'
            
            if sensor_collection is not None:
                sensor_record = {
                    "timestamp": datetime.datetime.now(),
                    "gas_value": data.get('gas'),
                    "rpm1": data.get('rpm1'),
                    "rpm2": data.get('rpm2'),
                    "rpm3": data.get('rpm3'),
                    "rpm4": data.get('rpm4'),
                }
                sensor_collection.insert_one(sensor_record)
                print("MongoDB <== Sensor DATA inserted into SENSOR.")
            
        else:
            print(f"Received unhandled topic: {msg.topic}")
            
    except Exception as e:
        print(f"Error processing message or inserting to MongoDB: {e}")

# ... (Hàm start_mqtt và các hàm định tuyến khác không đổi) ...

@app.before_request
def setup_mqtt_worker():
    """Khởi tạo MQTT Client cho mỗi Worker Gunicorn (Chỉ chạy một lần)."""
    
    if 'mqtt_connected_flag' not in app.config or not app.config.get('mqtt_connected_flag'):
        
        print("--- Setting up MQTT Worker Process ---")
        
        # BƯỚC 1: Cấu hình Username/Password
        if MQTT_USERNAME and MQTT_PASSWORD:
            mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # Log trạng thái cấu hình MQTT (không in mật khẩu)
        print(f"MQTT config -> broker={MQTT_BROKER} port={MQTT_PORT} user_set={bool(MQTT_USERNAME)}")
        
        # BƯỚC 2: Cấu hình TLS/SSL sử dụng system CA (an toàn hơn trên Render)
        try:
            tls_ctx = ssl.create_default_context()
            tls_ctx.check_hostname = True
            mqtt_client.tls_set_context(tls_ctx)
            print("MQTT TLS: Using system default CA context.")
        except Exception as e:
            print(f"WARNING: Could not set MQTT TLS context: {e}")
            
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        
        client_id = f'flask-robot-publisher-{datetime.datetime.now().timestamp()}'
        try:
            # 🚨 THỬ KẾT NỐI VÀ BẮT ĐẦU LUỒNG MQTT
            print(f"Attempting MQTT connect to {MQTT_BROKER}:{MQTT_PORT} ...")
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            mqtt_client.loop_start()
            app.config['mqtt_connected_flag'] = True
            print("INFO: MQTT Client thread started successfully within Worker.")
        except Exception as e:
            print(f"FATAL ERROR: Could not connect MQTT Broker. Details: {e}")

# ----------------------------------------------------
# 4. Định tuyến và MQTT Publishing (Giữ nguyên)
# ----------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/command', methods=['POST'])
def receive_command():
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
    global current_state
    if current_state['mode'] == 'MANUAL':
        current_state['mode'] = 'AUTO'
        mqtt_client.publish(MQTT_CMD_TOPIC, json.dumps({'cmd': 'S', 'spd': 0}))
    else:
        current_state['mode'] = 'MANUAL'
        
    mqtt_client.publish('robot/mode/status', current_state['mode'], qos=0)
    
    return jsonify({
        'status': 'OK', 
        'mode': current_state['mode']
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)