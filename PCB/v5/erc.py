"""Electrical rule check for netlist.py (runs on the host, no KiCad needed).

    python erc.py
"""

import sys

import netlist as n
from layout import GPIO

STRAPS = {4, 5, 8, 9, 15}           # ESP32-C6 strapping pins
problems, notes = [], []
nets = n.nets()

# 1. every net has at least two connections, except deliberate single-ended ones
single_ok = set()
for net, pins in nets.items():
    if len(pins) < 2 and net not in single_ok:
        problems.append(f"net {net} has only {pins}")

# 2. every IC's power pins are on a power net, every IC has its decoupling caps
supplies = {"U1": ["3V3"], "U2": ["VBAT"], "U3": ["VBUS", "VBAT"], "U4": ["VBAT", "3V3"], "U5": ["3V3"], "U6": ["3V3"]}
caps = {ref: (val, pads) for ref, (_, val, _, pads, _) in n.PARTS.items() if ref.startswith("C")}
for ic, rails in supplies.items():
    for rail in rails:
        local = [c for c, (val, pads) in caps.items() if rail in pads.values() and "GND" in pads.values() and n.PARTS[c][4] == ic]
        if not local:
            problems.append(f"{ic}: no decoupling capacitor on {rail} placed next to it")

# 3. straps: GPIO8 pulled up, GPIO9 = button with pull-up (download mode when held), no sensor on 4 / 5 / 15
for name, gpio in GPIO.items():
    if gpio in STRAPS and name != "BUTTON":
        problems.append(f"{name} on strapping pin GPIO{gpio}")
if not any("STRAP_IO8" in pads.values() and "3V3" in pads.values() for _, _, _, pads, _ in n.PARTS.values()):
    problems.append("GPIO8 has no pull-up")

# 4. ADC pins: ESP32-C6 ADC1 is on GPIO0-6
for name in ("VBAT_SENSE", "ISENSE"):
    if GPIO[name] > 6:
        problems.append(f"{name} is not on an ADC pin")
# ISENSE: 0.2 V chopping threshold at the max current, well inside the ADC range
rsense = 0.15
notes.append(f"motor current limit (DRV8833 chops at 200 mV): {0.2 / rsense:.2f} A total")
# battery divider at 4.2 V must stay below the ADC's 11 dB range (~3.1 V)
notes.append(f"battery sense at 4.2 V: {4.2 / 2:.2f} V (ADC max ~3.1 V), divider current {4.2 / 2e6 * 1e6:.1f} uA")
# charger current: 1000 / RPROG mA
notes.append(f"charge current: {1000 / 2000 * 1000:.0f} mA (RPROG 2 k)")

# 5. USB: both D+ and D- pads tied, CC pull-downs present
for net in ("USB_DP", "USB_DM"):
    if len([p for p in nets[net] if p.startswith("J1")]) != 2:
        problems.append(f"{net}: both USB-C rows must be connected")
for cc in ("CC1", "CC2"):
    if not any(cc in pads.values() and "GND" in pads.values() and val == "5.1k" for _, val, _, pads, _ in n.PARTS.values()):
        problems.append(f"{cc} needs 5.1 k to GND (5 V from USB-C chargers)")

# 6. DRV8833 parallel mode: AIN1/BIN1, AIN2/BIN2, AOUT1/BOUT1, AOUT2/BOUT2 paired
drv = n.PARTS["U2"][3]
for a, b in (("16", "9"), ("15", "10"), ("2", "7"), ("4", "5")):
    if drv[a] != drv[b]:
        problems.append(f"DRV8833 parallel mode: pads {a} and {b} differ")

# 7. Hall outputs are push-pull (DRV5032FB): no pull-ups needed; button / fault / stat pulled up
for net in ("BUTTON", "MOTOR_FAULT", "CHG_STAT"):
    if not any(net in pads.values() and "3V3" in pads.values() for _, _, _, pads, _ in n.PARTS.values()):
        problems.append(f"{net} needs a pull-up (open drain)")

print("ERC")
for line in notes:
    print("  note:", line)
for p in problems:
    print("  FAIL", p)
print(f"  {len(nets)} nets, {len(n.PARTS)} parts: {'OK' if not problems else 'PROBLEMS'}")
sys.exit(1 if problems else 0)
