# v5: self-adhesive, universal, battery powered

A clean-sheet lock, designed end to end: mechanics, PCB and firmware. It sticks to the door with 3M VHB tape, fits most thumb-turn cylinders, runs on a rechargeable pouch cell and shows up as a native **Matter door lock** (Apple Home, Google Home, SmartThings, Home Assistant). The key always turns freely, thanks to the spiral coupling from the single-servo branch.

| | Where |
| :-- | :-- |
| Mechanics (parametric CAD, STLs, checks, renders) | [`3D printed case/v5`](../3D%20printed%20case/v5) |
| PCB (generated in KiCad 9, routed, DRC, Gerbers, BOM, pick and place) | [`PCB/v5`](../PCB/v5) |
| Firmware (ESP32-C6, Arduino + esp-matter) | [`code/v5`](../code/v5) |
| Motion logic, shared with the V3 firmware and its simulation | [`code/smart_lock/motion.h`](../code/smart_lock/motion.h), [`code/tests/motion`](../code/tests/motion) |

![v5, cut open](../images/v5_cutaway.png)

## In one table

| | Single servo + spiral (USB) | **v5** |
| :-- | :-- | :-- |
| Size | 82 × 85 mm + the door's escutcheon | **78 × 63 mm from the door** (rosette door; 56 mm on a flush cylinder) |
| Mounting | door tab, screws | **self-adhesive base, nothing screwed to the door** |
| Fits | one thumb-turn shape (printed adapter) | **wings 4-22 mm thick, up to 46 mm long, 12-22 mm tall; home up / down / left / right** |
| Power | USB cable | **1200 mAh Li-ion pouch, USB-C charging** |
| Drive | MG996R 360° servo | **N20 50:1 gearmotor + steel worm + brass 30T wheel**, self-locking, current-limited |
| Free key | spiral coupling | spiral coupling (same geometry, 2.75 turns) |
| Sensors | knob reed + hub hall | two DRV5032 hall switches (~1 µA together) |
| Radio / smart home | ESP8266 Wi-Fi, HTTP / MQTT | **ESP32-C6, Matter over Thread** |
| Mass | | about 133 g (tape holds 22 cm² ≈ 7 N·m) |

![size](../images/v5_size.png)

## How it goes on the door

1. **Pick the base preset** for your door (`base_rosette`, `base_escutcheon` or `base_flat`). The base is a ring that clears the rosette or escutcheon and gives the tape a flat surface on the door leaf.
2. **Stick the base.** The `install_jig` drops into the base and over the thumb-turn wing, so the base is centred on the cylinder axis while the VHB tape sets (press 30 s, wait 24 h before full load).
3. **Clamp the adapter** onto the wing with its two M3 screw jaws. The `height_gauge` holds it at the right height while you tighten. Put the 5 × 2 mm knob magnet in the pocket that matches the thumb-turn's home position (up, down, left or right).
4. **Twist the case on.** The case slides down over the adapter and locks onto the base with a 25° bayonet. An M3 screw through the side stops it from turning back.
5. **Plug in the pouch, snap the cap on**, pair it in your home app.

![door presets](../images/v5_presets.png)

## Inside

![exploded](../images/v5_exploded.png)

Bottom to top: base, adapter with jaws and follower, spiral hub with the brass worm wheel (on two steel dowels), the drive layer (N20 motor + worm beside the hub, the crescent PCB around it), deck, pouch, cap.

* **Spiral coupling.** The adapter's follower pin runs in a 2.75-turn spiral groove under the hub. The hub only pushes the thumb-turn at the ends of the spiral, so the key turns freely everywhere else. After every move the motor parks the pin back in the middle. This is the verified geometry from `3D printed case/spiral`.
* **Worm drive.** The worm can't be back-driven, so nothing holds the motor still. The DRV8833's current limit (1.33 A) caps the torque at the thumb-turn to about 1.2 N·m.
* **Sensors.** A hall switch on the PCB's underside counts the thumb-turn magnet, which tells the firmware when the door is locked or unlocked, and also counts manual key turns. A second hall switch counts a magnet in the hub, for parking and stall detection. The firmware learns how many turns the lock needs.
* **Electronics.** The ESP32-C6-MINI-1 sits at the board edge with its antenna clear of copper. Around it: DRV8833 (both bridges in parallel), MCP73831 charger, RT9080 LDO, USB-C, a button and an LED with a light pipe. 37 parts, all SMD, both sides.

## The PCB

![PCB, top](../PCB/v5/render_top.png)

A half-disc board, 1.0 mm thick and 2 layers, beside the hub in the drive layer. The ESP32-C6 module sits on the right with its antenna in a copper-free corner. Power, the charger, the motor driver and USB-C are on the left. The two hall switches are on the underside, above their magnets.

Everything is generated from [`layout.py`](../PCB/v5/layout.py) (outline, fixed parts, GPIOs, shared with the CAD) and [`netlist.py`](../PCB/v5/netlist.py) (parts, MPNs, pads to nets):

```bash
cd PCB/v5    # in a KiCad 9 container (pcbnew + kicad-cli)
python3 erc.py && python3 make_board.py place && python3 make_board.py route && python3 make_board.py finish
```

`router.py` is a small 2-layer grid router written for this board, using negotiated congestion. Every net, ground included, is routed as tracks, so the ground pours are a bonus, not a dependency. Freerouting would be the usual tool, but it wasn't available here. Python's hashing randomises it slightly, so track shapes differ between runs. Most runs converge in 10-15 iterations. One stopped at 40 with three motor-driver nets left; the limit is now 80. If `route` reports failed nets, run `place` and `route` again. `finish.py` pours ground on both layers, runs KiCad's DRC and writes the Gerbers, drill file, BOM and pick-and-place to `fab/`. The latest board has about 2100 track segments and 190 vias, about 90 of them ground stitching.

## Battery life (estimated, not measured)

| | per day |
| :-- | :-- |
| 6 movements × ~35 s (drive + park) × ~0.3 A | ~18 mAh |
| ESP32-C6 as a Thread sleepy end device, 5 s poll, light sleep (~0.3 mA average) | ~7 mAh |
| Halls, LDO, charger, battery divider | < 0.2 mAh |
| **Total** | **~25 mAh** |

With ~1000 mAh usable that is **about 6 weeks** at 6 movements a day, and about 4 weeks at 10. Each movement costs as much as about a third of a day idle, so the number of movements decides most of it. Charging is through USB-C on the side of the case.

> **Not there yet in firmware.** The idle figure needs the ESP32-C6 to be a Thread *sleepy* end device with light sleep. The firmware here is built on the stock Arduino Matter libraries, which are compiled as a Thread router (FTD) with the radio always on (~25 mA): **on the pouch that lasts under two days**, so for now it's a bench / USB build. pioarduino's `custom_sdkconfig` can rebuild the libraries as MTD + ICD + light sleep, but its rebuild drops the esp-matter component, so the app doesn't compile (tried). The way there is to build the same app with ESP-IDF + esp-matter directly, using their ICD door-lock settings. The light-sleep code (wake on the button and the thumb-turn hall, Matter commands wake the loop) is already in `main.cpp` behind `CONFIG_PM_ENABLE`.

## Firmware

* Matter **door lock** endpoint (deadbolt) plus a **power source** cluster with the battery level, built on Arduino-ESP32 3.x (pioarduino) with esp-matter.
* Lock / unlock commands from any Matter controller, state reports for key turns by hand (source "manual"), a **LockJammed** alarm when the hub stalls before the end.
* Button: short press locks or unlocks; hold 6 s to forget the learned turns; hold 12 s to leave the Matter fabric. The pairing code is printed on the serial port.
* `motion.h` is the same controller as V3: drive until the thumb-turn arrives, park the pin back in the spiral, learn the turns, detect jams. `MOTION_DEFAULT_REV_MS` is now overridable, because the worm turns the hub in ~5 s instead of 1.2 s.
* Light sleep (compiled only with `CONFIG_PM_ENABLE`, see the battery section): level interrupts on the button and the thumb-turn hall wake the CPU, and Matter commands wake the loop directly.

```bash
cd code/v5 && pio run -t upload      # ESP32-C6-MINI-1-N4 (4 MB), pairing code on the serial port
```

## What was checked, and how

| Check | Tool | Result |
| :-- | :-- | :-- |
| Every pair of parts, 3 door presets × spiral start / middle / end | `checks.py` (manifold3d) | no overlaps |
| Spiral: the pin runs clear over 2.75 turns, is blocked 15° past both ends, walls ≥ 1.2 mm | `checks.py` | OK, 1.6 mm walls |
| The key turns two full turns with the motor parked; the hub sweeps the whole spiral | `checks.py` | OK |
| Universal range: 18 wing sizes, 4 home positions | `checks.py` | OK |
| Assembly order: base → adapter → case (twist) → pouch → cap; bayonet locks | `checks.py` | OK on all 3 presets |
| Hall sensors: on-axis field of each magnet, cross-talk between them, hub magnet phase vs firmware | `checks.py` (disc + dipole model) | 27 mT / 194 mT vs ~5 mT needed; cross-talk < 0.05 mT; phase 135° = firmware |
| Tape: shear from motor torque, peel from the weight | `checks.py` | 7.3 / 6.1 / 10.5 N·m vs 1.2 N·m |
| Printability in the export orientation (no sloped overhangs) | `checks.py` | all parts OK |
| Strength along the torque path at the current limit: pin, follower, dowels, bayonet lug, brass teeth | `checks.py` | all below limits (teeth 82 of 100 MPa) |
| Schematic rules: every net connected, decoupling, strapping pins, ADC pins, USB CC resistors, DRV8833 paralleling | `PCB/v5/erc.py` | OK |
| PCB: KiCad DRC (clearance 0.15 mm, edge 0.3 mm, antenna keep-out), unconnected items | `kicad-cli pcb drc` | **0 errors, 0 unconnected.** Accepted and listed by `finish.py`: 5 items inside the USB-C footprint itself (its locating holes are 0.19 mm from its own pads; its shell reaches the edge on purpose) |
| Motion logic: learning, parking, 300 random motor / key operations, jams, fresh install | `code/tests/motion/run.sh` | ALL OK |
| Firmware builds | PlatformIO (pioarduino, Arduino-ESP32 3.3) | builds: RAM 42 %, flash 76 % of the 3 MB app partition. Sleepy build: does not compile (see battery) |

All 40 mechanical checks pass with `python lock.py` in `3D printed case/v5` (it exports the STLs, then runs the checks). The PCB rebuilds from scratch with `make_board.py place / route / finish` in a KiCad 9 container.

## Not verified (needs a prototype)

| | |
| :-- | :-- |
| Torque of your cylinder | The most important unknown. Measure it with a lever and a luggage scale. Stiff doors need the current limit raised (R on ISENSE); easy ones can use a 30:1 motor and move ~1.7× faster. |
| Speed | Estimated ~20 s until the door is locked, ~35 s including parking. That is the price of a small motor through a self-locking worm. |
| Battery life | Estimated above. Light sleep with Thread polling must be measured. |
| Low-power firmware | Needs the ESP-IDF + esp-matter build described in the battery section. |
| Tape on your door | VHB needs a clean, smooth, non-porous surface. Painted wood and textured plastic are less reliable. |
| PCB | Generated and routed by script; DRC-clean is not the same as reviewed. Check the footprints of J1, J2 and SW1 against the parts you buy. |
| Matter | DIY devices aren't certified. They pair with a warning but work. Thread needs a border router at home (HomePod mini, Apple TV, Nest Hub, …). |

## Bill of materials (besides the PCB)

| Part | Note |
| :-- | :-- |
| N20 gearmotor 50:1, 6 V type (runs at 3.7 V) | about 370 rpm no-load at 3.7 V |
| Steel worm, module 0.6, Ø 3 mm bore | on the N20's 3 mm D-shaft (a drop of retaining compound) |
| Brass worm wheel, module 0.6, 30 teeth, Ø 3 mm bore | pinned to the hub with 2 × Ø 2 mm steel dowels (press fit) |
| Steel shaft Ø 3 mm and pin Ø 3 mm | hub axle, spiral follower pin |
| 1S Li-ion pouch 603450 with protection board | 1200 mAh; crimp a JST SH 2-pin (1.0 mm) plug on, the board's J2 |
| JST SH 2-pin plug for the motor leads | J3 |
| Magnets N52: 5 × 2 mm (knob), 3 × 2 mm (hub) | |
| 2 × M3 screws for the jaws, 1 × M3 lock screw | |
| 3M VHB tape (4910 or 5952), ~25 cm² | |

The PCB BOM and pick-and-place files for assembly are in `PCB/v5/fab`.
