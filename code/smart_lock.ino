#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include <ESP8266mDNS.h>
#include <EEPROM.h>

int baseVersion = 3;

#define SERVOPIN 12
#define SENSOR 13
#define BUTTON 4
#define RINGLED 5

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

const int numberOfTurnsRequired = 1; // CHANGE THIS
bool previousStateWasHigh = true;

struct { 
  // CALIBRATE
  int TimeToLock = 1000;
  int TimeToUnlock = 1000;
} settings;

//#############################################################################################################################################
//###                                                                   ###
//###                             LOCK                                  ###
//###                                                                   ###
//#############################################################################################################################################
bool locked = true;
bool lockingInProgress = false;
bool unlockingInProgress = false;
unsigned long lockUnlockStartTime = 0;

void lock() {
  if (!locked && !lockingInProgress) {
    servo.attach(SERVOPIN);
    servo.write(180);
    lockUnlockStartTime = millis();
    lockingInProgress = true;
  }
}

void unlock() {
  if (locked && !unlockingInProgress) {
    servo.attach(SERVOPIN);
    servo.write(1);
    lockUnlockStartTime = millis();
    unlockingInProgress = true;
  }
}

void handleLockUnlock() {
  if (lockingInProgress && millis() - lockUnlockStartTime >= settings.TimeToLock) {
    servo.detach();
    locked = true;

    // Completed the unlock, reset every state related variable
    counter = 0;
    previousStateWasHigh = false;
    
    
    if (lockingInProgress && millis() - lockUnlockStartTime >= settings.TimeToLock + 1000) lockingInProgress = false;
  }
  
  if (unlockingInProgress && millis() - lockUnlockStartTime >= settings.TimeToUnlock) {
    servo.detach();
    locked = false;

    // Completed the unlock, reset every state related variable
    counter = 0;
    previousStateWasHigh = false;
    
    if (unlockingInProgress && millis() - lockUnlockStartTime >= settings.TimeToUnlock + 1000) unlockingInProgress = false;
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
  sprintf(rsp, "{\"state\":\"%s\"}", locked ? "locked" : "unlocked");

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

    server.send(400, "text/plain", "INVALID POST REQUEST");
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

void calibrate() {
  Serial.println("Starting calibration...");
  flashLED();

  while (digitalRead(BUTTON) == LOW) {
    delay(50);
  }

  int startTime = millis();
  servo.attach(SERVOPIN);
  servo.write(180);
  while (digitalRead(BUTTON) == HIGH) {
    delay(50);
  }
  servo.detach();
  settings.TimeToLock = millis() - startTime - 1000;
  if (settings.TimeToLock >= 1 && settings.TimeToLock <= 10) Serial.println("New lock time: " + String(settings.TimeToLock) + " ms");
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
  if (settings.TimeToUnlock >= 1 && settings.TimeToUnlock <= 10) Serial.println("New unlock time: " + String(settings.TimeToUnlock) + " ms");
  else {
    settings.TimeToUnlock = 5000;
    Serial.println("Invalid unlock time, resetting back to default: 5000 ms");
  }

  EEPROM.put(0, settings); //write data to array in ram 
  EEPROM.commit();  //write data from ram to flash memory. Do nothing if there are no changes to EEPROM data in ram
  
  flashLED();
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
  Serial.begin(9600);

  initWifi();

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
  Serial.println("Current lock time: " + String(settings.TimeToLock) + " ms");
  Serial.println("Current unlock time: " + String(settings.TimeToUnlock) + " ms");

  delay(3000);
  if (digitalRead(BUTTON) == LOW) {
    calibrate();
  }
}

void loop() {
  MDNS.update();
  handleLockUnlock();
  if (!lockingInProgress && !unlockingInProgress) {
    server.handleClient();
    handleUpdateLockState();
    handleButton();
  }
  handleLED();
}
