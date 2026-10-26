// Board support
//
// ESP8266: the original V3 PCB (ESP-12F), USB powered
// ESP32:   the low power V4 board (ESP32-C3), battery powered, see PCB/V4-low-power/README.md
//
// Everything that differs between the two lives here, the sketch only calls these functions.

#pragma once

#if defined(ESP32)

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <ESP32Servo.h>
#include <esp_wifi.h>
#include <esp_pm.h>

#define BOARD_NAME "V4 ESP32-C3 battery"
#define SERVOPIN 4
#define CLUTCHPIN 5
#define SERVO_POWER 6      // N-MOSFET in the servo ground, HIGH = servos powered
#define SENSOR 7
#define BUTTON 3
#define RINGLED 10
#define BATTERY_ADC 0      // 330k / 100k divider from the battery
#define BATTERY_DIVIDER ((330.0 + 100.0) / 100.0)
#define BATTERY_EMPTY_MV 4400  // 4 x AA (NiMH 1.1 V / alkaline ~1.1 V under load)
#define BATTERY_FULL_MV 5600   // 4 x NiMH fully charged (alkaline starts higher and reads 100 %)
#define HAS_BATTERY 1
#define LED_ALWAYS_ON_WHEN_UNLOCKED 0  // the LED ring would drain the battery, it only flashes after a change
#define LOOP_IDLE_DELAY_MS 50          // lets the CPU fall into light sleep between loop iterations

typedef WebServer LockWebServer;

static esp_pm_lock_handle_t boardNoSleepLock = nullptr;

// Light sleep stops the servo PWM, so it is blocked while anything moves
void boardKeepAwake(bool awake) {
  if (boardNoSleepLock == nullptr) return;
  if (awake) esp_pm_lock_acquire(boardNoSleepLock);
  else esp_pm_lock_release(boardNoSleepLock);
}

void boardBegin() {
  pinMode(SERVO_POWER, OUTPUT);
  digitalWrite(SERVO_POWER, LOW);
  analogReadResolution(12);
  analogSetPinAttenuation(BATTERY_ADC, ADC_11db);
}

// Called after Wi-Fi connected: DTIM based modem sleep + automatic light sleep, ~1-2 mA while idle
void boardLowPower() {
  WiFi.setSleep(WIFI_PS_MAX_MODEM);
  wifi_config_t config;
  if (esp_wifi_get_config(WIFI_IF_STA, &config) == ESP_OK) {
    config.sta.listen_interval = 3;
    esp_wifi_set_config(WIFI_IF_STA, &config);
  }

  esp_pm_config_t pm = {};
  pm.max_freq_mhz = 80;
  pm.min_freq_mhz = 10;
  pm.light_sleep_enable = true;
  esp_err_t err = esp_pm_configure(&pm);
  if (err == ESP_OK) {
    esp_pm_lock_create(ESP_PM_NO_LIGHT_SLEEP, 0, "motion", &boardNoSleepLock);
    Serial.println("Power management: automatic light sleep enabled");
  } else {
    Serial.println("Power management: light sleep NOT available, build with platformio.ini env smartlock-battery");
  }
}

void boardServoPower(bool on) {
  digitalWrite(SERVO_POWER, on ? HIGH : LOW);
  if (on) delay(20); // let the servo electronics start before the first pulse
}

// Unpowered servos must not be fed through their signal line
void boardServoPinIdle(int pin) { pinMode(pin, INPUT); }

void boardMdnsUpdate() {}

int boardBatteryMillivolts() {
  uint32_t total = 0;
  for (int i = 0; i < 8; i++) total += analogReadMilliVolts(BATTERY_ADC);
  return (int)(total / 8 * BATTERY_DIVIDER);
}

#else

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266mDNS.h>
#include <Servo.h>

#define BOARD_NAME "V3 ESP8266"
#define SERVOPIN 12
#define CLUTCHPIN 3        // RX pin of the programming header, Serial runs TX only
#define SENSOR 13
#define BUTTON 4
#define RINGLED 5
#define HAS_BATTERY 0
#define LED_ALWAYS_ON_WHEN_UNLOCKED 1
#define LOOP_IDLE_DELAY_MS 0

typedef ESP8266WebServer LockWebServer;

void boardKeepAwake(bool) {}
void boardBegin() {}
void boardLowPower() {}
void boardServoPower(bool) {}
void boardServoPinIdle(int) {}
void boardMdnsUpdate() { MDNS.update(); }
int boardBatteryMillivolts() { return 0; }

#endif

int boardBatteryPercent() {
#if HAS_BATTERY
  int percent = map(boardBatteryMillivolts(), BATTERY_EMPTY_MV, BATTERY_FULL_MV, 0, 100);
  return constrain(percent, 0, 100);
#else
  return 100;
#endif
}
