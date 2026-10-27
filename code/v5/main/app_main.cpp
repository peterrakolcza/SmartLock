// v5 smart lock firmware: ESP32-C6, Matter door lock over Thread, worm drive + spiral coupling.
// Two builds: battery (Thread sleepy end device, sdkconfig.defaults) and USB powered (Thread router,
// CONFIG_SMARTLOCK_USB_POWERED via sdkconfig.defaults.usb).
//
// Hardware: PCB/v5 (pins in PCB/v5/layout.py). The motion logic is code/smart_lock/motion.h, the same file the
// simulation in code/tests/motion checks.
//
// Button: short press = lock / unlock, hold 6 s = forget the learned turns, hold 12 s = factory reset (leaves Matter).
// LED: blinks while moving, fast blinking = jammed, short flash every 2 s = not commissioned.
//
// Power (battery build): between Thread polls the chip is in automatic light sleep. The main task blocks until the button or the
// thumb-turn sensor changes level (GPIO wake), a Matter command arrives, or the next battery report is due. While the
// motor runs, a PM lock keeps the CPU awake.

#include <driver/gpio.h>
#include <esp_adc/adc_cali.h>
#include <esp_adc/adc_cali_scheme.h>
#include <esp_adc/adc_oneshot.h>
#include <esp_log.h>
#include <esp_pm.h>
#include <esp_sleep.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <nvs.h>
#include <nvs_flash.h>

#include <esp_matter.h>
#include <app/clusters/door-lock-server/door-lock-server.h>
#include <app/server/Server.h>
#include <esp_openthread_types.h>
#include <platform/ESP32/OpenthreadLauncher.h>

#include "motion.h"

using namespace esp_matter;
using namespace chip::app::Clusters;

static const char *TAG = "lock";

// Pins: PCB/v5/layout.py GPIO
static const gpio_num_t PIN_BUTTON = GPIO_NUM_9;
static const gpio_num_t PIN_MOTOR_IN1 = GPIO_NUM_18;
static const gpio_num_t PIN_MOTOR_IN2 = GPIO_NUM_19;
static const gpio_num_t PIN_MOTOR_SLEEP = GPIO_NUM_20;
static const gpio_num_t PIN_HALL_HUB = GPIO_NUM_21;
static const gpio_num_t PIN_HALL_KNOB = GPIO_NUM_22;
static const gpio_num_t PIN_LED = GPIO_NUM_23;
static const adc_channel_t VBAT_CHANNEL = ADC_CHANNEL_0;     // GPIO0, behind a 1 M / 1 M divider

static const uint32_t BATTERY_INTERVAL_MS = 10UL * 60 * 1000;

static uint32_t millis() { return (uint32_t)(esp_timer_get_time() / 1000); }

MotionController motion;
static nvs_handle_t prefs;
static SemaphoreHandle_t wakeSignal;
static esp_pm_lock_handle_t awakeLock = nullptr;   // battery build only (power management)
static uint16_t lockEndpoint = 0;
static uint16_t powerEndpoint = 0;
static volatile bool commissioned = false;

// ------------------------------------------------------------------------------------------------- hardware
static void motorRun(int direction) {
  // DRV8833, both bridges in parallel: IN1 / IN2 high-low = forward, low-high = reverse, low-low = coast
  gpio_set_level(PIN_MOTOR_IN1, direction > 0);
  gpio_set_level(PIN_MOTOR_IN2, direction < 0);
}

static void motorPower(bool on) {
  gpio_set_level(PIN_MOTOR_SLEEP, on);   // nSLEEP: the driver draws < 1 uA asleep (and has a pull-down)
  if (on) vTaskDelay(pdMS_TO_TICKS(2));
}

static bool knobActive() { return gpio_get_level(PIN_HALL_KNOB) == 0; }   // DRV5032 pulls low in a field
static bool hubActive() { return gpio_get_level(PIN_HALL_HUB) == 0; }
static bool buttonDown() { return gpio_get_level(PIN_BUTTON) == 0; }

static adc_oneshot_unit_handle_t adc;
static adc_cali_handle_t adcCali;

static void batteryBegin() {
  adc_oneshot_unit_init_cfg_t unit = {};
  unit.unit_id = ADC_UNIT_1;
  ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit, &adc));
  adc_oneshot_chan_cfg_t chan = {};
  chan.atten = ADC_ATTEN_DB_12;
  chan.bitwidth = ADC_BITWIDTH_DEFAULT;
  ESP_ERROR_CHECK(adc_oneshot_config_channel(adc, VBAT_CHANNEL, &chan));
  adc_cali_curve_fitting_config_t cali = {};
  cali.unit_id = ADC_UNIT_1;
  cali.chan = VBAT_CHANNEL;
  cali.atten = ADC_ATTEN_DB_12;
  cali.bitwidth = ADC_BITWIDTH_DEFAULT;
  if (adc_cali_create_scheme_curve_fitting(&cali, &adcCali) != ESP_OK) adcCali = nullptr;
}

static uint8_t batteryPercent() {
  int raw = 0, mv = 0;
  adc_oneshot_read(adc, VBAT_CHANNEL, &raw);
  if (adcCali) adc_cali_raw_to_voltage(adcCali, raw, &mv);
  else mv = raw * 3100 / 4095;
  int percent = (mv * 2 - 3300) * 100 / (4150 - 3300);
  return (uint8_t)(percent < 0 ? 0 : percent > 100 ? 100 : percent);
}

// ------------------------------------------------------------------------------------------------- wake-up
// The button and the thumb-turn sensor wake the CPU from light sleep with a level interrupt, re-armed for the
// opposite level before every wait.
static const gpio_num_t WAKE_PINS[] = {PIN_BUTTON, PIN_HALL_KNOB};

static void IRAM_ATTR onWakePin(void *arg) {
  gpio_intr_disable((gpio_num_t)(intptr_t)arg);
  BaseType_t woken = pdFALSE;
  xSemaphoreGiveFromISR(wakeSignal, &woken);
  if (woken) portYIELD_FROM_ISR();
}

static void armWakePins() {
  for (gpio_num_t pin : WAKE_PINS) {
    gpio_wakeup_enable(pin, gpio_get_level(pin) ? GPIO_INTR_LOW_LEVEL : GPIO_INTR_HIGH_LEVEL);
    gpio_intr_enable(pin);
  }
}

static void wakeLoop() { xSemaphoreGive(wakeSignal); }

static void hardwareBegin() {
  gpio_config_t out = {};
  out.pin_bit_mask = (1ULL << PIN_MOTOR_IN1) | (1ULL << PIN_MOTOR_IN2) | (1ULL << PIN_MOTOR_SLEEP) | (1ULL << PIN_LED);
  out.mode = GPIO_MODE_OUTPUT;
  gpio_config(&out);
  motorPower(false);
  motorRun(0);
  gpio_config_t in = {};
  in.pin_bit_mask = (1ULL << PIN_HALL_HUB) | (1ULL << PIN_HALL_KNOB) | (1ULL << PIN_BUTTON);   // pull-ups on the PCB
  in.mode = GPIO_MODE_INPUT;
  gpio_config(&in);
  batteryBegin();

  wakeSignal = xSemaphoreCreateBinary();
  gpio_install_isr_service(0);
  for (gpio_num_t pin : WAKE_PINS) gpio_isr_handler_add(pin, onWakePin, (void *)(intptr_t)pin);
  armWakePins();
  esp_sleep_enable_gpio_wakeup();
#if CONFIG_PM_ENABLE
  esp_pm_lock_create(ESP_PM_NO_LIGHT_SLEEP, 0, "motor", &awakeLock);
  esp_pm_config_t pm = {};
  pm.max_freq_mhz = CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ;
  pm.min_freq_mhz = CONFIG_XTAL_FREQ;
  pm.light_sleep_enable = true;
  ESP_ERROR_CHECK(esp_pm_configure(&pm));
#endif
}

// ------------------------------------------------------------------------------------------------- Matter
static void reportState(DoorLock::DlLockState state, DoorLock::OperationSourceEnum source) {
  lock::ScopedChipStackLock guard(portMAX_DELAY);
  DoorLockServer::Instance().SetLockState(lockEndpoint, state, source);
}

static void reportJammed() {
  lock::ScopedChipStackLock guard(portMAX_DELAY);
  DoorLockServer::Instance().SetLockState(lockEndpoint, DoorLock::DlLockState::kNotFullyLocked);
  DoorLockServer::Instance().SendLockAlarmEvent(lockEndpoint, DoorLock::AlarmCodeEnum::kLockJammed);
}

static void reportBattery(uint8_t percent) {
  esp_matter_attr_val_t v = esp_matter_nullable_uint8((uint8_t)(percent * 2));   // half percent units
  attribute::update(powerEndpoint, PowerSource::Id, PowerSource::Attributes::BatPercentRemaining::Id, &v);
}

// esp-matter's door lock cluster expects the app to provide this (CHIP generates it into the app's ZAP code)
void emberAfDoorLockClusterInitCallback(chip::EndpointId endpoint) {
  DoorLockServer::Instance().InitServer(endpoint);
}

// Commands arrive on the CHIP task: only record them, the main task does the work
static volatile int pendingCommand = 0;   // +1 lock, -1 unlock

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

static void onEvent(const ChipDeviceEvent *event, intptr_t) {
  switch (event->Type) {
  case chip::DeviceLayer::DeviceEventType::kCommissioningComplete:
    commissioned = true;
    break;
  case chip::DeviceLayer::DeviceEventType::kFabricRemoved:
    commissioned = chip::Server::GetInstance().GetFabricTable().FabricCount() > 0;
    break;
  default:
    break;
  }
  wakeLoop();
}

static esp_err_t onAttribute(attribute::callback_type_t, uint16_t, uint32_t, uint32_t, esp_matter_attr_val_t *, void *) {
  return ESP_OK;
}

static esp_err_t onIdentify(identification::callback_type_t, uint16_t, uint8_t, uint8_t, void *) { return ESP_OK; }

static void matterBegin(bool locked) {
  node::config_t nodeConfig;
  node_t *node = node::create(&nodeConfig, onAttribute, onIdentify);
  assert(node);

  endpoint::door_lock::config_t lockConfig;
  lockConfig.door_lock.lock_state = (uint8_t)(locked ? DoorLock::DlLockState::kLocked : DoorLock::DlLockState::kUnlocked);
  lockConfig.door_lock.lock_type = (uint8_t)DoorLock::DlLockType::kDeadBolt;
  lockConfig.door_lock.actuator_enabled = true;
  endpoint_t *ep = endpoint::door_lock::create(node, &lockConfig, ENDPOINT_FLAG_NONE, nullptr);
  assert(ep);
  lockEndpoint = endpoint::get_id(ep);

  // Power source for the home apps (on the lock's endpoint): battery level, or "wired" for the USB version
  cluster::power_source::config_t ps;
#if CONFIG_SMARTLOCK_USB_POWERED
  ps.feature_flags = cluster::power_source::feature::wired::get_id();
#else
  ps.feature_flags = cluster::power_source::feature::battery::get_id() | cluster::power_source::feature::rechargeable::get_id();
#endif
  cluster::power_source::create(ep, &ps, CLUSTER_FLAG_SERVER);
  powerEndpoint = lockEndpoint;

  esp_openthread_platform_config_t thread = {};
  thread.radio_config.radio_mode = RADIO_MODE_NATIVE;
  thread.host_config.host_connection_mode = HOST_CONNECTION_MODE_NONE;
  thread.port_config.storage_partition_name = "nvs";
  thread.port_config.netif_queue_size = 10;
  thread.port_config.task_queue_size = 10;
  set_openthread_platform_config(&thread);

  ESP_ERROR_CHECK(esp_matter::start(onEvent));
  lock::ScopedChipStackLock guard(portMAX_DELAY);
  commissioned = chip::Server::GetInstance().GetFabricTable().FabricCount() > 0;
}

// ------------------------------------------------------------------------------------------------- lock logic
static bool locked = true;
static bool jammedState = false;
static DoorLock::OperationSourceEnum lastSource = DoorLock::OperationSourceEnum::kRemote;
static unsigned manualCounter = 0;
static bool knobWas = false;

static void saveLearned() {
  nvs_set_blob(prefs, "learned", &motion.learned, sizeof(motion.learned));
  nvs_commit(prefs);
}

static void saveLocked() {
  nvs_set_u8(prefs, "locked", locked);
  nvs_commit(prefs);
}

static void reportLocked(DoorLock::OperationSourceEnum source) {
  reportState(locked ? DoorLock::DlLockState::kLocked : DoorLock::DlLockState::kUnlocked, source);
}

static void startMotion(bool toLocked, DoorLock::OperationSourceEnum source) {
  if (motion.busy() || (locked == toLocked && !jammedState)) {
    reportLocked(source);
    return;
  }
  lastSource = source;
  if (awakeLock) esp_pm_lock_acquire(awakeLock);
  motion.start(toLocked, millis(), knobActive(), hubActive());
}

static void handleMotion() {
  if (!motion.busy()) return;
  MotionResult r = motion.update(millis(), knobActive(), hubActive());
  if (r != MOTION_DONE && r != MOTION_JAMMED) return;
  if (r == MOTION_DONE) {
    locked = motion.targetLocked();
    jammedState = false;
    saveLocked();
    reportLocked(lastSource);
    ESP_LOGI(TAG, "%s after %u turn(s)", locked ? "locked" : "unlocked", motion.arrivals());
  } else {
    jammedState = true;
    locked = false;
    reportJammed();
    ESP_LOGW(TAG, "jammed after %u turn(s)", motion.arrivals());
  }
  if (motion.learnedChanged) {
    motion.learnedChanged = false;
    saveLearned();
  }
  manualCounter = 0;
  knobWas = knobActive();
  if (awakeLock) esp_pm_lock_release(awakeLock);
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
    saveLocked();
    reportLocked(DoorLock::OperationSourceEnum::kManual);
  }
}

static uint32_t pressedAt = 0;

static void handleButton() {
  bool down = buttonDown();
  if (down && pressedAt == 0) pressedAt = millis() | 1;
  if (!down && pressedAt != 0) {
    uint32_t held = millis() - pressedAt;
    pressedAt = 0;
    if (held > 12000) {
      esp_matter::factory_reset();
    } else if (held > 6000) {
      motion.forget();
      saveLearned();
      ESP_LOGI(TAG, "learned turns forgotten");
    } else if (held > 40) {
      startMotion(!locked, DoorLock::OperationSourceEnum::kButton);
    }
  }
}

static bool ledBlinking() { return motion.busy() || jammedState || !commissioned; }

static void handleLed() {
  uint32_t t = millis();
  bool on = false;
  if (motion.busy()) on = (t / 150) % 2;
  else if (jammedState) on = (t / 80) % 2;
  else if (!commissioned) on = (t % 2000) < 100;
  gpio_set_level(PIN_LED, on);
}

static uint32_t lastBattery = 0;

static void handleBattery() {
#if CONFIG_SMARTLOCK_USB_POWERED
  return;                                   // no battery: the divider sees the USB rail
#endif
  if (lastBattery != 0 && millis() - lastBattery < BATTERY_INTERVAL_MS) return;
  lastBattery = millis() | 1;
  reportBattery(batteryPercent());
}

// Block until something can happen: a pin, a command, the LED or button timers, or the next battery report
static void idleWait() {
#if CONFIG_SMARTLOCK_USB_POWERED
  uint32_t wait = 1000;                     // nothing to time: just a slow heartbeat
#else
  uint32_t wait = BATTERY_INTERVAL_MS - (millis() - lastBattery);
#endif
  if (ledBlinking() || pressedAt != 0) wait = 40;
  armWakePins();
  xSemaphoreTake(wakeSignal, pdMS_TO_TICKS(wait));
}

// ------------------------------------------------------------------------------------------------- main
extern "C" void app_main() {
  esp_err_t err = nvs_flash_init();
  if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    nvs_flash_erase();
    nvs_flash_init();
  }
  hardwareBegin();
  ESP_ERROR_CHECK(nvs_open("lock", NVS_READWRITE, &prefs));
  uint8_t storedLocked = 1;
  nvs_get_u8(prefs, "locked", &storedLocked);
  locked = storedLocked;
  size_t size = sizeof(motion.learned);
  nvs_get_blob(prefs, "learned", &motion.learned, &size);
  MotionHardware hw = {motorRun, motorPower};
  motion.begin(hw);

  matterBegin(locked);
  knobWas = knobActive();

  while (true) {
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
    if (motion.busy()) vTaskDelay(1);
    else idleWait();
  }
}
