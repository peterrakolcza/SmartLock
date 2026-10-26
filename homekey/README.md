# 💳 Home Key with HomeKey-ESP32

The Raspberry Pi / Orange Pi Python reader is replaced by [HomeKey-ESP32](https://github.com/rednblkx/HomeKey-ESP32) by [rednblkx](https://github.com/rednblkx). It runs on a ~5 € ESP32 board with a PN532 NFC module and appears in Apple Home as a **native HomeKit lock with Home Key** (Express mode included). You don't need Homebridge, a Pi, or a server.

The smart lock stays the mechanism. The reader is the Apple Home accessory and tells the lock what to do over Wi-Fi:

```
 iPhone / Watch ──NFC──▶ HomeKey-ESP32 reader ──MQTT (Wi-Fi)──▶ Smart lock (ESP8266) ──▶ servo
 Home app ─────HomeKit──▶        ▲                                   │
                                 └──────── real lock state ◀─────────┘  (button, key, HTTP API)
```

## Three ways to use the lock

| Setup | What you need | `HOMEKEY_MODE` |
| :-- | :-- | :-: |
| **Standalone** | The lock only. Use the side button and the HTTP API, or Homebridge + [EspLock](https://github.com/volca/homebridge-esplock). | `0` |
| **Apple Home + Home Key** (recommended) | The lock plus the HomeKey-ESP32 reader. The reader connects **directly to the lock**, which runs a tiny built-in MQTT broker. | `1` |
| **Apple Home + Home Key + Home Assistant** | The lock, the reader and your existing MQTT broker (Mosquitto, Home Assistant add-on). | `2` |

In every mode the HTTP API keeps working, and the lock reports manual changes (button, thumb-turn, key) back to Apple Home.

## Hardware

| Part | Notes | ~Price |
| :-- | :-- | :-: |
| ESP32 DevKitC (ESP32-WROOM-32) | any classic ESP32 board works | 4 € |
| PN532 NFC module (red "V3" board) | set the DIP switches to **SPI** (`0` `1`) | 4 € |
| 6 wires, USB cable + 5 V charger | | |
| 3D printed enclosure | [`reader_base.stl`](3D%20printed%20case/reader_base.stl) + [`reader_cover.stl`](3D%20printed%20case/reader_cover.stl) | |

The compact enclosure is for indoor use, such as a hallway wall next to the door. The NFC face is 1.2 mm thick, so print the cover face down. The DevKit lies face down on the two ledges with its pins pointing up. Solder the six wires (or use bent pins) and fix the board with a drop of hot glue or double-sided tape. Every dimension is a parameter in [`reader_enclosure.py`](3D%20printed%20case/reader_enclosure.py).

The weatherproof enclosure from the previous Raspberry Pi version is still in [`3D printed case`](3D%20printed%20case) (`enclosure-with-pg7-hub.stl`, `lid-with-homekit-logo-in-portrait.stl`, `nfc-hold-down.stl`). It is roomier, so the ESP32 board fits as well.

### Wiring (PN532 in SPI mode)

| ESP32 | PN532 |
| :-: | :-: |
| 3V3 | VCC |
| GND | GND |
| GPIO18 | SCK |
| GPIO19 | MISO |
| GPIO23 | MOSI |
| GPIO5 | SS |

These are HomeKey-ESP32's default pins, and you can change them in its web UI.

## Setup

### 1. Flash the reader

1. Download the latest `*.firmware.factory.bin` from the [HomeKey-ESP32 releases](https://github.com/rednblkx/HomeKey-ESP32/releases). Use the **unencrypted** build, because the encrypted one disables USB flashing.
2. Flash it with the browser flasher linked in the release notes, or run `esptool.py --port <port> write_flash 0x0 <file>.factory.bin`.
3. Join the `HomeSpan-Setup` Wi-Fi (password `homespan`), open `http://192.168.4.1` and enter your Wi-Fi credentials.
4. Add it in the Home app with the setup code `466-37-726` (you can change it in the web UI), then add Home Key in Wallet.

### 2. Configure MQTT on the reader

Open the reader's web UI and go to **MQTT**:

| Setting | Mode `1` (built-in broker) | Mode `2` (external broker) |
| :-- | :-- | :-- |
| Broker | IP address of the lock (shown on the serial monitor, or `ping smartlock.local`) | your broker |
| Port | `1883` | your broker's port |
| Client ID | `smartlock-reader` | `smartlock-reader` |
| Username / password | same as `MQTT_USER` / `MQTT_PASS` in the firmware, or empty | your broker's |
| Home Assistant discovery | off | as you like |

With the Client ID `smartlock-reader`, the reader's default topics match the lock: it publishes `smartlock-reader/homekit/state` and listens on `smartlock-reader/homekit/set_state`. If you use a different Client ID, change `HOMEKEY_TOPIC_PREFIX` in the firmware to match.

Leave the reader's GPIO actions disabled, because the lock does the moving. Also leave *Dumb Switch* mode off, so the reader waits for the lock to confirm each state change.

Use the lock's **IP address** rather than `smartlock.local`, because `.local` names may not resolve on the reader. Give the lock a static DHCP lease in your router.

### 3. Configure and flash the lock

In [`code/smart_lock/smart_lock.ino`](../code/smart_lock/smart_lock.ino):

```cpp
#define HOMEKEY_MODE 1                          // 0 standalone, 1 built-in broker, 2 external broker
#define HOMEKEY_TOPIC_PREFIX "smartlock-reader" // = Client ID on the reader
#define MQTT_HOST "192.168.1.10"                // only for mode 2
#define MQTT_USER ""                            // optional
#define MQTT_PASS ""
```

Flash it with the Arduino IDE (install *ArduinoJson* and *PubSubClient* from the library manager) or with PlatformIO (`cd code/smart_lock && pio run -t upload`). On the serial monitor you should see `HomeKey: reader connected as smartlock-reader`, and `GET http://smartlock.local` returns `"homekey":true`.

## How it works

| Topic | Direction | Payload |
| :-- | :-- | :-- |
| `smartlock-reader/homekit/state` | reader → lock | `4` unlocking, `5` locking: the lock starts the servo. `0` / `1` are confirmations and are ignored. |
| `smartlock-reader/homekit/set_state` | lock → reader | `0` unlocked, `1` locked (retained). Sent when a movement finishes and on every manual change. |

A Home Key tap or a Home app command makes the reader publish *unlocking* or *locking*. The lock moves and then reports the real state, and only then does Apple Home show the lock as unlocked or locked. If someone uses the button or turns the key by hand, the lock reports the new state as well, so Apple Home stays in sync.

The built-in broker (mode `1`) implements only the part of MQTT 3.1.1 that one reader needs, and it accepts a single client. To connect more MQTT clients, such as Home Assistant, use mode `2` with a real broker.

### Security notes

* The lock's HTTP API and MQTT port are unauthenticated on your LAN, as before. Set `MQTT_USER` / `MQTT_PASS` to at least require credentials from the reader.
* Home Key authentication happens on the reader, and the lock only acts on the reader's result. Keep both on a trusted Wi-Fi network.
