#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h> // Thư viện BẮT BUỘC cho kết nối SSL/TLS
#include <PubSubClient.h> 
#include <ArduinoJson.h> 
#include <WiFiManager.h>
// ----------------------------------------------------
// 1. THÔNG TIN CẤU HÌNH MẠNG VÀ MQTT
// ----------------------------------------------------
// Thay đổi bằng thông tin Wi-Fi chính xác của bạn
// const char* ssid = "DuongTran";
// const char* password = "haiphong742016";

// Thông tin Broker HiveMQ Cloud của bạn
const char* mqtt_server = "6400101a95264b8e8819d8992ed8be4e.s1.eu.hivemq.cloud"; 
const int mqtt_port = 8883; // Cổng MQTTS (Bảo mật)

// 🚨 THÔNG TIN ĐĂNG NHẬP HIVE MQ (CẦN THAY ĐỔI)
const char* mqtt_user = "tuanpro"; 
const char* mqtt_pass ="Tuan@24062004"; 

const char* MQTT_CMD_TOPIC = "robot/command/set"; 
const char* MQTT_STATUS_TOPIC = "robot/telemetry/status"; 

<<<<<<< HEAD
// Biến thời gian cho việc gửi dữ liệu định kỳ
unsigned long lastMsg = 0;
const long interval = 3000; // 3 giây gửi 1 lần 

=======
>>>>>>> b91306d14b940347b7ce30a33f2c94898781f811
// --- Khởi tạo các đối tượng ---
// Dùng WiFiClientSecure để thiết lập kết nối bảo mật
WiFiClientSecure espClient; 
PubSubClient client(espClient);
WiFiManager wifiManager;          // Khởi tạo WiFiManager
StaticJsonDocument<100> arduinoDoc; 

// ----------------------------------------------------
// 2. CÁC HÀM TIỆN ÍCH
// ----------------------------------------------------

// Gửi lệnh JSON qua Serial đến Arduino
void sendCommandToArduino(String command, int speed) {
  arduinoDoc["cmd"] = command.substring(0, 1); 
  arduinoDoc["spd"] = speed;
  
  serializeJson(arduinoDoc, Serial); 
  Serial.println();
}

// PUBLISH thông tin phản hồi (trạng thái) lên Broker
<<<<<<< HEAD
void publishStatus(String command, int speed, int gas) {
=======
void publishStatus(String command, int speed) {
>>>>>>> b91306d14b940347b7ce30a33f2c94898781f811
  if (!client.connected()) return; // Không gửi nếu bị ngắt kết nối
  
  StaticJsonDocument<200> statusDoc;
  statusDoc["direction"] = command; 
  statusDoc["speed"] = speed;
<<<<<<< HEAD
  statusDoc["mode"] = "MANUAL"; // Lưu ý: Cần biến toàn cục nếu muốn theo dõi đúng mode
  statusDoc["gas"] = gas;
=======
  statusDoc["mode"] = "MANUAL"; 
>>>>>>> b91306d14b940347b7ce30a33f2c94898781f811

  char payload[200];
  serializeJson(statusDoc, payload);

  client.publish(MQTT_STATUS_TOPIC, payload);
  Serial.print("MQTT PUBLISHED status: ");
  Serial.println(payload);
}

// ----------------------------------------------------
// 3. HÀM XỬ LÝ SỰ KIỆN MQTT
// ----------------------------------------------------
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("MQTT Command received on topic: ");
  Serial.println(topic);
  
  String message = "";
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  
  StaticJsonDocument<200> flaskDoc;
  DeserializationError error = deserializeJson(flaskDoc, message);

  if (error) {
    Serial.print("JSON parsing failed: ");
    Serial.println(error.f_str());
    return;
  }

  String cmd = flaskDoc["cmd"].as<String>();
  int spd = flaskDoc["spd"].as<int>();

  // 1. Gửi lệnh qua Serial xuống Arduino
  sendCommandToArduino(cmd, spd);

  // 2. Gửi phản hồi lên Broker (PUBLISH)
<<<<<<< HEAD
  // Đọc gas ngay lúc gửi command để phản hồi luôn
  int currentGas = analogRead(A0);
  publishStatus(cmd, spd, currentGas);
=======
  publishStatus(cmd, spd);
>>>>>>> b91306d14b940347b7ce30a33f2c94898781f811
}

// --- Hàm kết nối lại với MQTT Broker ---
void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTTS connection...");
    String clientId = "ESP8266SecureClient-";
    clientId += String(random(0xffff), HEX);
    
    // 🚨 SỬ DỤNG USER/PASS VÀ ID ĐỂ KẾT NỐI
    if (client.connect(clientId.c_str(), mqtt_user, mqtt_pass)) { 
      Serial.println("connected");
      client.subscribe(MQTT_CMD_TOPIC);
      Serial.print("Subscribed to: ");
      Serial.println(MQTT_CMD_TOPIC);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" Try again in 5 seconds");
      delay(5000);
    }
  }
}

// ----------------------------------------------------
// 4. SETUP VÀ LOOP
// ----------------------------------------------------
void setup() {
  Serial.begin(115200); 
  delay(100);
  Serial.println("\nĐang khởi động Robot MQTT...");
  Serial.println("Bắt đầu AutoConnect...");
  // 🚨 BƯỚC BẢO MẬT: Bỏ qua kiểm tra chứng chỉ (cho mục đích thử nghiệm)
   espClient.setInsecure(); 
  
  // WiFi.begin(ssid, password);
 // Nếu không thể kết nối hoặc chưa lưu, thiết bị sẽ tạo AP (Tên: "ROBOT_SETUP", Mật khẩu: "12345678")
  if (!wifiManager.autoConnect("ROBOT_SETUP", "12345678")) {
    Serial.println("Kết nối thất bại và hết thời gian chờ.");
    delay(3000);
    // Nếu thất bại, khởi động lại để thử lại
    ESP.restart(); 
    delay(5000);
  }
  Serial.println("\nWiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // Cấu hình MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  // Gọi reconnect để thiết lập kết nối MQTT lần đầu
  reconnect();
}

void loop() {
  if(WiFi.status() == WL_CONNECTED){
    if (!client.connected()) {
      reconnect(); // Kết nối lại nếu bị ngắt
    }
    client.loop(); // Duy trì kết nối và xử lý thông điệp đến
<<<<<<< HEAD

    // --- ĐOẠN CODE MỚI: Gửi dữ liệu định kỳ (Gas, Speed, Mode) ---
    unsigned long now = millis();
    if (now - lastMsg > interval) {
      lastMsg = now;
      
      // 1. Đọc cảm biến Gas từ chân A0 (Analog)
      int gasValue = analogRead(A0);
      
      // 2. Gửi dữ liệu lên MQTT (Dùng giá trị giả định hoặc biến toàn cục cho speed/dir nếu cần)
      // Ở đây ta tạm thời gửi trạng thái 'S' (Stop) hoặc cần lưu trạng thái hiện tại vào biến toàn cục.
      // Để đơn giản, ta chỉ gửi gas cập nhật, các cái khác có thể để mặc định hoặc cần cơ chế sync tốt hơn.
      // Tuy nhiên, hàm publishStatus ở trên đang nhận command/speed.
      
      // Để tốt nhất, bạn nên tạo biến toàn cục lưu currentSpeed, currentDirection.
      // Nhưng theo yêu cầu nhanh, mình sẽ gửi kèm gasValue.
      
      // Sửa lại hàm publishStatus để nhận thêm gasValue (đã sửa ở trên)
      // Gọi hàm với giá trị hiện tại (cần lưu biến toàn cục để chính xác, nhưng tạm thời để 0/S hoặc đọc từ biến nếu có)
      // Do code cũ chưa có biến toàn cục lưu state, ta sẽ gửi msg heartbeat.
      
      publishStatus("Hb", 0, gasValue); // Hb = Heartbeat
    }

=======
>>>>>>> b91306d14b940347b7ce30a33f2c94898781f811
  } else {
    // Thử kết nối lại Wi-Fi mỗi 10 giây nếu bị mất kết nối
    if (millis() % 10000 == 0) {
      wifiManager.setDebugOutput(true);
      wifiManager.autoConnect("ROBOT_SETUP", "12345678");
    }
  }
}