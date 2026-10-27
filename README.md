# 🔒 Smart Lock with Home Key support🔒

<img src="https://freesvg.org/img/1543428916.png" align="right" height="220">

A smart lock built using ESP8266, an affordable microcontroller with WiFi capabilities, that can be controlled through a mobile app or web interface.

### Features

- 📱 Remote control of lock through app or web interface
- 🔐 Native Apple Home support with the HomeKey-ESP32 reader, or Homebridge
- 🕰️ Real-time status updates
- 💳 Optional Home Key support with an ESP32 + PN532 reader. You don't need a Raspberry Pi
- 🔨 Easy installation, compatible with most standard locks
- 🌀 The key and thumb-turn turn freely with a single servo: a spiral coupling, no clutch, no fighting against the servo

<br>

## 💭 Inspiration

The whole idea came from a [hackaday.io](https://hackaday.io/project/11917-smart-lock) project, huge thanks for providing the basic STL files and logic. I tried to further improve the project and make it possible to integrate it into existing smart home ecosystems like Apple HomeKit.

### **Furthermore, the objectives were almost identical:**

- Device must be cheap. This means no expensive motors or sensors can be used.
- Device must be presentable. I don't want to see any cables, electronics not even the motor itself on my apartment door (since it is a very small apartment).
- No modifications on door itself. I am a tenant at this apartment right now so I can't modify anything that can't be fixed.
- It should be secure. Most of the RF devices are vulnerable to replay attacks, the lock should be safe enough.

|                Inspiration - hackaday.io                |                    Latest version               |
| :-----------------------------------------------------: | :---------------------------------------------: |
| <img src="images/hackaday_cropped.jpeg" height=400px /> | <img src="images/latest_version.JPEG" height=300px /> <img src="images/homekey.JPEG" height=300px /> |

<br>

## 🚀 Getting Started

1. Clone the repository to your local machine.

```bash
git clone https://github.com/peterrakolcza/SmartLock.git
```

2. 3D print the [single-servo lock](3D%20printed%20case/spiral/README.md), or the original case
3. Order the custom PCB and the components from JLCPCB for example
4. Wait :(
5. Configure the parameters in [`code/smart_lock/smart_lock.ino`](code/smart_lock/smart_lock.ino)
```
#ifndef STASSID
#define STASSID "*****" // CHANGE THIS
#define STAPSK  "*****" // CHANGE THIS
#endif

#define HOMEKEY_MODE 1 // 0 = standalone, 1 = HomeKey reader connects directly, 2 = external MQTT broker
```
6. Flash the firmware with the Arduino IDE (libraries: *ArduinoJson*, *PubSubClient*) or PlatformIO (`cd code/smart_lock && pio run -t upload`)
7. Assemble the whole lock
8. No calibration needed:
     - Put the magnet in the thumb-turn adapter so it is in front of the reed sensor when the thumb-turn is in its home position (where the key can be inserted and removed).
     - Start with the door unlocked. Then lock it once and unlock it once (button, app or HTTP API). On these first two moves the lock keeps turning until the thumb-turn stops at its end stop, counts the turns with the reed sensor and remembers them.
     - From then on every move stops when the magnet has come round the learned number of times, so the thumb-turn always ends in the home position. Servo speed and supply voltage no longer matter.
     - If the magnet doesn't come round in time (door handle not lifted, bolt blocked), the lock stops, reports **jammed** (Apple Home shows a jam alert, the API returns `"state":"jammed"`) and never claims to be locked.
     - To learn again (another door, moved magnet): hold the side button while powering on. The LED flashes 3 times.
9. Use it standalone (button + HTTP API), add it to Apple Home with Home Key using the [HomeKey-ESP32 reader](homekey/README.md), or integrate it with Homebridge

<br>

## ⚡ Custom PCB

You can just order my custom PCB assembled and flash the firmware. After that, connecting the sensors and servo using the header pins are easy.

<br>

|                easyEDA                |                     PCB               |
| :-----------------------------------------------------: | :---------------------------------------------: |
| <img src="images/pcb.jpg" height="550px">               | <img src="images/pcb2.JPEG" height="550px">     |

<br>

## 🔌 Pinout

<br>

<img src="images/ESP8266-Pinout.png" align=right height="350px">

| Pin on ESP | Pin in code |  Funcionality  |
| :--------: | :---------: | :------------: |
|     D6     |      12     |  Servo signal  |
|     D7     |      13     |  Reed sensor   |
|     D2     |      4      |     Button     |
|     D1     |      5      |      LED       |
|     RX     |      3      | Hub hall sensor (A3144) |

<br>
<br>
<br>
<br>
<br>
<br>
<br>
<br>

## ⚠️ **Limitations**

A lift-up handle on a smart lock can introduce several challenges that affect usability, compatibility, and security. One primary issue is user convenience. The necessity to lift the handle adds an extra step to the process of locking or unlocking the door, which can be particularly inconvenient when users' hands are full, they are in a hurry, or when it's dark. This could prevent the smart lock to properly lock the door.

The lock now detects this: if the thumb-turn stops before the learned number of turns, it reports **jammed** instead of locked (Apple Home shows a jam alert). The lock never claims to be locked when it isn't, and the next lock command simply tries again.

<br>

<img src="images/Lift-Up-Handle-Animation-2.gif" height=500px />

<br>

## 🧭 v5: self-adhesive, universal, battery powered

Designed end to end on this branch ([`redesign/`](redesign/README.md)): self-adhesive (3M VHB, nothing screwed to the door), universal (three base presets, an adapter with two screw jaws for most thumb-turns), a 1200 mAh pouch with USB-C charging, an N20 gearmotor with a self-locking worm over the spiral coupling, and Matter over Thread on an ESP32-C6. 78 × 63 mm from the door. The CAD passes 40 fit / motion / strength / printability checks, the PCB is generated, routed and DRC-checked in KiCad, and the firmware builds (the low-power Thread build that the battery life depends on is still to do); none of it is built and tested on a door yet.

<img src="images/v5_cutaway.png" width="640" />

<br>

## 🌀 Single servo, key turns freely

Without help, turning the key or the thumb-turn by hand means back-driving the servo gearbox. Here a **spiral coupling** sits between the servo and the thumb-turn: a pin runs in a 2.75-turn spiral groove under the servo hub. Inside the spiral the key turns freely, and only at its ends does the servo drive the lock. After every movement the servo backs off into the spiral, counted by a small hall sensor on the RX pin. It uses **one servo, has nothing to calibrate, and the V3 PCB is unchanged**. The case is 82 × 85 mm.

<img src="images/lock_operation.gif" width="760" />

<img src="images/lock_cutaway.png" width="640" />

See [the single-servo lock guide](3D%20printed%20case/spiral/README.md) for how it works, the other options I considered, parts, wiring, assembly, and the CAD and firmware checks. The two-servo clutch version is on branch `feature/clutch`. The original case (`bottom`, `middle`, `cover_led`) is still in `3D printed case`.

<br>

## 📙 API

Example request to lock the door:

```bash
curl -X POST http://smartlock.local -H 'Content-Type: application/json' -d '{"state":"locked"}'
```

Example request to get the current state:

```bash
curl -X GET http://smartlock.local
```

Example response:

```json
{
  "state": "locked",
  "homekey": true
}
```

`homekey` is `true` while the HomeKey reader (or the external MQTT broker) is connected.

<br>

## 🏠 Homebridge integration

<br>

<p align="center">
<img src="https://homekitnews.com/wp-content/uploads/2019/06/UI-SETTINGS-HOME2-IOS13.jpg" height=300>
</p>

Homebridge allows you to integrate with smart home devices that do not natively support HomeKit. There are over 2,000 Homebridge plugins supporting thousands of different smart accessories.

Homebridge is a lightweight Node.js server you can run on your home network that emulates the iOS HomeKit API. It supports Plugins, which are community-contributed modules that provide a basic bridge from HomeKit to various 3rd-party APIs provided by manufacturers of "smart home" devices.

You have 2 options to integrate the smart lock to your existing Apple HomeKit smart home:

### Home Key (native Apple Home)

<img src="images/homekey_card.JPEG" height=350  align="right">

The lock works with [HomeKey-ESP32](https://github.com/rednblkx/HomeKey-ESP32) by [rednblkx](https://github.com/rednblkx). An ESP32 board with a PN532 NFC module shows up in Apple Home as a native lock with Home Key and Express mode, and it drives this lock over Wi-Fi. The lock firmware has a tiny built-in MQTT broker, so the reader connects straight to it and you don't need a Raspberry Pi, Homebridge or any server.

<img src="images/homekey_flow.gif" width="760" />

See the **[Home Key setup guide](homekey/README.md)** for parts, wiring, the 3D printed reader enclosure, and configuration.

Thanks to [kormax](https://github.com/kormax) for [apple-home-key-reader](https://github.com/kormax/apple-home-key-reader), which the previous Raspberry Pi version was based on and which made Home Key on DIY hardware possible.

<br>

### EspLock

The lock uses the [EspLock](https://github.com/volca/homebridge-esplock) Homebridge plugin to integrate it into the Apple HomeKit ecosystem. Huge thanks to [volca](https://github.com/volca)!

Example configuration, it is possible to use a static IP address or the hostname:

```json
{
  "accessories": [
    {
      "accessory": "EspLock",
      "name": "Front Door",
      "url": "http://smartlock.local"
    }
  ]
}
```

To disable autolock feature, delete the following function from the index.js file:

```js
setTimeout(function () {
  if (currentState == Characteristic.LockTargetState.UNSECURED) {
    self.lockservice.setCharacteristic(
      Characteristic.LockTargetState,
      Characteristic.LockTargetState.SECURED
    );
  }
}, 5000);
```

<br>

## Contributions

🙏 I welcome contributions from the community! If you have any ideas or suggestions, please open an issue or submit a pull request.

<br>

## License

This project is licensed under the MIT License. See LICENSE for more information.

<br>

## 💻 Contact

For any questions or concerns, please open an issue or contact me.
