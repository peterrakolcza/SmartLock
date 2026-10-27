"""Verification for lock.py (single servo, spiral coupling): fit, the spiral itself, motion, assembly order,
sensors, clearances, printability.

Run through `python lock.py` (exports first) or on its own: `python checks.py`.
"""

import itertools
import math

import numpy as np

import lock as k

ALLOWED = {
    frozenset(("servo", "horn")),
    frozenset(("thumb_turn", "knob_adapter")),
    frozenset(("pin", "follower")),        # pressed in
    frozenset(("hall", "chassis")),        # sits in its pocket
    frozenset(("reed", "chassis")),
}
LIMIT = 0.5  # mm3
FP = k.FREE_PLAY


def overlap(a, b):
    return (a ^ b).volume()


def clashes(parts, label):
    found = []
    for (na, (a, _, _)), (nb, (b, _, _)) in itertools.combinations(parts.items(), 2):
        if frozenset((na, nb)) in ALLOWED:
            continue
        v = overlap(a, b)
        if v > LIMIT:
            found.append(f"{label}: {na} overlaps {nb} by {v:.1f} mm3")
    return found


def static_fit():
    problems = []
    for h in (0.0, FP / 2, FP):
        problems += clashes(k.assembly(h=h), f"spiral position {h / 360:.2f} turns")
    return problems


def spiral():
    """The pin must run clear in the groove over the whole spiral, and be blocked just past both ends."""
    problems = []
    hub0 = k.hub(0.0)
    worst = 0.0
    for t in np.linspace(0, k.SPIRAL_TURNS, 45):
        h = 360.0 * t
        worst = max(worst, overlap(k.pin_model(0.0, h), k.hub(h)))
    if worst > 0.05:
        problems.append(f"pin rubs in the groove ({worst:.2f} mm3)")
    # Past the ends the groove stops: the pin must hit the hub (that is what drives the thumb-turn)
    for h, end in ((-15.0, "inner"), (FP + 15.0, "outer")):
        if overlap(k.pin_model(0.0, h), k.hub(h)) < 0.5:
            problems.append(f"no stop at the {end} end of the spiral")
    # The groove walls between the turns
    wall = k.SPIRAL_PITCH - k.GROOVE_W
    if wall < 1.2:
        problems.append(f"wall between spiral turns only {wall:.1f} mm")
    del hub0
    return problems, worst


def motion():
    problems = []
    static = {n: p for n, (p, _, _) in k.assembly().items()
              if n in ("shell", "chassis", "cap", "servo", "hall", "reed", "pcb")}
    adapter = k.knob_adapter()
    # 1. Key turned by hand, servo parked: the thumb-turn turns two full turns, the pin walks along the spiral
    h_park = FP - 135.0 - 2 * 360.0            # parked after a two-turn lock (as in the firmware simulation)
    for kk in range(0, -721, -15):
        if not (0 <= h_park - kk <= FP):
            problems.append(f"key at {kk} deg would hit the end of the spiral")
            continue
        moving = {"adapter": adapter.rotate((0, 0, kk)), "follower": k.follower(kk, h_park), "pin": k.pin_model(kk, h_park)}
        for name, part in moving.items():
            for sname, spart in static.items():
                v = overlap(part, spart)
                if v > LIMIT:
                    problems.append(f"key at {kk} deg: {name} hits {sname} ({v:.1f} mm3)")
            if name != "adapter":
                v = overlap(part, adapter.rotate((0, 0, kk))) if name == "pin" else 0.0
                if v > LIMIT:
                    problems.append(f"key at {kk} deg: pin hits the adapter")
        v = overlap(k.pin_model(kk, h_park), k.hub(h_park))
        if v > 0.05:
            problems.append(f"key at {kk} deg: pin rubs in the groove ({v:.2f} mm3)")
    # 2. Servo turning, thumb-turn still (taking up / parking) and turning together (driving)
    _, horn = k.servo_model()
    for h in np.linspace(0, FP, 34):
        hub, hn = k.hub(h), horn.rotate((0, 0, h))
        for sname, spart in static.items():
            for name, part in (("hub", hub), ("horn", hn)):
                if name == "horn" and sname == "servo":
                    continue
                v = overlap(part, spart)
                if v > LIMIT:
                    problems.append(f"hub at {h:.0f} deg: {name} hits {sname} ({v:.1f} mm3)")
        v = overlap(hub, adapter)
        if v > LIMIT:
            problems.append(f"hub at {h:.0f} deg hits the adapter ({v:.1f} mm3)")
    return problems


def assembly_order():
    """Shell -> adapter + follower + pin -> chassis module (servo, hub, sensors) -> PCB -> cap, straight down."""
    problems = []
    shell = k.shell()
    servo, horn = k.servo_model()
    h = 135.0
    module = k.chassis() + servo + horn + k.hub(h) + k.hall_model() + k.reed_model()
    knob = k.knob_adapter() + k.follower(0, h) + k.pin_model(0, h)
    steps = {
        "adapter with follower": (knob, shell),
        "chassis module": (module, shell + knob),
        "PCB": (k.pcb_model(), shell + module),
        "cap": (k.cap(), shell + k.pcb_model()),
    }
    for name, (part, obstacles) in steps.items():
        lowest = part.bounding_box()[2]
        worst = 0.0
        for t in np.arange(0.5, k.L.top + 10 - lowest, 1.0):
            if name == "cap" and t < 3.0:     # snaps over a 0.35 mm bump on its last 2 mm
                continue
            worst = max(worst, overlap(part.translate((0, 0, t)), obstacles))
        if worst > LIMIT:
            problems.append(f"{name} can't go in straight from the top: {worst:.1f} mm3 in the way")
    return problems


def sensors():
    """Hall sensor sees the hub magnet 135 deg after reversing from either end; nothing confuses the two sensors."""
    report = {}
    mu = k.hub_magnet_angle()
    hall_x, hall_y = k.polar(k.HALL_R, k.HALL_ANGLE)
    for start, direction, label in ((FP, -1, "after a lock (outer end)"), (0.0, 1, "after an unlock (inner end)")):
        for step in range(0, 721):
            h = start + direction * step
            mx, my = k.polar(k.HALL_R, mu + h)
            if math.hypot(mx - hall_x, my - hall_y) < 0.5:
                report[f"hub magnet reaches the hall sensor {label}"] = step
                break
    L = k.L
    knob_magnet = np.array([k.MAGNET_R, 0, L.A - 4.5])
    hub_magnet_r, hub_magnet_z = k.HALL_R, L.hub_top - 1.0
    reed = np.array([k.KNOB_REED_R, 0, L.A - 4.5])
    hall = np.array([hall_x, hall_y, L.hub_top + 0.8 + k.HALL[2] / 2])
    report["knob magnet to knob reed, glass to magnet (mm)"] = round(float(np.linalg.norm(knob_magnet - reed)) - 2.5 - k.REED[0] / 2, 1)
    report["hub magnet to hall sensor (mm)"] = round(float(hall[2] - hub_magnet_z) - 1.0, 1)
    # Closest the wrong magnet ever gets to each sensor
    report["knob magnet to hall sensor, closest (mm)"] = round(min(
        float(np.linalg.norm(np.array([*k.polar(k.MAGNET_R, a), L.A - 4.5]) - hall)) for a in range(0, 360, 5)), 1)
    report["hub magnet to knob reed, closest (mm)"] = round(min(
        float(np.linalg.norm(np.array([*k.polar(hub_magnet_r, a), hub_magnet_z]) - reed)) for a in range(0, 360, 5)), 1)
    return report


def overhangs():
    out = {}
    for name, rot in k.PRINT_ROTATION.items():
        part = k.PARTS[name]().rotate(rot)
        part = part.translate((0, 0, -part.bounding_box()[2]))
        m = k.to_trimesh(part)
        n, c, a = m.face_normals, m.triangles_center, m.area_faces
        down = (n[:, 2] < -math.cos(math.radians(45))) & (c[:, 2] > 0.3)
        out[name] = a[down].sum()
    return out


def run():
    print("\nChecks")
    fit = static_fit()
    print(f"  fit (spiral start / middle / end):          {'OK' if not fit else 'PROBLEMS'}")
    sp, worst = spiral()
    print(f"  spiral: pin runs clear, stops at both ends:  {'OK' if not sp else 'PROBLEMS'}")
    mot = motion()
    print(f"  motion (key 2 turns by hand, servo):         {'OK' if not mot else 'PROBLEMS'}")
    order = assembly_order()
    print(f"  assembly straight down the bore:             {'OK' if not order else 'PROBLEMS'}")
    for p in fit + sp + mot + order:
        print("    " + p)
    print("  sensors:")
    for name, v in sensors().items():
        print(f"    {name:52s} {v}")
    print("  overhangs > 45 deg (need bridging or support):")
    for name, area in overhangs().items():
        print(f"    {name:14s} {area:7.0f} mm2")
    return not (fit or sp or mot or order)


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
