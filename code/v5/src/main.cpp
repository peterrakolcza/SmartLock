// v5 smart lock firmware: ESP32-C6, Matter door lock over Thread, worm drive + spiral coupling.
//
// Hardware: PCB/v5 (pins in PCB/v5/layout.py). The motion logic is code/smart_lock/motion.h, the same file the
// simulation in code/tests/motion checks.
//
// Button: short press = lock / unlock, hold 6 s = forget the learned turns, hold 12 s = leave the Matter fabric.
// LED: blinks while moving, fast blinking = jammed, slow pulse = not commissioned.

#include <Arduino.h>
#include <Matter.h>
#include <MatterEndPoint.h>
#include <Preferences.h>
#include <esp_matter.h>
#include <app/clusters/door-lock-server/door-lock-server.h>

#include "motion.h"

#if CONFIG_PM_ENABLE
#include <driver/gpio.h>
#include <esp_pm.h>
#include <esp_sleep.h>
#endif

using namespace esp_matter;
using namespace chip::app::Clusters;

// Pins: PCB/v5/layout.py GPIO
static const int PIN_VBAT_SENSE = 0;
static const int PIN_ISENSE = 1;
static const int PIN_CHG_STAT = 2;
static const int PIN_MOTOR_FAULT = 3;
static const int PIN_BUTTON = 9;
static const int PIN_MOTOR_IN1 = 18;
static const int PIN_MOTOR_IN2 = 19;
static const int PIN_MOTOR_SLEEP = 20;
static const int PIN_HALL_HUB = 21;
static const int PIN_HALL_KNOB = 22;
static const int PIN_LED = 23;

static const uint32_t BATTERY_INTERVAL_MS = 10UL * 60 * 1000;

Preferences prefs;
MotionController motion;

// ------------------------------------------------------------------------------------------------- hardware
static void motorRun(int direction) {
  // DRV8833, both bridges in parallel: IN1 / IN2 high-low = forward, low-high = reverse, low-low = coast
  digitalWrite(PIN_MOTOR_IN1, direction > 0 ? HIGH : LOW);
  digitalWrite(PIN_MOTOR_IN2, direction < 0 ? HIGH : LOW);
}

static void motorPower(bool on) {
  digitalWrite(PIN_MOTOR_SLEEP, on ? HIGH : LOW);   // nSLEEP: the driver draws < 1 uA asleep
  if (on) delay(2);
}

static bool knobActive() { return digitalRead(PIN_HALL_KNOB) == LOW; }  // DRV5032 pulls low in a field
static bool hubActive() { return digitalRead(PIN_HALL_HUB) == LOW; }

static uint8_t batteryPercent() {
  uint32_t mv = analogReadMilliVolts(PIN_VBAT_SENSE) * 2;      // 1 M / 1 M divider
  int percent = map((long)mv, 3300, 4150, 0, 100);
  return (uint8_t)constrain(percent, 0, 100);
}

// ------------------------------------------------------------------------------------------------- Matter endpoint
// ArduinoMatter::_init() is protected: a derived helper can reach it
struct MatterInit : ArduinoMatter {
  static void run() { _init(); }
};

class MatterLock : public MatterEndPoint {
public:
  bool begin(bool locked) {
    MatterInit::run();
    endpoint::door_lock::config_t config;
    config.door_lock.lock_state = locked ? (uint8_t)DoorLock::DlLockState::kLocked : (uint8_t)DoorLock::DlLockState::kUnlocked;
    config.door_lock.lock_type = (uint8_t)DoorLock::DlLockType::kDeadBolt;
    config.door_lock.actuator_enabled = true;
    endpoint_t *ep = endpoint::door_lock::create(node::get(), &config, ENDPOINT_FLAG_NONE, (void *)this);
    if (ep == nullptr) {
      log_e("Failed to create the door lock endpoint");
      return false;
    }
    setEndPointId(endpoint::get_id(ep));
    // Battery level for the Home app
    cluster::power_source::config_t ps;
    ps.feature_flags = cluster::power_source::feature::battery::get_id() | cluster::power_source::feature::rechargeable::get_id();
    cluster_t *power = cluster::power_source::create(ep, &ps, CLUSTER_FLAG_SERVER);
    if (power == nullptr) log_w("No power source cluster");
    return true;
  }

  bool attributeChangeCB(uint16_t, uint32_t, uint32_t, esp_matter_attr_val_t *) override { return true; }

  // Report the real state to the hubs (called from loop(), so lock the CHIP stack)
  void report(DoorLock::DlLockState state, DoorLock::OperationSourceEnum source) {
    lock::ScopedChipStackLock guard(portMAX_DELAY);
    DoorLockServer::Instance().SetLockState(getEndPointId(), state, source);
  }

  void jammed() {
    lock::ScopedChipStackLock guard(portMAX_DELAY);
    DoorLockServer::Instance().SetLockState(getEndPointId(), DoorLock::DlLockState::kNotFullyLocked);
    DoorLockServer::Instance().SendLockAlarmEvent(getEndPointId(), DoorLock::AlarmCodeEnum::kLockJammed);
  }

  void battery(uint8_t percent) {
    esp_matter_attr_val_t v = esp_matter_nullable_uint8((uint8_t)(percent * 2));   // half percent units
    attribute::update(getEndPointId(), PowerSource::Id, PowerSource::Attributes::BatPercentRemaining::Id, &v);
  }
};

MatterLock matterLock;

// esp-matter's door lock cluster expects the app to provide this (CHIP generates it into the app's ZAP code)
void emberAfDoorLockClusterInitCallback(chip::EndpointId endpoint) {
  DoorLockServer::Instance().InitServer(endpoint);
}

// Commands arrive on the CHIP task: only record them, loop() does the work
static volatile int pendingCommand = 0;   // +1 lock, -1 unlock
static void wakeLoop();

bool emberAfPluginDoorLockOnDoorLockCommand(chip::EndpointId, const chip::app::DataModel::Nullable<chip::FabricIndex> &,
                                            const chip::app::DataModel::Nullable<chip::NodeId> &, const chip::Optional<chip::ByteSpan> &,
                                            DoorLock::OperationErrorEnum &) {
  pendingCommand = 1;
  wakeLoop();
  return true;
}

bool emberAfPluginDoorLockOnDoorUnlockCommand(chip::EndpointId, const chip::app::DataModel::Nullable<chip::FabricIndex> &,
                                              const chip::app::DataModel::Nullable<chip::NodeId> &, const chip::Optional<chip::ByteSpan> &,
                                              DoorLock::OperationErrorEnum &) {
  pendingCommand = -1;
  wakeLoop();
  return true;
}

// ------------------------------------------------------------------------------------------------- lock logic
bool locked = true;
bool jammedState = false;
DoorLock::OperationSourceEnum lastSource = DoorLock::OperationSourceEnum::kRemote;
int manualCounter = 0;
bool knobWas = false;

static void saveLearned() {
  prefs.putBytes("learned", &motion.learned, sizeof(motion.learned));
}

static void startMotion(bool toLocked, DoorLock::OperationSourceEnum source) {
  if (motion.busy() || (locked == toLocked && !jammedState)) {
    matterLock.report(locked ? DoorLock::DlLockState::kLocked : DoorLock::DlLockState::kUnlocked, source);
    return;
  }
  lastSource = source;
  motion.start(toLocked, millis(), knobActive(), hubActive());
}

static void handleMotion() {
  if (!motion.busy()) return;
  MotionResult r = motion.update(millis(), knobActive(), hubActive());
  if (r == MOTION_DONE) {
    locked = motion.targetLocked();
    jammedState = false;
    prefs.putBool("locked", locked);
    matterLock.report(locked ? DoorLock::DlLockState::kLocked : DoorLock::DlLockState::kUnlocked, lastSource);
    log_i("%s after %u turn(s)", locked ? "locked" : "unlocked", motion.arrivals());
  } else if (r == MOTION_JAMMED) {
    jammedState = true;
    locked = false;
    matterLock.jammed();
    log_w("jammed after %u turn(s)", motion.arrivals());
  }
  if ((r == MOTION_DONE || r == MOTION_JAMMED) && motion.learnedChanged) {
    motion.learnedChanged = false;
    saveLearned();
  }
  if (r == MOTION_DONE || r == MOTION_JAMMED) {
    manualCounter = 0;
    knobWas = knobActive();
  }
}

// The key turned the thumb-turn by hand: count turns with the knob sensor
static void handleManual() {
  bool active = knobActive();
  if (active && !knobWas) manualCounter++;
  knobWas = active;
  if (manualCounter >= motion.manualTurns()) {
    manualCounter = 0;
    locked = !locked;
    jammedState = false;
    prefs.putBool("locked", locked);
    matterLock.report(locked ? DoorLock::DlLockState::kLocked : DoorLock::DlLockState::kUnlocked, DoorLock::OperationSourceEnum::kManual);
  }
}

static void handleButton() {
  static uint32_t pressedAt = 0;
  bool down = digitalRead(PIN_BUTTON) == LOW;
  if (down && pressedAt == 0) pressedAt = millis();
  if (!down && pressedAt != 0) {
    uint32_t held = millis() - pressedAt;
    pressedAt = 0;
    if (held > 12000) {
      Matter.decommission();
    } else if (held > 6000) {
      motion.forget();
      saveLearned();
      log_i("learned turns forgotten");
    } else if (held > 40) {
      startMotion(!locked, DoorLock::OperationSourceEnum::kButton);
    }
  }
}

static void handleLed() {
  uint32_t t = millis();
  bool on;
  if (motion.busy()) on = (t / 150) % 2;
  else if (jammedState) on = (t / 80) % 2;
  else if (!Matter.isDeviceCommissioned()) on = (t % 2000) < 100;
  else on = false;
  digitalWrite(PIN_LED, on);
}

static void handleBattery() {
  static uint32_t last = 0;
  if (last != 0 && millis() - last < BATTERY_INTERVAL_MS) return;
  last = millis();
  matterLock.battery(batteryPercent());
}

// ------------------------------------------------------------------------------------------------- sleep
// Battery build (env smartlock-v5-sleepy): automatic light sleep between Thread polls. The button and the knob hall
// wake the CPU with a level interrupt that is re-armed for the opposite level each time, so loop() can block
// instead of polling every 20 ms.
#if CONFIG_PM_ENABLE
static SemaphoreHandle_t wakeSignal;
static const int WAKE_PINS[] = {PIN_BUTTON, PIN_HALL_KNOB};

static void IRAM_ATTR onWakePin(void *arg) {
  gpio_intr_disable((gpio_num_t)(intptr_t)arg);
  BaseType_t woken = pdFALSE;
  xSemaphoreGiveFromISR(wakeSignal, &woken);
  if (woken) portYIELD_FROM_ISR();
}

static void armWakePins() {
  for (int pin : WAKE_PINS) {
    gpio_wakeup_enable((gpio_num_t)pin, digitalRead(pin) ? GPIO_INTR_LOW_LEVEL : GPIO_INTR_HIGH_LEVEL);
    gpio_intr_enable((gpio_num_t)pin);
  }
}

static void sleepBegin() {
  wakeSignal = xSemaphoreCreateBinary();
  gpio_install_isr_service(0);   // already installed by the Arduino core: harmless
  for (int pin : WAKE_PINS) gpio_isr_handler_add((gpio_num_t)pin, onWakePin, (void *)(intptr_t)pin);
  armWakePins();
  esp_sleep_enable_gpio_wakeup();
  esp_pm_config_t pm = {.max_freq_mhz = 160, .min_freq_mhz = 40, .light_sleep_enable = true};
  esp_pm_configure(&pm);
}

static void wakeLoop() {
  if (wakeSignal) xSemaphoreGive(wakeSignal);
}

static void idleWait() {
  armWakePins();
  // wakes on a pin or a Matter command; the timeout keeps the LED and the button hold timers going
  xSemaphoreTake(wakeSignal, pdMS_TO_TICKS(100));
}
#else
static void wakeLoop() {}
static void sleepBegin() {}
static void idleWait() { delay(20); }
#endif

// ------------------------------------------------------------------------------------------------- main
void setup() {
  Serial.begin(115200);
  pinMode(PIN_MOTOR_IN1, OUTPUT);
  pinMode(PIN_MOTOR_IN2, OUTPUT);
  pinMode(PIN_MOTOR_SLEEP, OUTPUT);
  motorPower(false);
  motorRun(0);
  pinMode(PIN_HALL_HUB, INPUT);
  pinMode(PIN_HALL_KNOB, INPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_MOTOR_FAULT, INPUT_PULLUP);
  pinMode(PIN_CHG_STAT, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  analogSetPinAttenuation(PIN_VBAT_SENSE, ADC_11db);

  prefs.begin("lock");
  locked = prefs.getBool("locked", true);
  prefs.getBytes("learned", &motion.learned, sizeof(motion.learned));
  MotionHardware hw = {motorRun, motorPower};
  motion.begin(hw);

#if CONFIG_ENABLE_MATTER_OVER_THREAD
  Matter.selectNetwork(MATTER_NETWORK_THREAD);
#endif
  matterLock.begin(locked);
  Matter.begin();
  if (!Matter.isDeviceCommissioned()) {
    Serial.printf("Pair in your home app: %s\n%s\n", Matter.getManualPairingCode().c_str(), Matter.getOnboardingQRCodeUrl().c_str());
  }
  knobWas = knobActive();
  sleepBegin();
}

void loop() {
  int cmd = pendingCommand;
  if (cmd != 0) {
    pendingCommand = 0;
    startMotion(cmd > 0, DoorLock::OperationSourceEnum::kRemote);
  }
  handleMotion();
  if (!motion.busy()) {
    handleManual();
    handleButton();
    handleBattery();
  }
  handleLed();
  if (motion.busy()) delay(1);
  else idleWait();
}
