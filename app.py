import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from functools import wraps
import json
import datetime 
import os
import time

# ----------------------------------------------------
# 1. Cấu hình CSDL MongoDB (Giữ nguyên)
# ----------------------------------------------------
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
    # print("WARNING: Application running without database connection.")
    # telemetry_collection = None 
    # Fallback cho chạy local không có mạng/CSDL
    telemetry_collection = None

# ----------------------------------------------------
# 2. Cấu hình MQTT
# ----------------------------------------------------
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883 
MQTT_CMD_TOPIC = "robot/command/set" 
MQTT_STATUS_TOPIC = "robot/telemetry/status" 

app = Flask(__name__)
# SECRET_KEY rất quan trọng cho session
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bat_ky_chuoi_bi_mat_nao_do_123456') 

mqtt_client = mqtt.Client()

current_state = {
    'speed': 0,
    'mode': 'MANUAL',
    'last_command': 'S',
    'gas': 0
}

# ----------------------------------------------------
# 3. Xử lý sự kiện MQTT (Ghi CSDL)
# ----------------------------------------------------
def on_connect(client, userdata, flags, rc):
    print(f"MQTT Connected with result code {rc}")
    client.subscribe(MQTT_STATUS_TOPIC) 

def on_message(client, userdata, msg):
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
                    "gas": data.get('gas', 0),       
                    "raw_data": data                                   
                }
                try:
                    telemetry_collection.insert_one(telemetry_record)
                    print("MongoDB <== Data inserted.")
                except Exception as db_err:
                    print(f"Lỗi ghi DB: {db_err}")

            if 'speed' in data:
                current_state['speed'] = data['speed']
            if 'mode' in data:
                current_state['mode'] = data['mode']
            if 'gas' in data:
                current_state['gas'] = data['gas']
            
    except Exception as e:
        print(f"Error processing message: {e}")

# ----------------------------------------------------
# 4. Routes: Login & Logout
# ----------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        # Đăng nhập đơn giản (Hardcoded)
        if username == 'admin' and password == '123456':
            session['logged_in'] = True
            return jsonify({'status': 'OK', 'message': 'Login successful'})
        else:
            return jsonify({'status': 'Error', 'message': 'Sai tên đăng nhập hoặc mật khẩu'}), 401
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login_page'))

# ----------------------------------------------------
# 5. Routes: Dashboard & History
# ----------------------------------------------------
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/history')
@login_required
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

# ----------------------------------------------------
# 6. Routes: Control (API)
# ----------------------------------------------------
@app.route('/command', methods=['POST'])
@login_required
def receive_command():
    data = request.get_json()
    command = data.get('command', 'S')
    
    mqtt_payload = json.dumps({
        'cmd': command,
        'spd': current_state['speed'],
    })
    
    mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
    
    current_state['last_command'] = command
    print(f"Flask ==> PUBLISHED: {command}")
    
    return jsonify({
        'status': 'OK', 
        'message': f'Published {command}',
        'mode': current_state['mode'] 
    }), 200

@app.route('/speed/<int:value>', methods=['POST'])
@login_required
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
@login_required
def toggle_mode():
    global current_state
    if current_state['mode'] == 'MANUAL':
        current_state['mode'] = 'AUTO'
        mqtt_client.publish(MQTT_CMD_TOPIC, json.dumps({'cmd': 'S', 'spd': 0}))
    else:
        current_state['mode'] = 'MANUAL'
        
    mqtt_client.publish('robot/mode/status', current_state['mode'], qos=0)
    
    return jsonify({'status': 'OK', 'mode': current_state['mode']}), 200

# -----------------
# 7. Khởi động Server
# -----------------
if __name__ == '__main__':
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    client_id = f'flask-robot-{time.time()}'
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start() 
    except Exception as e:
        print(f"Không thể kết nối MQTT Broker: {e}")

    # Chạy Rebug mode nếu ở local
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode, threaded=True)