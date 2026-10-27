"""Clean-sheet smart lock concept (v5): packaging study.

This is a concept, not a print-ready design: it places real component envelopes (gearmotor, worm, worm wheel, spiral
hub, PCB parts, 4 x AAA) in a case and checks that everything fits, moves and assembles. The thumb-turn adapter,
follower and spiral are the verified ones from `3D printed case/spiral`.

    pip install manifold3d trimesh
    python concept.py
"""

import itertools
import math
import sys
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, JoinType, Manifold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "3D printed case" / "spiral"))
import lock as s  # noqa: E402  (spiral geometry, adapter, follower, helpers)

cube, cyl, ring, polar = s.cube, s.cyl, s.ring, s.polar

A = s.L.A                  # adapter top, same door / thumb-turn as the spiral version

# ---------------------------------------------------------------------------------------------------- drive
# Bought worm set (brass / steel worm, POM wheel), module 0.5, single start: printed teeth would be overloaded
WHEEL_MODULE = 0.5
WHEEL_TEETH = 40           # 40:1
WORM_PITCH_R = 3.0
WHEEL_FACE = 5.0
MOTOR = dict(gearbox=(9.0, 10.0, 12.0), can=(15.0, 10.0, 12.0), shaft=3.0)   # N20 gearmotor lying flat: length, width, height
WHEEL_PITCH_R = WHEEL_MODULE * WHEEL_TEETH / 2
CENTRE = WHEEL_PITCH_R + WORM_PITCH_R          # worm axis distance from the lock axis
SPIRAL_TOP = s.L.hub0 + s.GROOVE_DEPTH + 1.7   # spiral disc: groove + floor
WHEEL_MID = SPIRAL_TOP + 0.5 + MOTOR["gearbox"][2] / 2   # motor sits just above the spiral disc
WORM_X = (-8.0, 6.5)                           # worm along x, the mesh is at x = 0; the gearbox starts clear of the wheel

# ---------------------------------------------------------------------------------------------------- electronics
PCB_D = 74.0
PCB_T = 1.6
BATTERY = dict(cells=4, d=10.5, length=44.5)   # AAA
WALL = 1.8
BORE = PCB_D / 2 + 0.3
CASE_R = BORE + WALL
CAP_T = 1.5


class Z:
    wheel0 = WHEEL_MID - WHEEL_FACE / 2
    wheel1 = WHEEL_MID + WHEEL_FACE / 2
    motor0 = WHEEL_MID - MOTOR["gearbox"][2] / 2
    motor1 = WHEEL_MID + MOTOR["gearbox"][2] / 2
    plate0 = motor1 + 0.6
    plate1 = plate0 + 2.0
    magnet1 = plate1 + 1.5          # diametric magnet on the hub shaft
    pcb0 = magnet1 + 1.0 + 1.5      # AS5600 (1.5 mm) on the PCB underside, 1 mm above the magnet
    pcb1 = pcb0 + PCB_T
    parts1 = pcb1 + 2.6             # ESP32-C6-MINI-1 2.4 mm
    battery0 = parts1 + 0.4
    battery1 = battery0 + 1.0 + BATTERY["d"]
    top = battery1 + 0.4


# ---------------------------------------------------------------------------------------------------- parts
def hub(h=0.0):
    """Spiral disc (verified groove from the spiral version) + worm wheel + shaft with the encoder magnet."""
    disc = cyl(s.HUB_R, s.L.hub0, SPIRAL_TOP)
    disc -= s.spiral_groove(s.L.hub0 - 1, s.L.hub0 + s.GROOVE_DEPTH)
    neck = cyl(9.0, SPIRAL_TOP - 0.01, Z.wheel0 + 0.01)
    root_r = WHEEL_PITCH_R - 1.25 * WHEEL_MODULE
    wheel = cyl(root_r, Z.wheel0, Z.wheel1)
    tooth = cube(-0.5 * WHEEL_MODULE * 1.4, 0.5 * WHEEL_MODULE * 1.4, root_r - 0.1, WHEEL_PITCH_R + WHEEL_MODULE, Z.wheel0, Z.wheel1)
    for i in range(WHEEL_TEETH):
        wheel += tooth.rotate((0, 0, 360.0 * i / WHEEL_TEETH))
    shaft = cyl(2.5, Z.wheel1 - 0.01, Z.plate1 + 0.3) + cyl(3.0, Z.plate1 + 0.3, Z.magnet1)   # 6 x 2.5 diametric magnet on top
    return (disc + neck + wheel + shaft).rotate((0, 0, h))


def worm():
    r_out = WORM_PITCH_R + WHEEL_MODULE
    w = Manifold.cylinder(WORM_X[1] - WORM_X[0], r_out, circular_segments=32).rotate((0, 90, 0)).translate((WORM_X[0], CENTRE, WHEEL_MID))
    return w


def motor():
    gl, gw, gh = MOTOR["gearbox"]
    ml, mw, mh = MOTOR["can"]
    x0 = WORM_X[1] + 0.5
    gearbox = cube(x0, x0 + gl, CENTRE - gw / 2, CENTRE + gw / 2, WHEEL_MID - gh / 2, WHEEL_MID + gh / 2)
    can = cube(x0 + gl, x0 + gl + ml, CENTRE - mw / 2, CENTRE + mw / 2, WHEEL_MID - mh / 2, WHEEL_MID + mh / 2)
    return gearbox + can


def chassis():
    """Plate over the drive: clamps the motor, carries the worm's end bearing, the hub shaft bushing, the knob sensor."""
    plate = cyl(BORE - 0.3, Z.plate0, Z.plate1)
    plate -= cyl(2.75, Z.plate0 - 1, Z.plate1 + 1, 32)                # hub shaft bushing
    for a in (45.0, 135.0, 225.0, 315.0):                              # notches to pass the PCB ledges
        x, y = polar(BORE, a)
        plate -= cyl(3.6, Z.plate0 - 1, Z.plate1 + 1, 24, x=x, y=y)
    # Motor saddle: two cheeks down beside the gearbox, an end bearing for the worm
    gl, gw, gh = MOTOR["gearbox"]
    cheeks = cube(WORM_X[1] + 0.5, WORM_X[1] + 0.5 + gl, CENTRE + gw / 2 + 0.1, CENTRE + gw / 2 + 2.0, Z.motor0, Z.plate0 + 0.01)
    bearing = cube(WORM_X[0] - 3.0, WORM_X[0] - 0.4, CENTRE - 3.0, CENTRE + 3.0, Z.motor0, Z.plate0 + 0.01)
    bearing -= Manifold.cylinder(4, 1.0, circular_segments=16).rotate((0, 90, 0)).translate((WORM_X[0] - 3.5, CENTRE, WHEEL_MID))
    # Knob sensor leg (hall switch beside the adapter magnet, outside the adapter's sweep)
    rx = s.KNOB_REED_R
    leg = cube(rx - 1.5, rx + 2.4, -6.0, 6.0, A - 7.0, Z.plate0 + 0.01)
    # Screw tabs into the case
    part = plate + cheeks + bearing + leg
    for a in (100.0, 220.0, 340.0):
        x, y = polar(BORE - 2.0, a)
        part -= cyl(1.25, Z.plate0 - 1, Z.plate1 + 1, 16, x=x, y=y)
    return part


def pcb():
    board = cyl(PCB_D / 2, Z.pcb0, Z.pcb1)
    top = [
        (cube(-8.2, 8.2, 10.0, 26.6, Z.pcb1, Z.pcb1 + 2.4), "ESP32-C6-MINI-1"),
        (cube(-12.0, -7.0, -6.0, -1.0, Z.pcb1, Z.pcb1 + 1.0), "DRV8871 motor driver"),
        (cube(-35.6, -28.0, -4.5, 4.5, Z.pcb1, Z.pcb1 + 3.2), "USB-C"),
        (cube(29.0, 35.4, -3.0, 3.0, Z.pcb1, Z.pcb1 + 2.5), "side button"),
        (cube(4.0, 10.0, -20.0, -14.0, Z.pcb1, Z.pcb1 + 1.6), "charger / regulator"),
    ]
    for p, _ in top:
        board += p
    board += cube(-2.5, 2.5, -2.5, 2.5, Z.pcb0 - 1.5, Z.pcb0)                 # AS5600 underneath, on the axis
    for a in (45, 135, 225, 315):
        x, y = polar(24, a)
        board += cube(x - 1, x + 1, y - 0.6, y + 0.6, Z.pcb1, Z.pcb1 + 0.8)    # LED ring
    return board


def battery():
    n, d, length = BATTERY["cells"], BATTERY["d"], BATTERY["length"]
    holder = cube(-length / 2 - 4, length / 2 + 4, -n * d / 2 - 1, n * d / 2 + 1, Z.battery0, Z.battery0 + 1.0)
    cells = Manifold()
    for i in range(n):
        y = (i - (n - 1) / 2) * d
        cells += Manifold.cylinder(length, d / 2, circular_segments=32).rotate((0, 90, 0)).translate((-length / 2, y, Z.battery0 + 1.0 + d / 2))
    return holder, cells


def case():
    original = s.from_stl(s.ORIGINAL / "bottom.stl")
    floor = original ^ cyl(BORE + 0.2, -1, 1.0)
    tab = original ^ cube(-50, 50, CASE_R - 0.5, 100, -1, 50)
    root = tab ^ cube(-50, 50, 43.6, 45.0, -1, 50)
    tab += Manifold.hull(root + root.translate((0, -(43.6 - BORE), 0)))
    tube = ring(BORE, CASE_R, 0, Z.top)
    part = floor + tab + tube
    for a in (100.0, 220.0, 340.0):                                         # chassis bosses
        x, y = polar(BORE - 2.0, a)
        boss = cyl(3.4, Z.plate0 - 4.0, Z.plate0, 32, x=x, y=y) ^ cyl(BORE + 0.5, 0, Z.top)
        part += boss - cyl(1.25, Z.plate0 - 5, Z.plate0 + 1, 16, x=x, y=y)
    for a in (45.0, 135.0, 225.0, 315.0):                                   # PCB ledges
        x, y = polar(BORE, a)
        part += (cyl(2.6, Z.pcb0 - 1.5, Z.pcb0, 24, x=x, y=y) ^ cyl(BORE + 0.5, 0, Z.top)) - cyl(BORE - 1.4, 0, Z.top + 1)
    part -= cube(-CASE_R - 1, -BORE + 1, -6.0, 6.0, Z.pcb1 - 0.5, Z.pcb1 + 4.5)  # USB-C
    part -= cube(BORE - 1, CASE_R + 1, -2.0, 2.0, Z.pcb1 + 0.3, Z.pcb1 + 2.2)   # button plunger
    return s.largest(part)


def cap():
    part = cyl(CASE_R, Z.top, Z.top + CAP_T)
    part -= ring(20, 28, Z.top - 1, Z.top + CAP_T + 1)          # LED ring window (diffuser insert)
    part += ring(BORE - 1.2, BORE - 0.2, Z.battery0 + 1.0, Z.top + 0.01)
    return s.largest(part)


def knob_sensor():
    x, _ = polar(s.KNOB_REED_R, 0)
    return cube(x - 0.75, x + 0.75, -1.5, 1.5, A - 5.5, A - 3.5)  # DRV5032 hall switch, SOT-23


def assembly(h=s.FREE_PLAY / 2, k=0.0):
    holder, cells = battery()
    return {
        "case": (case(), "case"),
        "adapter": (s.knob_adapter().rotate((0, 0, k)), "adapter"),
        "follower": (s.follower(k, h), "slider"),
        "pin": (s.pin_model(k, h), "metal"),
        "hub": (hub(h), "hub"),
        "worm": (worm(), "metal"),
        "motor": (motor(), (0.75, 0.6, 0.25)),
        "chassis": (chassis(), "bracket"),
        "knob_sensor": (knob_sensor(), (0.1, 0.1, 0.1)),
        "pcb": (pcb(), (0.1, 0.45, 0.25)),
        "battery_holder": (holder, (0.2, 0.2, 0.22)),
        "batteries": (cells, (0.85, 0.55, 0.15)),
        "cap": (cap(), "case"),
        "thumb_turn": (s.thumb_turn().rotate((0, 0, k)), "metal"),
    }


# ---------------------------------------------------------------------------------------------------- checks
ALLOWED = {frozenset(p) for p in (("adapter", "thumb_turn"), ("follower", "pin"), ("hub", "worm"),   # the mesh
                                  ("worm", "motor"), ("chassis", "knob_sensor"), ("battery_holder", "batteries"))}


def overlap(a, b):
    return (a ^ b).volume()


def checks():
    problems = []
    for h in (0.0, s.FREE_PLAY / 2, s.FREE_PLAY):
        parts = assembly(h=h)
        for (na, (a, _)), (nb, (b, _)) in itertools.combinations(parts.items(), 2):
            if frozenset((na, nb)) in ALLOWED:
                continue
            v = overlap(a, b)
            if v > 0.5:
                problems.append(f"spiral {h / 360:.2f} turns: {na} overlaps {nb} by {v:.1f} mm3")
    static = {n: p for n, (p, _) in assembly().items() if n in ("case", "chassis", "motor", "worm", "pcb", "knob_sensor")}
    # Key turned two turns by hand with the motor parked, hub turning a full spiral with the thumb-turn still
    h_park = s.FREE_PLAY - 135.0 - 720.0
    adapter = s.knob_adapter()
    for kk in range(0, -721, -30):
        for name, part in (("adapter", adapter.rotate((0, 0, kk))), ("follower", s.follower(kk, h_park))):
            for sname, spart in static.items():
                if overlap(part, spart) > 0.5:
                    problems.append(f"key at {kk} deg: {name} hits {sname}")
    for h in np.linspace(0, s.FREE_PLAY, 23):
        hb = hub(h)
        for sname, spart in static.items():
            if sname == "worm":
                continue
            if overlap(hb, spart) > 0.5:
                problems.append(f"hub at {h:.0f} deg hits {sname}")
    # Assembly straight down: adapter, chassis module (chassis + motor + worm + hub), PCB, battery, cap
    module = chassis() + motor() + worm() + hub(135.0)
    holder, cells = battery()
    shell = case()
    knob = s.knob_adapter() + s.follower(0, 135.0) + s.pin_model(0, 135.0)
    for name, part, obstacles in (("adapter", knob, shell), ("drive module", module, shell + knob),
                                  ("PCB", pcb(), shell + module), ("battery", holder + cells, shell + pcb())):
        lowest = part.bounding_box()[2]
        worst = max(overlap(part.translate((0, 0, t)), obstacles) for t in np.arange(0.5, Z.top + 10 - lowest, 1.0))
        if worst > 0.5:
            problems.append(f"{name} can't go in straight from the top ({worst:.1f} mm3)")
    return problems


def drive_estimate():
    # N20 gearmotor 6 V, 30:1 class (check the datasheet of the motor you buy): ~1000 rpm no load, ~0.05 N m stall
    rpm, stall = 1000.0, 0.05   # N20 6 V 30:1 class
    ratio, efficiency = WHEEL_TEETH, 0.45       # single-start brass worm on a POM wheel
    return {"output speed (rpm, no load)": rpm / ratio, "output stall torque (N m)": stall * ratio * efficiency,
            "time for 2 turns (s, ~60 % speed under load)": 2 / (rpm / ratio * 0.6 / 60)}


if __name__ == "__main__":
    print(f"Envelope: {2 * CASE_R:.1f} mm diameter x {Z.top + CAP_T:.1f} mm from the door")
    print(f"  adapter top {A:.1f}, spiral {s.L.hub0:.1f}-{SPIRAL_TOP:.1f}, worm wheel {Z.wheel0:.1f}-{Z.wheel1:.1f}, "
          f"PCB {Z.pcb0:.1f}, batteries {Z.battery0:.1f}-{Z.battery1:.1f}")
    for name, v in drive_estimate().items():
        print(f"  {name:46s} {v:.1f}")
    problems = checks()
    print("\nChecks (fit at 3 spiral positions, key 2 turns, hub full spiral, assembly order):", "OK" if not problems else "")
    for p in problems:
        print("  " + p)
    sys.exit(1 if problems else 0)
