/*
 * Autonomous Smart Warehouse Robot
 * ESP32 - Arduino IDE
 * 
 * HARDWARE CONNECTIONS:
 * Motors (L298N):
 *   IN1 = GPIO 27, IN2 = GPIO 26 (Left Motor)
 *   IN3 = GPIO 25, IN4 = GPIO 33 (Right Motor)
 *   ENA = GPIO 14 (Left PWM), ENB = GPIO 12 (Right PWM)
 * 
 * Ultrasonic (HC-SR04):
 *   TRIG = GPIO 5, ECHO = GPIO 18
 * 
 * Touch Sensor:
 *   OUT = GPIO 4 (or use ESP32 capacitive touch on T0=GPIO4)
 */

#include <WiFi.h>
#include <HTTPClient.h>

// ─── WiFi Config ──────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";       // ← Change this
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // ← Change this
const char* LAPTOP_IP     = "192.168.1.100";         // ← Change to your laptop IP
const int   FLASK_PORT    = 5000;

// ─── Motor Pins ───────────────────────────────────────────────────────────────
#define IN1 27
#define IN2 26
#define IN3 25
#define IN4 33
#define ENA 14
#define ENB 12

// ─── Ultrasonic Pins ─────────────────────────────────────────────────────────
#define TRIG_PIN 5
#define ECHO_PIN 18

// ─── Touch Sensor Pin ────────────────────────────────────────────────────────
#define TOUCH_PIN 4   // GPIO4 = Touch0 on ESP32

// ─── PWM Config ──────────────────────────────────────────────────────────────
#define PWM_FREQ      1000
#define PWM_RES       8
#define MOTOR_SPEED   180   // 0–255
#define TURN_SPEED    150

// ─── Timing ──────────────────────────────────────────────────────────────────
#define FORWARD_MS    2000   // ms to move forward between zones
#define TURN_MS       650    // ms for 90° turn (calibrate for your robot)
#define STOP_MS       500    // pause after arriving at zone

// ─── Obstacle threshold ──────────────────────────────────────────────────────
#define OBSTACLE_CM   15

// ─── State machine ───────────────────────────────────────────────────────────
enum State { WAITING, MOVING_TO_ZONE, AT_ZONE, DETECTING, DONE };
State robotState = WAITING;
int   currentZone = 0;

// ─── Setup ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(500);

  // Motor pins
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);

  // PWM channels
  ledcSetup(0, PWM_FREQ, PWM_RES); ledcAttachPin(ENA, 0);
  ledcSetup(1, PWM_FREQ, PWM_RES); ledcAttachPin(ENB, 1);

  // Ultrasonic
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Touch pin (digital input with pullup as fallback)
  pinMode(TOUCH_PIN, INPUT);

  stopMotors();

  // Connect WiFi
  connectWiFi();

  Serial.println("=== Warehouse Robot Ready ===");
  Serial.println("Touch sensor to START");
}

// ─── Main Loop ───────────────────────────────────────────────────────────────
void loop() {
  switch (robotState) {

    case WAITING:
      waitForTouch();
      break;

    case MOVING_TO_ZONE:
      moveToNextZone();
      break;

    case AT_ZONE:
      handleZoneArrival();
      break;

    case DETECTING:
      // Detection is blocking in handleZoneArrival; this state is transitional
      break;

    case DONE:
      Serial.println("All zones complete. System idle.");
      stopMotors();
      delay(5000);
      // Reset for next run
      currentZone = 0;
      robotState = WAITING;
      break;
  }
}

// ─── WiFi Connection ─────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("ESP32 IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi FAILED. Check SSID/Password.");
  }
}

// ─── Wait for Touch ──────────────────────────────────────────────────────────
void waitForTouch() {
  // ESP32 capacitive touch: touchRead returns LOW value when touched
  int touchVal = touchRead(TOUCH_PIN);
  Serial.print("Touch value: "); Serial.println(touchVal);

  if (touchVal < 40) {  // Threshold: <40 = touched (tune as needed)
    Serial.println("TOUCH detected! Starting robot...");
    delay(500);
    currentZone = 0;
    robotState = MOVING_TO_ZONE;
  }
  delay(100);
}

// ─── Move to Next Zone ───────────────────────────────────────────────────────
void moveToNextZone() {
  currentZone++;
  if (currentZone > 3) {
    robotState = DONE;
    return;
  }

  Serial.print("Moving to Zone "); Serial.println(currentZone);

  if (currentZone == 1) {
    // First zone: move forward
    moveForwardTimed(FORWARD_MS);
  } else {
    // Subsequent zones: turn right then move forward
    turnRight(TURN_MS);
    delay(200);
    moveForwardTimed(FORWARD_MS);
  }

  stopMotors();
  delay(STOP_MS);
  robotState = AT_ZONE;
}

// ─── Handle Zone Arrival ─────────────────────────────────────────────────────
void handleZoneArrival() {
  Serial.print("=== Arrived at Zone "); Serial.print(currentZone); Serial.println(" ===");
  stopMotors();

  // Send detect request to Python server
  String result = sendDetectRequest(currentZone);
  Serial.print("Detection result: "); Serial.println(result);

  delay(1500);  // Wait for detection and dashboard update

  // Continue to next zone
  robotState = MOVING_TO_ZONE;
}

// ─── HTTP Request to Python Server ───────────────────────────────────────────
String sendDetectRequest(int zone) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected! Reconnecting...");
    connectWiFi();
  }

  HTTPClient http;
  String url = "http://" + String(LAPTOP_IP) + ":" + String(FLASK_PORT) +
               "/detect?zone=" + String(zone);

  Serial.print("GET "); Serial.println(url);

  http.begin(url);
  http.setTimeout(8000);  // 8 second timeout
  int httpCode = http.GET();

  String response = "";
  if (httpCode == 200) {
    response = http.getString();
    Serial.print("Response: "); Serial.println(response);
  } else {
    Serial.print("HTTP Error: "); Serial.println(httpCode);
    response = "{\"zone\":" + String(zone) + ",\"status\":\"ERROR\"}";
  }

  http.end();
  return response;
}

// ─── Ultrasonic Distance ─────────────────────────────────────────────────────
float getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);  // 30ms timeout
  float distance = (duration * 0.0343) / 2.0;
  return distance;
}

bool obstacleDetected() {
  float d = getDistance();
  Serial.print("Distance: "); Serial.print(d); Serial.println(" cm");
  return (d > 0 && d < OBSTACLE_CM);
}

// ─── Motor Control ───────────────────────────────────────────────────────────
void moveForward() {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(0, MOTOR_SPEED);
  ledcWrite(1, MOTOR_SPEED);
}

void moveBackward() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  ledcWrite(0, MOTOR_SPEED);
  ledcWrite(1, MOTOR_SPEED);
}

void turnRight(int ms) {
  // Left wheel forward, right wheel backward
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);  digitalWrite(IN4, HIGH);
  ledcWrite(0, TURN_SPEED);
  ledcWrite(1, TURN_SPEED);
  delay(ms);
  stopMotors();
}

void turnLeft(int ms) {
  // Left wheel backward, right wheel forward
  digitalWrite(IN1, LOW);  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  ledcWrite(0, TURN_SPEED);
  ledcWrite(1, TURN_SPEED);
  delay(ms);
  stopMotors();
}

void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  ledcWrite(0, 0);
  ledcWrite(1, 0);
}

// ─── Move Forward With Obstacle Check ────────────────────────────────────────
void moveForwardTimed(int ms) {
  unsigned long startTime = millis();
  moveForward();

  while (millis() - startTime < ms) {
    if (obstacleDetected()) {
      Serial.println("OBSTACLE! Stopping...");
      stopMotors();
      // Wait until obstacle clears
      while (obstacleDetected()) {
        delay(200);
      }
      Serial.println("Path clear, resuming...");
      moveForward();
    }
    delay(50);
  }

  stopMotors();
}
