# v5: if I could redesign everything

A clean-sheet proposal. It keeps what has already proven itself in this project and changes everything else:

- **Kept:** the door mount, the thumb-turn adapter, the spiral coupling, self-learning and jam detection.
- **Changed:** the motor, the electronics, the power supply, the connectivity and the case.

This is a **concept**. The packaging is checked in CAD (`concept.py`), but there is no PCB layout and no v5 firmware yet, and the motor and battery numbers are estimates.

![v5 concept, cut open](../images/v5_cutaway.png)

## In one table

| | Today (single servo + spiral) | **v5** |
| :-- | :-- | :-- |
| Size | 82 × 85 mm, USB powered | **78 × 71 mm including batteries** |
| Power | USB cable to the door | **4 × AAA (~3-4 months, estimated), or 18650 + USB-C charging (~1 year, +8 mm)** |
| Motor | MG996R 360 servo, 37 mm tall, speed only | **N20 gearmotor lying flat + brass worm 40:1**: self-locking, quiet, current-limited |
| Free key | spiral coupling | spiral coupling (unchanged) |
| Position sensing | knob reed + hub hall pulses | **AS5600 absolute encoder on the hub** + low-power knob hall switch + motor current |
| MCU / radio | ESP8266, Wi-Fi only | **ESP32-C6**: Wi-Fi 6, **Thread**, BLE |
| Smart home | HTTP / MQTT, HomeKit via the HomeKey reader | **Matter door lock**: Apple Home, Google, SmartThings and Home Assistant without bridges; Wi-Fi + MQTT kept for USB-powered installs |
| Home Key | separate HomeKey-ESP32 reader | the same separate reader, linked with a Home automation |
| PCB | V3 (round, 78 mm) | new round 74 mm board, about 20 parts |

![size](../images/v5_size.png)

## What I would change, and why

### 1. Motor: a flat gearmotor and a worm instead of a hobby servo

The servo is the biggest part of the lock: 37 mm tall, standing upright, with the PCB stacked on its back. It is also a black box. You can set its speed, but you can't read its position or current, and it can't stop itself in a defined way.

The v5 drive:

- **N20 gearmotor, lying flat beside the hub.** It is only 12 mm tall, so the whole drive fits in one layer.
- **A bought brass worm and a POM worm wheel (module 0.5, 40:1) on top of the spiral hub.** Printed teeth would be overloaded at this torque; a bought set is stronger and cheap.
- **The worm is self-locking.** Nothing back-drives the motor, and the spiral already takes care of letting the key turn.
- **An H-bridge with current limiting (DRV8871).** The current limit **caps the output torque**, so a jam can't strip a gear, and the current tells the firmware when the motor stalls.

Estimate for an N20 30:1 at 6 V (check the datasheet of the motor you buy): **~25 rpm, ~0.9 N·m at stall, ~8 s for a two-turn lock**. A 50:1 motor gives ~1.4 N·m at ~15 rpm. Measuring how hard your cylinder is to turn decides which one to use (see the plan below).

### 2. Keep the spiral coupling

The spiral is the best part of the current design. The key turns freely, nothing has to engage, and it works with any thumb-turn cylinder. That is unlike Nuki, which needs a special emergency-function cylinder. v5 puts the worm wheel straight on top of the spiral disc.

### 3. Sensors: know the real position instead of counting pulses

- **AS5600 magnetic encoder** on the PCB, directly above a magnet on the hub shaft. It reads the absolute hub angle to 0.1°, and the firmware counts the turns. Parking becomes exact, and the hub magnet placement and hall pulse counting go away. It is only powered while the motor runs (it draws ~6 mA).
- **Knob hall switch (DRV5032, ~0.5 µA)** instead of the reed, for the thumb-turn's home position and for counting key turns by hand.
- **Motor current** for stall and jam detection, in addition to the encoder speed.
- **Optional door sensor** (a magnet on the frame), for auto-lock when the door closes and a "door left open" warning.

### 4. Electronics: one small board around the mechanism

| Block | Part | Why |
| :-- | :-- | :-- |
| MCU + radio | ESP32-C6-MINI-1 | Wi-Fi 6, Thread 802.15.4 and BLE on one chip. Native USB for flashing, so no USB-UART chip. |
| Motor | DRV8871 | 3.6 A H-bridge with a current limit set by one resistor, so the torque cap is in hardware. |
| Encoder | AS5600 | Absolute angle over I²C, sits on the axis under the PCB. |
| Knob sensor | DRV5032 | Hall switch at 0.5 µA. |
| Power | 4 × AAA → 3.3 V LDO (low quiescent current), motor straight from the batteries | Simple, with no boost converter. (18650 variant: charger + boost to 6 V.) |
| UI | 4 LEDs + diffuser, side button (flexure in the case), USB-C | Same look as today. |

That is about 20 parts on a round 74 mm board, with the encoder underneath on the axis and the ESP32 antenna at the edge. Parts cost is roughly €20-30 including the motor and worm set, but that's an estimate.

### 5. Connectivity and firmware

- **Matter "Door Lock" over Thread**, built with ESP-IDF + esp-matter. One device then works natively with Apple Home (via a HomePod or Apple TV as Thread border router), Google, SmartThings and Home Assistant. Thread lets the radio sleep between polls, which is what makes batteries viable.
- **Wi-Fi mode** for USB-powered installs: the same firmware with the existing HTTP API and the built-in MQTT broker for the HomeKey-ESP32 reader.
- **Home Key** isn't part of Matter today. Keep the separate HomeKey-ESP32 reader and link it with a Home automation ("when the reader unlocks, unlock the front door"). The CSA's **Aliro** standard is meant to bring phone/watch keys to Matter locks; if and when it's usable on DIY hardware it would replace the second device.
- **Motion logic:** the current `motion.h` carries over (drive, park, learning, jam). Its tests and simulation move with it, and it gets simpler with an absolute encoder.
- **Auto-lock**, battery level in the app, OTA updates through Matter.

### 6. Case

- **One printed case** keeps the original floor and door tab, so it mounts to the door exactly as today. A chassis plate carries the motor, the worm's end bearing, the hub shaft bushing and the knob sensor. The PCB sits on ledges, the batteries go on top, and the cap snaps on with a bayonet for battery changes.
- **Parts:** case, adapter, follower, spiral hub with worm wheel, chassis and cap (6 printed), plus the bought worm set, gearmotor, PCB, batteries and a 3 mm pin.

## Battery estimate (not measured)

| | per day |
| :-- | :-- |
| 10 movements × ~10 s (drive + park) × ~0.4 A at ~5 V | ~20 mWh |
| ESP32-C6 as a Thread sleepy end device, ~100 µA average (strongly depends on the poll interval) | ~8 mWh |
| **Total** | **~28 mWh** |

- **4 × AAA alkaline:** about 3 Wh usable under motor load, so **~3-4 months**.
- **18650 Li-ion (11 Wh) with USB-C charging:** **~1 year**. It needs a boost converter and makes the case 8 mm taller.

The real idle current has to be measured on a prototype.

## Checked in CAD

`python concept.py` (needs `manifold3d` and `trimesh`) places real component envelopes. These are the N20 gearmotor, the worm, the 40-tooth wheel, the spiral hub, the PCB parts, 4 × AAA and the case. The adapter, follower and spiral are the ones already verified in `3D printed case/spiral`. It then checks:

* **Fit:** no two parts overlap at the start, middle and end of the spiral. The worm–wheel mesh is the only intended contact.
* **Key by hand:** with the motor parked, the thumb-turn turns two full turns without hitting anything.
* **Hub:** it turns through the whole spiral without touching the motor, chassis or case.
* **Assembly:** the adapter, the drive module (chassis, motor, worm, hub), the PCB and the battery pack each go straight down into the case.
* **Envelope:** **78.2 × 70.7 mm** with a 23.5 mm thumb-turn.

![exploded](../images/v5_exploded.png)

## Risks and open questions

| | |
| :-- | :-- |
| Torque margin | The most important unknown. Measure your cylinder first. Stiff or misaligned doors may need the 50:1 motor or a two-start worm. |
| Speed | 8-13 s for two turns, slower than the servo (~3 s). This is the price of a small motor with a self-locking worm. |
| Battery life | Estimated, not measured. Thread polling and the number of movements a day dominate. |
| Matter | DIY devices aren't certified. They pair with a warning but work. Thread needs a border router at home. |
| Wear | The worm set is bought metal/POM. The printed spiral and the follower are the parts to watch. |

## How I would build it

1. **Measure the lock.** Put a lever and a luggage scale on the thumb-turn and record the peak torque to lock and unlock. That number decides the motor ratio.
2. **Drive test rig.** Print the hub with the worm wheel seat and a motor bracket, and use an off-the-shelf DRV8871 board plus an ESP32-C6 DevKit. Check torque, speed and current at stall.
3. **Port the firmware.** Move `motion.h` to ESP-IDF, add the AS5600 and current sensing, and build the Matter door lock on the DevKit over Thread. Measure the idle current.
4. **PCB rev A**, from the schematic blocks above.
5. **Integration:** print the case, mount it on the door, run a battery test over a few weeks.

## Files

| | |
| :-- | :-- |
| `concept.py` | parametric packaging model + checks |
| `render.py` | the images on this page |
