# ⚡ V4 low power board (ESP32-C3, battery): design

> **Status: experimental design.** The schematic, parts and pin map are below. The board has not been laid out, built or measured yet. The battery-life figures are estimates from Espressif's published numbers. Build the [perfboard prototype](#prototype-before-ordering-a-pcb) and measure the current before ordering PCBs.

The V3 board can't run on batteries. The ESP8266 has no usable sleep mode while it stays connected to Wi-Fi, the AMS1117 regulator alone draws ~5 mA, and the servo is powered all the time. V4 changes three things:

| | V3 (USB) | V4 (battery) |
| :-- | :-- | :-- |
| MCU | ESP-12F (ESP8266) | ESP32-C3-MINI-1 with automatic light sleep while connected to Wi-Fi (DTIM3) |
| Regulator | AMS1117, ~5 mA quiescent | HT7833, 4 µA quiescent, 8.5 V max input |
| Servos | always powered | power switched by a MOSFET, off between movements |
| Programming | 3-pin UART header + buttons | USB-C, using the C3's native USB (no USB-UART chip) |
| Clutch servo | RX pin of the programming header | own 3-pin header |

The board has about 25 parts, all common JLCPCB / LCSC stock, so it is no more complex than V3.

## Schematic (net list)

```
BATTERY  J5 (JST-PH 2p)  BAT+ ──┬──────────────────────────────▶ VSERVO (servo + pins, J1/J2 pin 2)
                                ├── D2 B5819W ──┐
USB-C    J7 VBUS ───────────────┼── D1 B5819W ──┴── VIN ── C1 10µF ── U2 HT7833 ── 3V3 ── C2 10µF, C3 100nF
         J7 CC1, CC2 ── R1, R2 5.1k ── GND                                    │
         J7 D+ ── GPIO19, D- ── GPIO18                                         └── U1 ESP32-C3-MINI-1 3V3
                                │
BAT+ ── R3 330k ──┬── GPIO0 (ADC, battery sense)
                  ├── R4 100k ── GND
                  └── C4 100nF ── GND

Servo power switch (low side):
  GPIO6 ── R5 100Ω ── Q1 AO3400A gate, R6 100k gate ── GND
  Q1 drain ── SERVO_GND (J1/J2 pin 1), Q1 source ── GND
  C5 470µF / 10V between VSERVO and SERVO_GND, close to the headers

J1 main servo:    1 SERVO_GND, 2 VSERVO, 3 GPIO4 via R7 220Ω
J2 clutch servo:  1 SERVO_GND, 2 VSERVO, 3 GPIO5 via R8 220Ω
J3 reed sensor:   GPIO7, GND        (internal pull-up)
J4 side button:   GPIO3, GND        (internal pull-up)
J6 LED ring:      3V3 ─ LED1-4 ─ R9-R12 66Ω ─ Q2 2N7002 drain, Q2 gate ─ R13 10k ─ GPIO10, R14 100k ─ GND
SW1 BOOT:         GPIO9 to GND, R15 10k pull-up to 3V3
SW2 RESET:        EN to GND, R16 10k pull-up to 3V3, C6 1µF to GND
```

The pin map matches `board.h` (`#if defined(ESP32)`): servo 4, clutch 5, servo power 6, reed 7, button 3, LED 10, battery ADC 0.

The side button is deliberately not GPIO9. Holding it at power-on resets the learned turns, and on GPIO9 that would put the chip into download mode instead.

## Bill of materials

| Ref | Part | Package | Qty |
| :-- | :-- | :-- | :-: |
| U1 | ESP32-C3-MINI-1-N4 | module | 1 |
| U2 | HT7833 (Holtek), 3.3 V LDO, 4 µA Iq | SOT-89 | 1 |
| Q1 | AO3400A N-MOSFET (servo power) | SOT-23 | 1 |
| Q2 | 2N7002 N-MOSFET (LED ring, same as V3) | SOT-23 | 1 |
| D1, D2 | B5819W Schottky | SOD-123 | 2 |
| J7 | USB-C 16 pin receptacle (USB 2.0) | SMD | 1 |
| J5 | JST-PH 2 pin, battery | THT | 1 |
| J1, J2 | 3 pin header 2.54 mm, servos | THT | 2 |
| J3, J4, J6 | 2 pin header 2.54 mm | THT | 3 |
| SW1, SW2 | tactile switch (BOOT, RESET; V3 used PTS645) | SMD | 2 |
| C5 | 470 µF 10 V electrolytic | radial / SMD | 1 |
| C1, C2 | 10 µF | 0805 | 2 |
| C3, C4 | 100 nF | 0402 | 2 |
| C6 | 1 µF | 0402 | 1 |
| R1, R2 | 5.1 kΩ | 0805 | 2 |
| R3 | 330 kΩ 1 % | 0805 | 1 |
| R4, R6, R14 | 100 kΩ 1 % | 0805 | 3 |
| R5 | 100 Ω | 0805 | 1 |
| R7, R8 | 220 Ω | 0805 | 2 |
| R9 - R12 | 66 Ω (LED ring, as V3) | 0805 | 4 |
| R13, R15, R16 | 10 kΩ | 0805 | 3 |
| LED1 - LED4 | white 0805 (as V3) | 0805 | 4 |

Search JLCPCB's parts library by part number. The ESP32-C3 module, AO3400A, 2N7002, B5819W, the resistors and the capacitors are all basic or common extended parts.

## Batteries

Use **4 × AA NiMH (e.g. Eneloop, ~2000 mAh)** in a standard 4 × AA flat holder with leads.

* 4.8 V nominal suits the MG996R and SG90 (the V3 board fed them 5 V from USB), so the servos run directly from the battery with no boost converter.
* NiMH cells have low internal resistance. A stalling servo draws 1.5-2.5 A, and alkaline cells sag enough under that load to brown out the ESP32. NiMH stays above the ~3.9 V the regulator path needs.
* The firmware reports the battery level to Apple Home through the HomeKey reader. Turn on *Proxy Battery* in the reader's HomeKit settings.

## Power budget (estimate)

| Consumer | Average current |
| :-- | :-- |
| ESP32-C3, Wi-Fi connected, automatic light sleep, DTIM3 | ~1.0-1.5 mA (Espressif's figure for the C3) |
| HTTP server + MQTT keep-alive wake-ups | ~0.2-0.5 mA |
| Battery divider (430 kΩ) + LDO quiescent | ~0.015 mA |
| Servos, 10 movements a day, ~1.2 A for ~2.5 s each | ~0.35 mA |
| LED ring, 3 s after each change | ~0.01 mA |
| **Total** | **~1.6-2.4 mA → 2000 mAh lasts ~5-7 weeks** |

Wi-Fi reconnects, a busy network (more broadcast traffic wakes the radio) or a weak signal all push this up. Check it before relying on it:

1. Put a multimeter (mA range) or a USB power meter in series with the battery.
2. The idle current should average below 3 mA. If it stays at 15-25 mA, light sleep is not active. The serial log shows `Power management: automatic light sleep enabled` when the battery env is built correctly.

## Prototype before ordering a PCB

All of this can be built on perfboard:

* **ESP32-C3 SuperMini** board (~2 €). Remove its red power LED, which draws ~1-2 mA all the time. Feed **3.3 V directly into its 3V3 pin** from an HT7833 breakout, because the SuperMini's own regulator is not rated for a fresh 4 × AA pack.
* One AO3400A on a SOT-23 adapter as the servo ground switch, plus the 100 Ω / 100 kΩ gate resistors.
* The 330 k / 100 k battery divider into GPIO0.
* The original reed switch, button and LED ring.

Flash with `pio run -e smartlock-battery -t upload` (from `code/smart_lock`).

## Laying out the PCB

The V3 board was drawn in EasyEDA (`PCB/easyEDA files`). For V4, draw the net list above in EasyEDA and keep the module's antenna end over the board edge with no copper underneath. Route the servo ground (Q1) and VSERVO as wide traces (≥ 1 mm), with C5 next to the servo headers.
