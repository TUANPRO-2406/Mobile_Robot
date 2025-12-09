import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import json
import datetime 
import os
import ssl 

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/") 
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
# 2. Cấu hình MQTT (Đảm bảo các biến được đọc)
# ----------------------------------------------------
MQTT_BROKER = "6400101a95264b8e8819d8992ed8be4e.s1.eu.hivemq.cloud" 
MQTT_PORT = 8883 # Cổng MQTTS (Bảo mật)
MQTT_CMD_TOPIC = "robot/command/set" 
MQTT_STATUS_TOPIC = "robot/telemetry/status" 

MQTT_USERNAME = os.environ.get('MQTT_USER', 'tuanpro')
MQTT_PASSWORD = os.environ.get('MQTT_PASS', 'Tuan@24062004')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_local') 

# Khởi tạo client, sử dụng API V2 
mqtt_client = mqtt.Client()

current_state = {
    'speed': 0,
    'mode': 'MANUAL',
    'last_command': 'S'
}

# ----------------------------------------------------
# 3. Logic Kết nối MQTT (Khởi tạo NỘI BỘ Worker)
# ----------------------------------------------------

# 🚨 ĐÃ SỬA: Chấp nhận 5 tham số để khớp với API V2
def on_connect(client, userdata, flags, rc):
    """Callback khi kết nối thành công: Đăng ký Topic (API V2)."""
    print(f"MQTT Connected successfully with result code {rc}")
    client.subscribe(MQTT_STATUS_TOPIC) 

# 🚨 ĐÃ SỬA: Chấp nhận 4 tham số để khớp với API V2
def on_message(client, userdata, msg):
    """Callback khi nhận được dữ liệu trạng thái từ ESP (API V2)."""
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

# 🚨 SỬ DỤNG HOOK CỦA FLASK: Khởi tạo MQTT trong tiến trình Worker 
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

@app.route('/history')
def history():
    # Lấy dữ liệu từ MongoDB, sắp xếp mới nhất trước
    data = []
    if telemetry_collection is not None:
        try:
            # Lấy 50 bản ghi gần nhất
            cursor = telemetry_collection.find().sort('timestamp', -1).limit(50)
            for doc in cursor:
                data.append({
                    'timestamp': doc.get('timestamp').strftime('%Y-%m-%d %H:%M:%S') if doc.get('timestamp') else 'N/A',
                    'speed': doc.get('speed', 0),
                    'direction': doc.get('direction', 'S'),
                    'mode': doc.get('mode', 'MANUAL'),
                    'gas': doc.get('gas', 0)
                })
        except Exception as e:
            print(f"Lỗi đọc lịch sử: {e}")
            
    return render_template('history.html', history_data=data)

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


@app.route('/status', methods=['GET'])
def get_status():
    """Trả về trạng thái hiện tại của Robot để đồng bộ giao diện."""
    return jsonify({
        'status': 'OK',
        'speed': current_state['speed'],
        'mode': current_state['mode'],
        'gas': current_state.get('gas', 0)
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health endpoint: checks MongoDB ping and MQTT connection status."""
    db_ok = False
    try:
        mongo_client.admin.command('ping')
        db_ok = True
    except Exception:
        db_ok = False

    mqtt_ok = bool(app.config.get('mqtt_connected_flag', False))

    return jsonify({
        'status': 'OK',
        'mongo': 'connected' if db_ok else 'disconnected',
        'mqtt': 'connected' if mqtt_ok else 'disconnected'
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)