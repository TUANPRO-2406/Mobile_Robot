#include <ArduinoJson.h>

// --- Cấu hình Chân Động Cơ (L298N) ---
const int enA = 6;  // PWM A
const int in1 = 8;
const int in2 = 7;

const int enB = 11; // PWM B
const int in3 = 12;
const int in4 = 13;

// --- Cấu hình Encoder (4 Bánh) ---
// Sử dụng các chân Digital còn trống.
// Lưu ý: Để đọc chính xác tốc độ cao cần ngắt (Interrupt).
// Arduino Uno chỉ có ngắt trên chân 2, 3.
// Ở đây dùng polling hoặc PinChangeInterrupt nếu cần.
// Để đơn giản cho demo, ta dùng digitalRead trong loop (tốc độ thấp) hoặc giả lập.
const int ENC1_PIN = 2;
const int ENC2_PIN = 3;
#include <ArduinoJson.h>

// --- Pin Definitions ---
// L298N Motor Driver
const int ENA = 6;
const int IN1 = 8;
const int IN2 = 7;
const int IN3 = 12;
const int IN4 = 13;
const int ENB = 11;

// Encoders
const int ENC1_A = 2; // Interrupt
const int ENC2_A = 3; // Interrupt
const int ENC3_A = 4;
const int ENC4_A = 5;

// Sensors
const int GAS_PIN = A0;
const int TRIG_PIN = 9;
const int ECHO_PIN = 10;

// --- Variables ---
volatile long count1 = 0;
volatile long count2 = 0;
long count3 = 0;
long count4 = 0;
int lastEnc3 = 0;
int lastEnc4 = 0;

unsigned long lastTime = 0;
unsigned long lastCmdTime = 0;
const unsigned long SEND_INTERVAL = 200; // 200ms
const unsigned long WATCHDOG_TIMEOUT = 2000; // 2s stop if no command

String currentMode = "MANUAL"; // MANUAL or AUTO
String currentCommand = "STOP";
int currentSpeed = 0;

void setup() {
  Serial.begin(9600); // Comm with ESP8266

  // Motor Pins
  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENB, OUTPUT);

  // Encoder Pins
  pinMode(ENC1_A, INPUT_PULLUP);
  pinMode(ENC2_A, INPUT_PULLUP);
  pinMode(ENC3_A, INPUT_PULLUP);
  pinMode(ENC4_A, INPUT_PULLUP);

  // Sensor Pins
  pinMode(GAS_PIN, INPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Interrupts
  attachInterrupt(digitalPinToInterrupt(ENC1_A), isr1, RISING);
  attachInterrupt(digitalPinToInterrupt(ENC2_A), isr2, RISING);

  stopMotors();
}

void loop() {
  // 1. Read Sensors
  pollEncoders();
  int gasValue = analogRead(GAS_PIN);
  long distance = getDistance();

  // 2. Safety Watchdog (Only in MANUAL mode)
  if (currentMode == "MANUAL" && millis() - lastCmdTime > WATCHDOG_TIMEOUT) {
    stopMotors();
    currentCommand = "STOP";
  }

  // 3. Auto Mode Logic
  if (currentMode == "AUTO") {
    if (distance > 0 && distance < 25) { // Obstacle detected < 25cm
      stopMotors();
      delay(500);
      moveBackward(150);
      delay(1000);
      turnLeft(150);
      delay(800);
    } else {
      moveForward(150);
    }
  }

  // 4. Send Data to ESP (JSON)
  if (millis() - lastTime > SEND_INTERVAL) {
    lastTime = millis();
    
    StaticJsonDocument<200> doc;
    doc["s1"] = count1;
    doc["s2"] = count2;
    doc["s3"] = count3;
    doc["s4"] = count4;
    doc["gas"] = gasValue;
    doc["dist"] = distance;
    
    serializeJson(doc, Serial);
    Serial.println();
    
    // Reset counters for speed calculation (impulses per interval)
    count1 = 0; count2 = 0; count3 = 0; count4 = 0;
  }

  // 5. Read Commands from ESP
  if (Serial.available()) {
    String input = Serial.readStringUntil('\n');
    processCommand(input);
    lastCmdTime = millis();
  }
}

long getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // Timeout 30ms
  if (duration == 0) return 999; // No echo
  return duration * 0.034 / 2;
}

void processCommand(String input) {
  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, input);
  
  if (!error) {
    if (doc.containsKey("cmd")) {
      String cmd = doc["cmd"].as<String>();
      
      if (cmd == "AUTO_MODE") {
        currentMode = "AUTO";
      } else if (cmd == "MANUAL_MODE") {
        currentMode = "MANUAL";
        stopMotors();
      } else if (currentMode == "MANUAL") {
        currentCommand = cmd;
        // Execute manual command
        if (cmd == "FORWARD") moveForward(currentSpeed);
        else if (cmd == "BACKWARD") moveBackward(currentSpeed);
        else if (cmd == "LEFT") turnLeft(currentSpeed);
        else if (cmd == "RIGHT") turnRight(currentSpeed);
        else if (cmd == "STOP") stopMotors();
      }
    }
    
    if (doc.containsKey("spd")) {
      currentSpeed = doc["spd"];
      // Update speed immediately if moving
      if (currentMode == "MANUAL" && currentCommand != "STOP") {
         if (currentCommand == "FORWARD") moveForward(currentSpeed);
         else if (currentCommand == "BACKWARD") moveBackward(currentSpeed);
         else if (currentCommand == "LEFT") turnLeft(currentSpeed);
         else if (currentCommand == "RIGHT") turnRight(currentSpeed);
      }
    }
  }
}

// --- Interrupt Service Routines ---
void isr1() { count1++; }
void isr2() { count2++; }

// --- Polling Encoders ---
void pollEncoders() {
  int val3 = digitalRead(ENC3_A);
  int val4 = digitalRead(ENC4_A);
  if (val3 != lastEnc3 && val3 == HIGH) count3++;
  if (val4 != lastEnc4 && val4 == HIGH) count4++;
  lastEnc3 = val3;
  lastEnc4 = val4;
}

// --- Motor Control Functions ---
void moveForward(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
}

void moveBackward(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
}

void turnLeft(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
}

void turnRight(int speed) {
  analogWrite(ENA, speed);
  analogWrite(ENB, speed);
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
}

void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
}
