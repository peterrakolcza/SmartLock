"""Shared PCB description for the v5 board: outline, fixed placements, GPIO map.

Used by the case CAD (3D printed case/v5/lock.py: clearances, sensor positions) and by the board generator
(PCB/v5/make_board.py). Coordinates are mm in the lock's frame: origin on the lock axis, +y up, seen from the cap
side (the board's top side faces the cap, its bottom side faces the spiral hub). Rotations are counter-clockwise.

The board is a crescent: it shares the drive layer with the worm wheel and the motor, so the lock has no separate
electronics layer. The two hall switches on the bottom side look straight down at the hub magnet and the thumb-turn
magnet.

After `make_board.py place`, placement.json holds every part's final position (the passives are placed
automatically); the case CAD uses it when present.
"""

import json
import math
from pathlib import Path

THICKNESS = 1.0
BORE_R = 37.3            # inside of the case
EDGE_CLEAR = 0.5
CUT_Y = -11.6            # straight edge above: clear of the worm wheel
R = BORE_R - EDGE_CLEAR
SENSOR_ANGLE = -130.0    # both hall switches sit on this ray (clear of the ESP32's antenna keep-out)
HUB_HALL_R = 18.0
KNOB_HALL_R = 27.5


def outline(points=72):
    a0 = math.degrees(math.asin(CUT_Y / R))
    a1 = 180.0 - a0
    pts = []
    for i in range(points + 1):
        a = math.radians(a1 + (360.0 + a0 - a1) * i / points)
        pts.append((R * math.cos(a), R * math.sin(a)))
    return pts


def _polar(r, a):
    return (round(r * math.cos(math.radians(a)), 2), round(r * math.sin(math.radians(a)), 2))


# Parts whose position the mechanics decide.
# name: (x, y, rotation, side, body (w, h, height), body centre offset (dx, dy) from the footprint origin, footprint, value)
FIXED = {
    # antenna (bottom of the module after the 180 deg turn) at the arc, its keep-out mostly outside the board
    "U1": (14.0, -19.35, 180, "top", (13.3, 16.7, 2.4), (0.0, -2.7), "RF_Module:ESP32-C6-MINI-1", "ESP32-C6-MINI-1-N4"),
    "U5": (*_polar(HUB_HALL_R, SENSOR_ANGLE), 0, "bottom", (2.9, 1.6, 1.12), (0, 0), "Package_TO_SOT_SMD:SOT-23", "DRV5032 unipolar (hub)"),
    "U6": (*_polar(KNOB_HALL_R, SENSOR_ANGLE), 0, "bottom", (2.9, 1.6, 1.12), (0, 0), "Package_TO_SOT_SMD:SOT-23", "DRV5032 unipolar (thumb-turn)"),
    # opening towards the case wall (-y), the plug's shell sits 0.5 mm past the board edge
    "J1": (-14.0, -30.3, 0, "top", (8.9, 9.0, 3.2), (0, 0.29), "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", "USB-C"),
    "SW1": (*_polar(34.3, -26.5), 65, "top", (3.5, 2.9, 1.35), (0, 0), "Button_Switch_SMD:SW_SPST_EVQP7A", "side button (side push)"),
    "D1": (-22.5, -24.5, 0, "top", (1.6, 0.8, 0.6), (0, 0), "LED_SMD:LED_0603_1608Metric", "status LED"),
}
# The PCB rests on ledges in the case and is held down by posts on the deck at these points (kept free of parts)
CLAMPS = [(round(35.6 * math.cos(math.radians(a)), 2), round(35.6 * math.sin(math.radians(a)), 2)) for a in (-160.0, -75.0, -45.0)]
CLAMP_R = 2.2
ANTENNA_KEEPOUT = (14.0 - 21.6, -19.35 - 26.0, 14.0 + 21.6, -19.35 - 5.6)   # x0, y0, x1, y1 (world)

GPIO = {
    "VBAT_SENSE": 0, "ISENSE": 1, "CHG_STAT": 2, "MOTOR_FAULT": 3,
    "BUTTON": 9,            # also the boot strap: hold while plugging in USB = download mode
    "USB_DM": 12, "USB_DP": 13,
    "MOTOR_IN1": 18, "MOTOR_IN2": 19, "MOTOR_SLEEP": 20,
    "HALL_HUB": 21, "HALL_KNOB": 22, "LED": 23,
}


def placement():
    """Final placement from the board generator if it has run, else the fixed parts only."""
    f = Path(__file__).parent / "placement.json"
    if f.exists():
        return json.loads(f.read_text())
    return {k: dict(x=v[0], y=v[1], rot=v[2], side=v[3], body=v[4], offset=v[5]) for k, v in FIXED.items()}


def hall(name):
    return FIXED[name][:2]
