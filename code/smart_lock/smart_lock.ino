#include <ArduinoJson.h>
#include <EEPROM.h>
#include "board.h"

int baseVersion = 4;

Servo servo;
Servo clutch;

int counter = 0;

//#############################################################################################################################################
//###                                                                   ###
//###                             CONFIGURATION                         ###
//###                                                                   ###
//#############################################################################################################################################

#ifndef STASSID
#define STASSID "*************" // CHANGE THIS
#define STAPSK  "*************" // CHANGE THIS
#endif

const int numberOfTurnsRequired = 1; // CHANGE THIS
bool previousStateWasHigh = true;

// HomeKey / native Apple Home support with a HomeKey-ESP32 reader, see homekey/README.md
// 0 = standalone, HTTP API + button only
// 1 = built-in broker, the reader connects directly to this lock (no Raspberry Pi or server needed)
// 2 = external MQTT broker (Mosquitto, Home Assistant, ...)
#define HOMEKEY_MODE 1 // CHANGE THIS
#define HOMEKEY_TOPIC_PREFIX "smartlock-reader" // MQTT Client ID configured on the reader
#define MQTT_HOST "192.168.1.10" // only used in mode 2
#define MQTT_PORT 1883
#define MQTT_USER "" // optional, must match the reader's MQTT settings
#define MQTT_PASS ""

// Clutch servo (3D printed case/clutch): the key / thumb-turn turns freely while the lock is idle
// Set to 0 for the original direct drive build without the clutch
#define USE_CLUTCH 1 // CHANGE THIS
#define CLUTCH_OPEN_ANGLE 75     // CALIBRATE: fork lifted, dogs apart
#define CLUTCH_CLOSED_ANGLE 105  // CALIBRATE: fork pressed down, a few degrees past contact so it keeps pushing
#define CLUTCH_SETTLE_MS 350     // time for the SG90 to move
#define CLUTCH_RELIEF_MS 40      // short reverse of the main servo so the dogs are not loaded when releasing

#define SETTINGS_MAGIC 0x5D10C3

struct { 
  // CALIBRATE
  int TimeToLock = 1000;
  int TimeToUnlock = 1000;
  uint32_t magic = SETTINGS_MAGIC;
} settings;

#include "homekey_bridge.h"

//#############################################################################################################################################
//###                                                                   ###
//###                             LOCK                                  ###
//###                                                                   ###
//#############################################################################################################################################
bool locked = true;

// A movement is a small state machine so the loop never blocks:
// engage the clutch -> run the servo -> back off a little -> release the clutch -> settle
enum Motion { IDLE, ENGAGING, MOVING, RELIEVING, RELEASING };
Motion motion = IDLE;
bool motionToLocked = true;
unsigned long motionStartTime = 0;

void setClutch(bool closed) {
#if USE_CLUTCH
  if (!clutch.attached()) clutch.attach(CLUTCHPIN);
  clutch.write(closed ? CLUTCH_CLOSED_ANGLE : CLUTCH_OPEN_ANGLE);
#endif
}

void servosOff() {
  servo.detach();
  boardServoPinIdle(SERVOPIN);
#if USE_CLUTCH
  clutch.detach();
  boardServoPinIdle(CLUTCHPIN);
#endif
  boardServoPower(false);
}

void startMotion(bool toLocked) {
  if (motion != IDLE || locked == toLocked) return;
  boardKeepAwake(true);
  boardServoPower(true);
  setClutch(true);
  motionToLocked = toLocked;
  motionStartTime = millis();
  motion = ENGAGING;
}

void lock() { startMotion(true); }

void unlock() { startMotion(false); }

bool motionInProgress() { return motion != IDLE; }

void handleLockUnlock() {
  unsigned long elapsed = millis() - motionStartTime;
  unsigned long runTime = motionToLocked ? settings.TimeToLock : settings.TimeToUnlock;

  switch (motion) {
    case IDLE:
      break;

    case ENGAGING:
      if (!USE_CLUTCH || elapsed >= CLUTCH_SETTLE_MS) {
        servo.attach(SERVOPIN);
        servo.write(motionToLocked ? 180 : 1);
        motionStartTime = millis();
        motion = MOVING;
      }
      break;

    case MOVING:
      if (elapsed >= runTime) {
        servo.write(motionToLocked ? 1 : 180);
        motionStartTime = millis();
        motion = RELIEVING;
      }
      break;

    case RELIEVING:
      if (!USE_CLUTCH || elapsed >= CLUTCH_RELIEF_MS) {
        servo.detach();
        boardServoPinIdle(SERVOPIN);
        setClutch(false);
        locked = motionToLocked;

        // Completed the movement, reset every state related variable
        counter = 0;
        previousStateWasHigh = false;
        homekeyReportState(locked);

        motionStartTime = millis();
        motion = RELEASING;
      }
      break;

    case RELEASING:
      // The thumb-turn may still swing back a little, the sensor is ignored for another second
      if (elapsed >= CLUTCH_SETTLE_MS + 1000) {
        servosOff();
        boardKeepAwake(false);
        motion = IDLE;
      }
      break;
  }
}

//#############################################################################################################################################
//###                                                                   ###
//###                             WEBSERVER                             ###
//###                                                                   ###
//#############################################################################################################################################

const char* ssid = STASSID;
const char* password = STAPSK;

LockWebServer server(80);

void handleNotFound() {
  String message = "File Not Found\n\n";
  message += "URI: ";
  message += server.uri();
  message += "\nMethod: ";
  message += (server.method() == HTTP_GET) ? "GET" : "POST";
  message += "\nArguments: ";
  message += server.args();
  message += "\n";
  for (uint8_t i = 0; i < server.args(); i++) {
    message += " " + server.argName(i) + ": " + server.arg(i) + "\n";
  }
  server.send(404, "text/plain", message);
}

void handleStatus() {
  char rsp[255];
  sprintf(rsp, "{\"state\":\"%s\",\"homekey\":%s,\"battery\":%d}", locked ? "locked" : "unlocked", homekeyConnected() ? "true" : "false", boardBatteryPercent());

  server.send(200, "application/json", rsp);
}

void handleUpdate() {
  JsonDocument newjson;
  DeserializationError error = deserializeJson(newjson, server.arg("plain"));
  String state = newjson["state"];
  if (state == "") {
    int args = server.args();
    for (uint8_t i = 0; i < server.args(); i++) {
      String argName = server.argName(i);
      argName.toLowerCase();

      if (argName.equals("state")) {
        state = server.arg(i);
      }
    }

  }

  Serial.println(state);

  if (state != "null") {
    if (state == "locked") {
      if (!locked) {
        lock();

        char rsp[255];
        sprintf(rsp, "{\"success\":\"true\"}");
        server.send(200, "application/json", rsp);
      } else {
        char rsp[255];
        sprintf(rsp, "{\"success\":\"false\",\"error\":\"already locked\"}");
        server.send(200, "application/json", rsp);
      }
    }
    else if (state == "unlocked") {
      if (locked) {
        unlock();

        char rsp[255];
        sprintf(rsp, "{\"success\":\"true\"}");
        server.send(200, "application/json", rsp);
      } else {
        char rsp[255];
        sprintf(rsp, "{\"success\":\"false\",\"error\":\"already unlocked\"}");
        server.send(200, "application/json", rsp);
      }
      
    }
    else {
      server.send(400, "text/plain", "INVALID POST REQUEST");
    }
  } else {
    server.send(400, "text/plain", "EMPTY POST REQUEST");
  }
}

//#############################################################################################################################################
//###                                                                   ###
//###                               SENSOR                              ###
//###                                                                   ###
//#############################################################################################################################################

void handleUpdateLockState() {
  if (digitalRead(SENSOR) == LOW && previousStateWasHigh) {
    counter++;
    previousStateWasHigh = false;
    delay(500);
  } else if (digitalRead(SENSOR) == HIGH) {
    previousStateWasHigh = true;
  }

  if (counter == numberOfTurnsRequired) {
    counter = 0;
    if (locked) {
      locked = false;
      Serial.println("unlocked manually");
    } else {
      locked = true;
      Serial.println("locked manually");
    }
    homekeyReportState(locked);
  }
}

//#############################################################################################################################################
//###                                                                   ###
//###                             BUTTON                                ###
//###                                                                   ###
//#############################################################################################################################################

void handleButton() {
  if (digitalRead(BUTTON) == LOW) {
    if (locked) {
      unlock();
      Serial.println("unlocked using the button");
    } else {
      lock();
      Serial.println("locked using the button");
    }
    delay(500);
  }
}

//#############################################################################################################################################
//###                                                                   ###
//###                             WIFI                                  ###
//###                                                                   ###
//#############################################################################################################################################

void initWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.println("");

  // Wait for connection
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to ");
  Serial.println(ssid);
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

//#############################################################################################################################################
//###                                                                   ###
//###                             LED                                   ###
//###                                                                   ###
//#############################################################################################################################################

void handleLED() {
#if LED_ALWAYS_ON_WHEN_UNLOCKED
  if (!locked) {
    digitalWrite(RINGLED, HIGH);
  } else {
    digitalWrite(RINGLED, LOW);
  }
#else
  // Battery: light up for a few seconds after every change instead
  static bool lastLocked = locked;
  static unsigned long changedAt = 0;
  if (locked != lastLocked) {
    lastLocked = locked;
    changedAt = millis();
  }
  digitalWrite(RINGLED, (changedAt != 0 && millis() - changedAt < 3000) ? HIGH : LOW);
#endif
}

//#############################################################################################################################################
//###                                                                   ###
//###                             BATTERY                               ###
//###                                                                   ###
//#############################################################################################################################################

void handleBattery() {
#if HAS_BATTERY
  static unsigned long lastReport = 0;
  if (lastReport == 0 || millis() - lastReport > 30UL * 60 * 1000) {
    lastReport = millis();
    int percent = boardBatteryPercent();
    Serial.println("Battery: " + String(boardBatteryMillivolts()) + " mV, " + String(percent) + " %");
    homekeyReportBattery(percent);
  }
#endif
}

void flashLED() {
  digitalWrite(RINGLED, HIGH);
  delay(500);
  digitalWrite(RINGLED, LOW);
  delay(500);
  digitalWrite(RINGLED, HIGH);
  delay(500);
  digitalWrite(RINGLED, LOW);
  delay(500);
  digitalWrite(RINGLED, HIGH);
  delay(500);
  digitalWrite(RINGLED, LOW);
}

//#############################################################################################################################################
//###                                                                   ###
//###                             CALIBRATION                           ###
//###                                                                   ###
//#############################################################################################################################################

void calibrate() {
  Serial.println("Starting calibration...");
  flashLED();

  while (digitalRead(BUTTON) == LOW) {
    delay(50);
  }

  boardKeepAwake(true);
  boardServoPower(true);
  setClutch(true);
  delay(CLUTCH_SETTLE_MS);

  unsigned long startTime = millis();
  servo.attach(SERVOPIN);
  servo.write(180);
  while (digitalRead(BUTTON) == HIGH) {
    delay(50);
  }
  servo.detach();
  settings.TimeToLock = millis() - startTime - 1000;
  if (settings.TimeToLock >= 100 && settings.TimeToLock <= 10000) Serial.println("New lock time: " + String(settings.TimeToLock) + " ms");
  else {
    settings.TimeToLock = 5000;
    Serial.println("Invalid lock time, resetting back to default: 5000 ms");
  }

  flashLED();

  startTime = millis();
  servo.attach(SERVOPIN);
  servo.write(1);
  while (digitalRead(BUTTON) == HIGH) {
    delay(50);
  }
  servo.detach();
  settings.TimeToUnlock = millis() - startTime - 1000;
  if (settings.TimeToUnlock >= 100 && settings.TimeToUnlock <= 10000) Serial.println("New unlock time: " + String(settings.TimeToUnlock) + " ms");
  else {
    settings.TimeToUnlock = 5000;
    Serial.println("Invalid unlock time, resetting back to default: 5000 ms");
  }

  servosOff();
  boardKeepAwake(false);

  EEPROM.put(0, settings); //write data to array in ram 
  EEPROM.commit();  //write data from ram to flash memory. Do nothing if there are no changes to EEPROM data in ram
  
  flashLED();
}

//#############################################################################################################################################
//###                                                                   ###
//###                             HOMEKEY                               ###
//###                                                                   ###
//#############################################################################################################################################

void onHomeKeyCommand(bool shouldLock) {
  if (shouldLock && !locked) lock();
  else if (!shouldLock && locked) unlock();
  else homekeyReportState(locked); // already there, let the reader settle
}

//#############################################################################################################################################
//###                                                                   ###
//###                             MAIN                                  ###
//###                                                                   ###
//#############################################################################################################################################

void setup() {
  boardBegin();
  pinMode(SENSOR, INPUT_PULLUP);
  pinMode(BUTTON, INPUT_PULLUP);
  pinMode(RINGLED, OUTPUT);
#if USE_CLUTCH && !defined(ESP32)
  Serial.begin(9600, SERIAL_8N1, SERIAL_TX_ONLY); // RX is the clutch servo signal
#else
  Serial.begin(9600);
#endif
  Serial.println("Smart lock, board " BOARD_NAME);

  initWifi();
  boardLowPower();

  server.on("/", HTTP_GET, handleStatus);
  server.on("/", HTTP_POST, handleUpdate);
  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("HTTP server started");

  if (MDNS.begin("smartlock")) {
    Serial.println("MDNS responder started");
  }

  EEPROM.begin(sizeof(settings));
  EEPROM.get(0, settings); //read data from array in ram and cast it into struct called settings
  if (settings.magic != SETTINGS_MAGIC) {
    // Never calibrated, the flash holds garbage
    settings.TimeToLock = 1000;
    settings.TimeToUnlock = 1000;
    settings.magic = SETTINGS_MAGIC;
  }
  Serial.println("Current lock time: " + String(settings.TimeToLock) + " ms");
  Serial.println("Current unlock time: " + String(settings.TimeToUnlock) + " ms");

  delay(3000);
  if (digitalRead(BUTTON) == LOW) {
    calibrate();
  }

  homekeyBegin(onHomeKeyCommand);
  homekeyReportState(locked);
}

void loop() {
  boardMdnsUpdate();
  handleLockUnlock();
  if (!motionInProgress()) {
    server.handleClient();
    homekeyLoop();
    handleUpdateLockState();
    handleButton();
    handleBattery();
  }
  handleLED();
  if (LOOP_IDLE_DELAY_MS > 0 && !motionInProgress()) delay(LOOP_IDLE_DELAY_MS);
}
