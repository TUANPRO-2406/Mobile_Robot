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

TELEMETRY_COLLECTION = "telemetry"
SENSOR_COLLECTION = "sensor"

try:
    if "srv" in MONGO_URI:
        mongo_client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
    else:
        mongo_client = MongoClient(MONGO_URI)
        
    db = mongo_client[DB_NAME]
    telemetry_collection = db[TELEMETRY_COLLECTION]
    sensor_collection = db[SENSOR_COLLECTION]
    
    mongo_client.admin.command('ping')
    print("MongoDB connected successfully (CLOUD Optimized).")
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    print("WARNING: Application running without database connection.")
    telemetry_collection = None 
    sensor_collection = None

MQTT_BROKER = "6400101a95264b8e8819d8992ed8be4e.s1.eu.hivemq.cloud" 
MQTT_PORT = 8883 
MQTT_CMD_TOPIC = "robot/command/set" 
MQTT_STATUS_TOPIC = "robot/telemetry/status" 
MQTT_DATA_TOPIC = "robot/telemetry/data"
MQTT_USERNAME = os.environ.get('MQTT_USER', 'tuanpro')
MQTT_PASSWORD = os.environ.get('MQTT_PASS', 'Tuan@24062004')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key_local') 

mqtt_client = mqtt.Client()

current_state = {
    'speed': 150,
    'mode': 'MANUAL',
    'last_command': 'S',
    'gas': 0
}

def on_connect(client, userdata, flags, rc):
    print(f"MQTT Connected successfully with result code {rc}")
    client.subscribe(MQTT_STATUS_TOPIC) 
    client.subscribe(MQTT_DATA_TOPIC)

def on_message(client, userdata, msg):
    global current_state
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)

        # 1. DATA TOPIC: Gas Only
        if msg.topic == MQTT_DATA_TOPIC:
            gas_val = data.get('gas', 0)
            current_state['gas'] = gas_val

            if gas_val > 500 and sensor_collection is not None:
                sensor_record = {
                    "timestamp": datetime.datetime.now(),
                    "gas_value": gas_val,
                }
                sensor_collection.insert_one(sensor_record)
                print(f"ALARM: Gas leak detected ({gas_val}) -> Saved to DB 'sensor'")

        # 2. STATUS TOPIC: Robot State & Avoidance
        elif msg.topic == MQTT_STATUS_TOPIC:
            # Update Robot State
            current_state['mode'] = data.get('mode', current_state['mode'])
            current_state['speed'] = data.get('spd', current_state['speed'])
            if 'cmd' in data:
                current_state['last_command'] = data['cmd']

            # Avoidance Events
            if 'duration' in data and telemetry_collection is not None:
                telemetry_record = {
                    "timestamp": datetime.datetime.now(),
                    "direct": data.get('direct'),
                    "angle": data.get('angle'),
                    "duration": data.get('duration'),
                }
                telemetry_collection.insert_one(telemetry_record)
                print(f"EVENT: Obstacle Avoided ({data.get('direct')}) -> Saved to DB 'telemetry'")

    except Exception as e:
        print(f"Error processing message: {e}")

@app.before_request
def setup_mqtt_worker():
    if 'mqtt_connected_flag' not in app.config or not app.config.get('mqtt_connected_flag'):
        print("--- Setting up MQTT Worker Process ---")
        if MQTT_USERNAME and MQTT_PASSWORD:
            mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        try:
            tls_ctx = ssl.create_default_context()
            tls_ctx.check_hostname = True
            mqtt_client.tls_set_context(tls_ctx)
        except Exception as e:
            print(f"WARNING: Could not set MQTT TLS context: {e}")
            
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            mqtt_client.loop_start()
            app.config['mqtt_connected_flag'] = True
            print("INFO: MQTT Client thread started successfully.")
        except Exception as e:
            print(f"FATAL ERROR: Could not connect MQTT Broker. Details: {e}")


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
        'mode': current_state['mode'] 
    })
    mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
    
    current_state['last_command'] = command
    
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
            'mode': current_state['mode'] 
        })
        mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
        
        return jsonify({'status': 'OK', 'speed': value, 'mode': current_state['mode']}), 200
        
    return jsonify({'status': 'Error', 'message': 'Invalid speed value'}), 400

@app.route('/mode', methods=['POST'])
def toggle_mode():
    global current_state
    if current_state['mode'] == 'MANUAL':
        current_state['mode'] = 'AUTO'
    else:
        current_state['mode'] = 'MANUAL'
        
    mqtt_payload = json.dumps({
        'cmd': 'S', 
        'spd': current_state['speed'],
        'mode': current_state['mode']
    })
    mqtt_client.publish(MQTT_CMD_TOPIC, mqtt_payload, qos=0)
    mqtt_client.publish('robot/mode/status', json.dumps({"mode": current_state['mode']}), qos=0)
    
    return jsonify({
        'status': 'OK', 
        'mode': current_state['mode']
    }), 200


@app.route('/status', methods=['GET'])
def get_status():
    global current_state
    return jsonify({
        'status': 'OK',
        'speed': current_state['speed'],
        'mode': current_state['mode'],
        'last_command': current_state['last_command'],
        'gas': current_state.get('gas', 0)
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
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


@app.route('/history')
def history_page():
    if telemetry_collection is None and sensor_collection is None:
        return render_template('history.html', gas_history=[], auto_history=[], selected_date="")
    
    selected_date = request.args.get('date', "") 
    query_filter = {}
    
    if selected_date:
        try:
            start_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d')
            end_date = start_date + datetime.timedelta(days=1)
            query_filter["timestamp"] = {"$gte": start_date, "$lt": end_date}
        except ValueError:
            pass 

    try:
        gas_history = []
        if sensor_collection is not None:
            gas_filter = {}
            gas_filter.update(query_filter)
            
            gas_cursor = sensor_collection.find(gas_filter).sort('timestamp', -1)
            if not selected_date: gas_cursor = gas_cursor.limit(50)
            
            for record in gas_cursor:
                gas_history.append({
                    'timestamp': record.get('timestamp').strftime('%d/%m/%Y %H:%M:%S'),
                    'value': "CÓ" if record.get('gas_value', 0)  >500 else "KHÔNG"
                })

        auto_history = []
        if telemetry_collection is not None:
            auto_filter = {}
            auto_filter.update(query_filter)
            
            auto_cursor = telemetry_collection.find(auto_filter).sort('timestamp', -1)
            if not selected_date: auto_cursor = auto_cursor.limit(50)
            
            for record in auto_cursor:
                auto_history.append({
                    'timestamp': record.get('timestamp').strftime('%d/%m/%Y %H:%M:%S'),
                    'direct': record.get('direct', 'S'),
                    'angle': record.get('angle', 0),
                    'duration': record.get('duration', 0),
                })
        
        return render_template('history.html', 
                               gas_history=gas_history,
auto_history=auto_history,
                               selected_date=selected_date)
        
    except Exception as e:
        print(f"[ERROR] history page: {e}")
        return render_template('history.html', gas_history=[], auto_history=[], selected_date="")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
