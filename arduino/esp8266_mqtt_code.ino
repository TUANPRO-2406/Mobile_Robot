#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// --- Cấu hình WiFi ---
const char* ssid = "ESP8266";
const char* password = "12345678";

// --- Cấu hình MQTT ---
const char* mqtt_server = "test.mosquitto.org";
const int mqtt_port = 1883;
const char* mqtt_topic_speed = "robot/speed";
const char* mqtt_topic_command = "robot/command";

WiFiClient espClient;
PubSubClient client(espClient);

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.println("WiFi connected");
}

void callback(char* topic, byte* payload, unsigned int length) {
  // Nhận lệnh từ MQTT -> Gửi xuống Arduino qua Serial
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  // message ví dụ: "FORWARD" hoặc "STOP"
  // Cần chuyển đổi sang JSON format mà Arduino hiểu: {"cmd":"F", "spd":150}
  // Tuy nhiên, server hiện tại gửi command string đơn giản.
  // Ta cần map command string sang ký tự.
  
  StaticJsonDocument<200> doc;
  int speed = 150; // Tốc độ mặc định nếu không có
  
  if (message == "FORWARD") doc["cmd"] = "F";
  else if (message == "BACKWARD") doc["cmd"] = "B";
  else if (message == "LEFT") doc["cmd"] = "L";
  else if (message == "RIGHT") doc["cmd"] = "R";
  else if (message == "STOP") doc["cmd"] = "S";
  else doc["cmd"] = "S";
  
  doc["spd"] = speed; // Có thể cải tiến để nhận tốc độ từ MQTT topic khác
  
  serializeJson(doc, Serial);
  Serial.println();
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("ESP8266_Robot_Bridge")) {
      client.subscribe(mqtt_topic_command);
    } else {
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(9600);
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Đọc dữ liệu từ Arduino gửi lên qua Serial
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    // line là JSON: {"s1":..., "gas":...}
    // Publish nguyên chuỗi JSON lên MQTT
    client.publish(mqtt_topic_speed, line.c_str());
  }
}
