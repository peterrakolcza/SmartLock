#include <ESP8266WiFi.h>
#include <WiFiClient.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>
#include <RemoteDebug.h>

int baseVersion = 0;
int version = 1;

#define CURRENT A0
#define SERVOPIN 12
#define SENSOR 13
#define BUTTON 4
#define RINGLED 5

RemoteDebug Debug;

Servo servo;

int counter = 0;

//#############################################################################################################################################
//###                                                                    ###
//###                             CONFIGURATION                                    ###
//###                                                                   ###
//#############################################################################################################################################

#ifndef STASSID
#define STASSID "********" // CHANGE THIS
#define STAPSK  "********" // CHANGE THIS
#endif

const int model = 2;   // enter the model number (see below)
const int cutOff = 400;  // CHANGE THIS
const int numberOfTurnsRequired = 3; // CHANGE THIS
const int timeOutRequiredTurns = 30000; // CHANGE THIS
const int timeOutServo = 4000; // CHANGE THIS
const int minTimeToLock = 2500; // CHANGE THIS

/*
          "ACS712ELCTR-05B-T",// for model use 0
          "ACS712ELCTR-20A-T",// for model use 1
          "ACS712ELCTR-30A-T"// for model use 2
  sensitivity array is holding the sensitivy of the  ACS712
  current sensors. Do not change. All values are from page 5  of data sheet
*/
float sensitivity[] = {
  0.185,// for ACS712ELCTR-05B-T
  0.100,// for ACS712ELCTR-20A-T
  0.066// for ACS712ELCTR-30A-T

};

//#############################################################################################################################################
//###                                                                    ###
//###                             LOCK                                    ###
//###                                                                   ###
//#############################################################################################################################################
bool locked = true;

int readCurrent() {
  int current = analogRead(CURRENT);
  /*Serial.print("I: ");
    Serial.print(current);
    Serial.print(" Contact: ");
    Serial.print(digitalRead(SENSOR));
    Serial.println();*/
  debugV("Current: %d", current);
  return current;
}

void detachServo() {
  int startTime = millis();
  counter = 0;
  delay(500);
  while (true) {
    if (readCurrent() < cutOff) {
      delay(500);
      if (readCurrent() < cutOff) {
        servo.detach();
        break;
      }
    }
    else if (millis() - startTime > timeOutServo) {
      servo.detach();
      break;
    }
    delay(15);
  }
}

void lock() {
  int startTime;
  if (!locked) {
    startTime = millis();
    servo.attach(SERVOPIN);
    servo.write(180);
    detachServo();
  }

  locked = true;
}

void unlock() {
  if (locked) {
    servo.attach(SERVOPIN);
    servo.write(1);
    detachServo();
  }

  locked = false;
}

//#############################################################################################################################################
//###                                                                    ###
//###                             WEBSERVER                                    ###
//###                                                                   ###
//#############################################################################################################################################

const char* ssid = STASSID;
const char* password = STAPSK;

ESP8266WebServer server(80);

void writeHeaders() {
  server.sendHeader("Cache-Control", "no-cache");
  server.sendHeader("Version", "v" + String(baseVersion) + "." + String(version));
}

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

void handleDebug() {
  String html = ESP.getResetReason();

  writeHeaders();
  server.send(200, "text/html", html);
}

void handleStatus() {
  writeHeaders();
  char rsp[255];
  sprintf(rsp, "{\"state\":\"%s\",\"statusCode\":200,\"battery\":100}", locked ? "locked" : "unlocked");

  server.send(200, "text/plain", rsp);
}

void handleUpdate() {
  StaticJsonBuffer<200> newBuffer;
  JsonObject& newjson = newBuffer.parseObject(server.arg("plain"));
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

  if (state != "") {
    if (state == "locked") {
      lock();
      handleStatus();
    }
    else if (state == "unlocked") {
      unlock();
      handleStatus();
    }

    writeHeaders();
    server.send(500, "text/plain", "INVALID POST REQUEST");
  } else {
    writeHeaders();
    server.send(500, "text/plain", "EMPTY POST REQUEST");
  }
}

//#############################################################################################################################################
//###                                                                    ###
//###                               SENSOR                                   ###
//###                                                                   ###
//#############################################################################################################################################

void handleUpdateLockState() {
  if (digitalRead(SENSOR) == LOW) {
    counter++;
    delay(1000);
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
//###                                                                    ###
//###                               OTA                                   ###
//###                                                                   ###
//#############################################################################################################################################

void initOTA() {
  // Port defaults to 8266
  // ArduinoOTA.setPort(8266);

  // Hostname defaults to esp8266-[ChipID]
  ArduinoOTA.setHostname("smartlock");

  // No authentication by default
  // ArduinoOTA.setPassword("admin");

  // Password can be set with it's md5 value as well
  // MD5(admin) = 21232f297a57a5a743894a0e4a801fc3
  // ArduinoOTA.setPasswordHash("21232f297a57a5a743894a0e4a801fc3");

  ArduinoOTA.onStart([]() {
    String type;
    if (ArduinoOTA.getCommand() == U_FLASH) {
      type = "sketch";
    } else { // U_FS
      type = "filesystem";
    }

    // NOTE: if updating FS this would be the place to unmount FS using FS.end()
    Serial.println("Start updating " + type);
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("\nEnd");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("Progress: %u%%\r", (progress / (total / 100)));
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("Error[%u]: ", error);
    if (error == OTA_AUTH_ERROR) {
      Serial.println("Auth Failed");
    } else if (error == OTA_BEGIN_ERROR) {
      Serial.println("Begin Failed");
    } else if (error == OTA_CONNECT_ERROR) {
      Serial.println("Connect Failed");
    } else if (error == OTA_RECEIVE_ERROR) {
      Serial.println("Receive Failed");
    } else if (error == OTA_END_ERROR) {
      Serial.println("End Failed");
    }
  });
  ArduinoOTA.begin();
  Serial.println("OTA Ready");
}

//#############################################################################################################################################
//###                                                                    ###
//###                             BUTTON                                    ###
//###                                                                   ###
//#############################################################################################################################################

void handleButton() {
  if (digitalRead(BUTTON) == LOW) {
    if (locked) {
      unlock();
      Serial.println("unlocked using the button");
      debugV("unlocked");
    } else {
      lock();
      Serial.println("locked using the button");
      debugV("locked");
    }
    delay(1000);
  }
}

//#############################################################################################################################################
//###                                                                    ###
//###                             WIFI                                    ###
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

  if (MDNS.begin("smartlock")) {
    Serial.println("MDNS responder started");
  }
}

//#############################################################################################################################################
//###                                                                    ###
//###                             LED                                    ###
//###                                                                   ###
//#############################################################################################################################################

void handleLED() {
  if (!locked) {
    digitalWrite(RINGLED, HIGH);
  } else {
    digitalWrite(RINGLED, LOW);
  }
}

//#############################################################################################################################################
//###                                                                    ###
//###                             MAIN                                    ###
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
  server.on("/debug", HTTP_GET, handleDebug);
  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("HTTP server started");

  initOTA();

  Debug.begin("ESP");
}

void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  handleUpdateLockState();
  handleButton();
  handleLED();
  Debug.handle();
}