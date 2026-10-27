#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include <ESP8266mDNS.h>
#include <EEPROM.h>
#include "motion.h"

int baseVersion = 4;

#define SERVOPIN 12
#define SENSOR 13
#define BUTTON 4
#define RINGLED 5
#define HUBSENSOR 3 // hall switch on the servo hub, RX pin of the programming header (Serial runs TX only)

Servo servo;

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

// Single servo with the spiral coupling (3D printed case/spiral): the key turns freely while the lock is idle,
// a hall switch on the hub tells the firmware how far the servo has backed off. Nothing to calibrate.

// No manual calibration: the first lock and the first unlock run until the thumb-turn stops and learn the number of
// turns (counted by the reed sensor). Hold the side button while powering on to forget them and learn again.
#define SETTINGS_MAGIC 0x5D10C4

struct {
  MotionLearned learned;
  uint32_t magic = SETTINGS_MAGIC;
} settings;

#include "homekey_bridge.h"

//#############################################################################################################################################
//###                                                                   ###
//###                             LOCK                                  ###
//###                                                                   ###
//#############################################################################################################################################
bool locked = true;
bool jammed = false;

MotionController motion;

void runServo(int direction) {
  if (direction == 0) {
    servo.detach();
    return;
  }
  if (!servo.attached()) servo.attach(SERVOPIN);
  servo.write(direction > 0 ? 180 : 1);
}

// The V3 board powers the servo all the time
void servoPower(bool) {}

bool reedActive() { return digitalRead(SENSOR) == LOW; }

bool hubActive() { return digitalRead(HUBSENSOR) == LOW; }

void startMotion(bool toLocked) {
  if (motion.busy() || (locked == toLocked && !jammed)) return;
  if (motion.start(toLocked, millis(), reedActive(), hubActive()) && motion.learning()) {
    Serial.println(String("Learning: turning until the thumb-turn stops (") + (toLocked ? "lock" : "unlock") + ")");
  }
}

void lock() { startMotion(true); }

void unlock() { startMotion(false); }

bool motionInProgress() { return motion.busy(); }

void handleLockUnlock() {
  if (!motion.busy()) return;
  MotionResult result = motion.update(millis(), reedActive(), hubActive());

  if (result == MOTION_DONE) {
    locked = motion.targetLocked();
    jammed = false;
    Serial.println(String(locked ? "locked" : "unlocked") + " after " + String(motion.arrivals()) + " turn(s)");
    homekeyReportState(locked);
  } else if (result == MOTION_JAMMED) {
    // Not where it should be: report it, a lock that didn't lock must not look locked
    jammed = true;
    locked = false;
    Serial.println("JAMMED after " + String(motion.arrivals()) + " turn(s), is the door handle lifted?");
    homekeyReportJammed();
  }

  if (result == MOTION_DONE || result == MOTION_JAMMED) {
    // Completed the movement, reset every state related variable
    counter = 0;
    previousStateWasHigh = false;
    if (motion.learnedChanged) {
      motion.learnedChanged = false;
      saveSettings();
      Serial.println("Learned: " + String(settings.learned.turnsToLock) + " turn(s) to lock, " + String(settings.learned.turnsToUnlock) + " to unlock, " + String(settings.learned.revolutionMs) + " ms per turn");
    }
  }
}

//#############################################################################################################################################
//###                                                                   ###
//###                             WEBSERVER                             ###
//###                                                                   ###
//#############################################################################################################################################

const char* ssid = STASSID;
const char* password = STAPSK;

ESP8266WebServer server(80);

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
  sprintf(rsp, "{\"state\":\"%s\",\"homekey\":%s}", jammed ? "jammed" : (locked ? "locked" : "unlocked"), homekeyConnected() ? "true" : "false");

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
      if (locked || jammed) {
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

  if (counter >= motion.manualTurns()) {
    counter = 0;
    jammed = false;
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
  if (!locked) {
    digitalWrite(RINGLED, HIGH);
  } else {
    digitalWrite(RINGLED, LOW);
  }
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

void saveSettings() {
  settings.learned = motion.learned;
  EEPROM.put(0, settings); //write data to array in ram 
  EEPROM.commit();  //write data from ram to flash memory. Do nothing if there are no changes to EEPROM data in ram
}

// Holding the side button at power on: forget the learned turns, the next lock and unlock learn them again
void relearn() {
  Serial.println("Forgetting the learned turns, the next lock and unlock will learn them again");
  flashLED();
  motion.forget();
  saveSettings();
  while (digitalRead(BUTTON) == LOW) {
    delay(50);
  }
}

//#############################################################################################################################################
//###                                                                   ###
//###                             HOMEKEY                               ###
//###                                                                   ###
//#############################################################################################################################################

void onHomeKeyCommand(bool shouldLock) {
  if (jammed || shouldLock != locked) startMotion(shouldLock);
  else homekeyReportState(locked); // already there, let the reader settle
}

//#############################################################################################################################################
//###                                                                   ###
//###                             MAIN                                  ###
//###                                                                   ###
//#############################################################################################################################################

void setup() {
  pinMode(SENSOR, INPUT_PULLUP);
  pinMode(BUTTON, INPUT_PULLUP);
  pinMode(RINGLED, OUTPUT);
  Serial.begin(9600, SERIAL_8N1, SERIAL_TX_ONLY); // RX is the hub sensor
  pinMode(HUBSENSOR, INPUT_PULLUP);

  initWifi();

  server.on("/", HTTP_GET, handleStatus);
  server.on("/", HTTP_POST, handleUpdate);
  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("HTTP server started");

  if (MDNS.begin("smartlock")) {
    Serial.println("MDNS responder started");
  }

  MotionHardware hardware = {runServo, servoPower};
  motion.begin(hardware);

  EEPROM.begin(sizeof(settings));
  EEPROM.get(0, settings); //read data from array in ram and cast it into struct called settings
  if (settings.magic != SETTINGS_MAGIC) {
    // Nothing learned yet (or settings from an older firmware)
    settings.learned = MotionLearned();
    settings.magic = SETTINGS_MAGIC;
  }
  motion.learned = settings.learned;
  if (motion.learned.turnsToLock == 0 || motion.learned.turnsToUnlock == 0) {
    Serial.println("Turns not learned yet, the first lock and unlock will learn them");
  } else {
    Serial.println("Learned: " + String(motion.learned.turnsToLock) + " turn(s) to lock, " + String(motion.learned.turnsToUnlock) + " to unlock");
  }

  delay(3000);
  if (digitalRead(BUTTON) == LOW) {
    relearn();
  }

  homekeyBegin(onHomeKeyCommand);
  homekeyReportState(locked);
}

void loop() {
  MDNS.update();
  handleLockUnlock();
  if (!motionInProgress()) {
    server.handleClient();
    homekeyLoop();
    handleUpdateLockState();
    handleButton();
  }
  handleLED();
}
