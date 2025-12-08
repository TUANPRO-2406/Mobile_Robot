import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify, request
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import json
import datetime
import os
import ssl

# ----------------------------------------------------
# 1. CẤU HÌNH MONGODB (NẾU CÓ)
# ----------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI")  # hoặc gán trực tiếp nếu test local
DB_NAME = "Mobile_Robot"
COLLECTION_NAME = "telemetry"

telemetry_collection = None

try:
    if MONGO_URI:
        if "srv" in MONGO_URI:
            mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
        else:
            mongo_client = MongoClient(MONGO_URI)

        db = mongo_client[DB_NAME]
        telemetry_collection = db[COLLECTION_NAME]
        mongo_client.admin.command('ping')
        print("✅ MongoDB connected successfully.")
    else:
        print("⚠️ MONGO_URI not set. Running without database.")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    telemetry_collection = None

# ----------------------------------------------------
# 2. CẤU HÌNH MQTT (HIVEMQ CLOUD)
# ----------------------------------------------------
MQTT_BROKER = "6400101a95264b8e8819d8992ed8be4e.s1.eu.hivemq.cloud"
MQTT_PORT = 8883

MQTT_USERNAME = "tuanpro24062004@gmail.com"
MQTT_PASSWORD = "Tuan@24062004"

MQTT_CMD_TOPIC = "robot/command/set"
MQTT_STATUS_TOPIC = "robot/telemetry/status"

# ----------------------------------------------------
# 3. FLASK APP
# ----------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = "secret-key-demo"

# ----------------------------------------------------
# 4. BIẾN TRẠNG THÁI HIỆN TẠI
# ----------------------------------------------------
current_state = {
    'speed': 0,
    'mode': 'MANUAL',
    'last_command': 'S'
}

# ----------------------------------------------------
# 5. MQTT CLIENT
# ----------------------------------------------------
client_id = f"flask-robot-{int(datetime.datetime.now().timestamp())}"
mqtt_client = mqtt.Client(client_id=client_id)

mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.tls_set(tls_version=ssl.PROTOCOL_TLS)

# ----------------------------------------------------
# 6. MQTT CALLBACK
# ----------------------------------------------------
def on_connect(client, userdata, flags, rc):
    print("✅ MQTT Connected with code:", rc)
    client.subscribe(MQTT_STATUS_TOPIC)
    print("✅ Subscribed:", MQTT_STATUS_TOPIC)

def on_message(client, userdata, msg):
    global current_state

    try:
        payload = msg.payload.decode()
        print("📥 MQTT RECEIVED:", payload)

        data = json.loads(payload)

        if msg.topic == MQTT_STATUS_TOPIC:

            if telemetry_collection is not None:
                telemetry_record = {
                    "timestamp": datetime.datetime.now(),
"speed": data.get('speed', current_state['speed']),
                    "mode": data.get('mode', current_state['mode']),
                    "direction": data.get('direction', current_state['last_command']),
                    "raw_data": data
                }
                telemetry_collection.insert_one(telemetry_record)
                print("✅ MongoDB: Data inserted")

            if 'speed' in data:
                current_state['speed'] = data['speed']

            if 'mode' in data:
                current_state['mode'] = data['mode']

    except Exception as e:
        print("❌ MQTT MESSAGE ERROR:", e)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# ----------------------------------------------------
# 7. ROUTE WEB
# ----------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

# ----------------------------------------------------
# 8. NHẬN LỆNH ĐIỀU KHIỂN TỪ WEB → GỬI MQTT
# ----------------------------------------------------
@app.route('/command', methods=['POST'])
def receive_command():
    global current_state

    data = request.get_json()
    command = data.get('command', 'S')

    mqtt_payload = json.dumps({
        'cmd': command,
        'spd': current_state['speed']
    })

    mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload)
    current_state['last_command'] = command

    print(f"🚀 Flask ==> MQTT PUBLISHED: {mqtt_payload}")

    return jsonify({
        'status': 'OK',
        'command': command,
        'speed': current_state['speed'],
        'mode': current_state['mode']
    }), 200

# ----------------------------------------------------
# 9. SET SPEED
# ----------------------------------------------------
@app.route('/speed/<int:value>', methods=['POST'])
def set_speed(value):
    global current_state

    if 0 <= value <= 255:
        current_state['speed'] = value

        mqtt_payload = json.dumps({
            'cmd': 'S',
            'spd': value
        })

        mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload)

        print(f"🚀 Set Speed ==> MQTT: {mqtt_payload}")

        return jsonify({
            'status': 'OK',
            'speed': value,
            'mode': current_state['mode']
        }), 200

    return jsonify({'status': 'Error', 'message': 'Invalid speed'}), 400

# ----------------------------------------------------
# 10. MODE AUTO / MANUAL
# ----------------------------------------------------
@app.route('/mode', methods=['POST'])
def toggle_mode():
    global current_state

    if current_state['mode'] == 'MANUAL':
        current_state['mode'] = 'AUTO'

        mqtt_client.publish(MQTT_CMD_TOPIC, json.dumps({
            'cmd': 'S',
            'spd': 0
        }))
    else:
        current_state['mode'] = 'MANUAL'

    print("🔄 Mode changed to:", current_state['mode'])

    return jsonify({
        'status': 'OK',
        'mode': current_state['mode']
    }), 200
# ----------------------------------------------------
# 11. KHỞI ĐỘNG SERVER
# ----------------------------------------------------
if __name__ == '__main__':
    print("🚀 Connecting to MQTT Broker...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    app.run(host='0.0.0.0', port=5000, debug=True)