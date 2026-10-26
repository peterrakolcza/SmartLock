"""Verification for lock.py: fit, motion, assembly order, clearances, printability.

Run through `python lock.py` (exports first) or on its own: `python checks.py`.
"""

import itertools
import math

import numpy as np

import lock as k

# Pairs that are meant to touch or nest
ALLOWED = {
    frozenset(("servo", "horn")),
    frozenset(("sg90", "sg90_horn")),
    frozenset(("thumb_turn", "knob_adapter")),
}
LIMIT = 0.5  # mm3


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
    for closed in (0.0, 0.5, 1.0):
        problems += clashes(k.assembly(closed_fraction=closed), f"clutch {closed:.0%} closed")
    return problems


def motion():
    problems = []
    open_parts = k.assembly(0.0)
    static = {n: p for n, (p, _, _) in open_parts.items() if n not in ("knob_adapter", "thumb_turn", "hub", "slider", "horn")}
    adapter, turn = k.knob_adapter(), k.thumb_turn()
    hub, slider_open, slider_closed = k.hub(), k.slider(0.0), k.slider(1.0)
    _, horn = k.servo_model()
    # Key turned by hand, clutch open: the thumb-turn spins, nothing else may be in the way
    for rot in range(0, 360, 10):
        a = adapter.rotate((0, 0, rot))
        for name, part in list(static.items()) + [("hub", hub), ("slider", slider_open)]:
            v = overlap(a, part)
            if v > LIMIT:
                problems.append(f"thumb-turn at {rot} deg (clutch open) hits {name}: {v:.1f} mm3")
    # Servo turning while the teeth search for the slots (open) and while driving (closed, adapter follows)
    for rot in range(0, 360, 10):
        for name, part in static.items():
            for moving, label in ((hub.rotate((0, 0, rot)), "hub"), (horn.rotate((0, 0, rot)), "horn"),
                                  (slider_open.rotate((0, 0, rot)), "open slider")):
                if name in ("servo",) and label == "horn":
                    continue
                v = overlap(moving, part)
                if v > LIMIT:
                    problems.append(f"{label} at {rot} deg hits {name}: {v:.1f} mm3")
        v = overlap(slider_closed.rotate((0, 0, rot)), adapter.rotate((0, 0, rot)))
        if v > LIMIT:
            problems.append(f"closed slider and adapter turning together at {rot} deg overlap {v:.1f} mm3")
    # Teeth only seat when lined up with the slots
    seated = [d for d in range(0, 60, 2) if overlap(slider_closed.rotate((0, 0, d)), adapter) < LIMIT]
    if not seated or max(abs(((d + 30) % 60) - 30) for d in seated) > 6:
        problems.append(f"unexpected seating window: {seated}")
    return problems, seated


def assembly_order():
    """Shell on the door -> adapter onto the thumb-turn -> chassis module -> PCB -> cap, all straight down the bore."""
    problems = []
    shell = k.shell()
    servo, horn = k.servo_model()
    module = k.chassis() + k.sg90_clip() + servo + horn + k.hub() + k.slider(0.0) + k.fork(k.fork_angle(0.0)) + k.sg90_model() + k.sg90_horn(k.fork_angle(0.0))
    steps = {
        "knob adapter": (k.knob_adapter(), shell),
        "chassis module": (module, shell + k.knob_adapter()),
        "PCB": (k.pcb_model(), shell + module),
        "cap": (k.cap(), shell + k.pcb_model()),
    }
    for name, (part, obstacles) in steps.items():
        lowest = part.bounding_box()[2]
        travel = k.L.top + 10 - lowest
        worst = 0.0
        for t in np.arange(0.5, travel, 1.0):
            # The cap snaps over a 0.35 mm bump on its last 2 mm
            if name == "cap" and t < 3.0:
                continue
            worst = max(worst, overlap(part.translate((0, 0, t)), obstacles))
        if worst > LIMIT:
            problems.append(f"{name} can't go in straight from the top: {worst:.1f} mm3 in the way")
    return problems


def clearances():
    L = k.L
    report = {
        "reed glass above the magnet": (L.A + 1.0 + 1.6 - 1.35) - L.A,
        "SG90 above the adapter top": (L.G - k.SG90_SHAFT_FROM_END) - L.A,
        "fork ring to SG90": abs(k.PIVOT_Y) - k.SG90_BODY[1] / 2 - k.FORK_RING[1],
        "fork ring to slider": k.FORK_RING[0] - k.SLIDER_R,
        "slider teeth tips above the adapter when open": k.OPEN_GAP,
        "tooth engagement when closed": k.TOOTH_HEIGHT - (k.TRAVEL - k.OPEN_GAP) + k.TRAVEL - k.OPEN_GAP - 0.0,
        "servo back to PCB": k.PCB_BELOW,
        "PCB to the bore": k.BORE - k.PCB_DIAMETER / 2,
    }
    report["tooth engagement when closed"] = k.TRAVEL - k.OPEN_GAP
    return report


def overhangs():
    """Downward faces steeper than 45 deg that are not on the bed, per printed part in its print orientation."""
    out = {}
    for name, rot in k.PRINT_ROTATION.items():
        part = {"shell": k.shell, "knob_adapter": k.knob_adapter, "hub": k.hub, "slider": lambda: k.slider(0),
                "fork": lambda: k.fork(0), "chassis": k.chassis, "sg90_clip": k.sg90_clip, "cap": k.cap}[name]().rotate(rot)
        part = part.translate((0, 0, -part.bounding_box()[2]))
        m = k.to_trimesh(part)
        n, c, a = m.face_normals, m.triangles_center, m.area_faces
        down = (n[:, 2] < -math.cos(math.radians(45))) & (c[:, 2] > 0.3)
        out[name] = a[down].sum()
    return out


def run():
    print("\nChecks")
    fit = static_fit()
    print(f"  fit (open / half / closed):        {'OK' if not fit else 'PROBLEMS'}")
    mot, seated = motion()
    window = max(abs(((d + 30) % 60) - 30) for d in seated)
    print(f"  motion (key, servo, clutch):       {'OK' if not mot else 'PROBLEMS'}  (teeth seat within +-{window} deg of a slot)")
    order = assembly_order()
    print(f"  assembly straight down the bore:   {'OK' if not order else 'PROBLEMS'}")
    for p in fit + mot + order:
        print("    " + p)
    print("  clearances:")
    for name, v in clearances().items():
        print(f"    {name:48s} {v:5.2f} mm")
    print("  overhangs > 45 deg (need bridging or support):")
    for name, area in overhangs().items():
        print(f"    {name:14s} {area:7.0f} mm2")
    return not (fit or mot or order)


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
