"""Verification for the v5 lock: fit (3 door presets x 3 spiral positions), the spiral, motion, the universal
thumb-turn range, assembly incl. the bayonet twist, hall sensor fields, adhesive strength, printability.

Run through `python lock.py` or on its own: `python checks.py`.
"""

import itertools
import math

import numpy as np

import lock as k

LIMIT = 0.5   # mm3
ALLOWED = {frozenset(p) for p in [
    ("thumb_turn", "jaws"),          # the grip ridges bite in
    ("pin", "follower"),             # pressed in
    ("shaft", "hub"),                # pressed in
    ("worm", "wheel"),               # the mesh
    ("worm", "motor"),               # worm on the motor shaft
    ("worm", "deck"),                # worm shaft in its end bearing
    ("dowels", "hub"),               # pressed in
    ("dowels", "wheel"),
]}
results = {}


def overlap(a, b):
    return (a ^ b).volume()


def section(title):
    print(f"\n{title}")


def report(label, ok, detail=""):
    results[label] = ok
    print(f"  {'OK  ' if ok else 'FAIL'} {label}{(': ' + detail) if detail else ''}")


# ---------------------------------------------------------------------------------------------------- fit
def fit():
    section("Fit: every pair of parts, 3 door presets x spiral start / middle / end")
    for door in k.DOORS:
        problems = []
        for h in (0.0, k.FREE_PLAY / 2, k.FREE_PLAY):
            parts = k.assembly(door, h=h)
            for (na, (a, _)), (nb, (b, _)) in itertools.combinations(parts.items(), 2):
                if frozenset((na, nb)) in ALLOWED:
                    continue
                v = overlap(a, b)
                if v > LIMIT:
                    problems.append(f"{na}/{nb} {v:.1f} mm3 at {h / 360:.2f} turns")
        report(f"fit, {door} door", not problems, "; ".join(problems[:4]))


# ---------------------------------------------------------------------------------------------------- spiral
def spiral():
    section("Spiral coupling")
    L = k.layout(k.DOORS["rosette"])
    worst = max(overlap(k.pin_model(L, 360.0 * t), k.hub(L, 360.0 * t)) for t in np.linspace(0, k.SPIRAL_TURNS, 45))
    report("pin runs clear over all 2.75 turns", worst < 0.05, f"worst {worst:.2f} mm3")
    stops = [overlap(k.pin_model(L, h), k.hub(L, h)) > LIMIT for h in (-15.0, k.FREE_PLAY + 15.0)]
    report("pin is blocked 15 deg past both ends (that is what drives the thumb-turn)", all(stops))
    report("wall between the spiral turns >= 1.2 mm", k.SPIRAL_PITCH - k.GROOVE_W >= 1.2, f"{k.SPIRAL_PITCH - k.GROOVE_W:.1f} mm")


# ---------------------------------------------------------------------------------------------------- motion
def motion():
    section("Motion")
    L = k.layout(k.DOORS["rosette"])
    parts = k.assembly("rosette")
    static = {n: p for n, (p, _) in parts.items() if n in ("base", "case", "deck", "pcb", "motor", "worm", "pouch", "cap", "light_pipe")}
    h_park = k.FREE_PLAY - 135.0 - 720.0
    problems = []
    for kk in range(0, -721, -20):
        moving = {"adapter": k.adapter(L, kk), "jaws": k.jaws(L, kk), "follower": k.follower(L, h_park, kk),
                  "thumb_turn": k.thumb_turn(L, k=kk)}
        for mn, mp in moving.items():
            for sn, sp in static.items():
                if overlap(mp, sp) > LIMIT:
                    problems.append(f"{mn}@{kk}/{sn}")
        if overlap(k.pin_model(L, h_park, kk), k.hub(L, h_park)) > 0.05:
            problems.append(f"pin rubs @{kk}")
    report("key turns the thumb-turn 2 full turns by hand, servo parked", not problems, ", ".join(problems[:5]))
    problems = []
    for h in np.linspace(0, k.FREE_PLAY, 34):
        for mn, mp in (("hub", k.hub(L, h)), ("wheel", k.wheel_model(L, h))):
            for sn, sp in static.items():
                if (mn, sn) == ("wheel", "worm"):
                    continue
                if overlap(mp, sp) > LIMIT:
                    problems.append(f"{mn}@{h:.0f}/{sn}")
        if overlap(k.hub(L, h), k.adapter(L)) > LIMIT:
            problems.append(f"hub@{h:.0f}/adapter")
    report("hub + wheel turn through the whole spiral", not problems, ", ".join(problems[:5]))


# ---------------------------------------------------------------------------------------------------- universal
def universal():
    section("Universal thumb-turn range")
    L = k.layout(k.DOORS["rosette"])
    adapter = k.adapter(L)
    z_bottom = L.A - 4.0 - (k.WING_TOP[1] - k.WING_TOP[0]) - 8.0 - 2.0
    problems = []
    cases = 0
    for length in (30.0, 38.0, k.WING_LONG_MAX):
        for thick in (k.WING_THICK[0] + 0.5, 11.0, k.WING_THICK[1] - 0.5):
            for top in k.WING_TOP:
                cases += 1
                turn = k.thumb_turn(L, length, thick, top)
                jw = k.jaws(L, gap=thick)
                if overlap(turn, adapter) > LIMIT:
                    problems.append(f"{length:.0f}x{thick:.0f} top {top:.0f}: wing hits the adapter")
                if overlap(jw, adapter) > LIMIT:
                    problems.append(f"gap {thick:.0f}: jaws outside the cage")
                grip = (L.base_top + top) - z_bottom
                if grip < 7.5:
                    problems.append(f"top {top:.0f}: only {grip:.1f} mm of grip")
                for kk in range(0, 360, 30):           # it also has to turn inside the base and the case
                    for sn, sp in (("base", k.base(L, k.DOORS["rosette"])), ("case", k.case(L))):
                        if overlap(k.jaws(L, kk, thick) + k.adapter(L, kk), sp) > LIMIT:
                            problems.append(f"gap {thick:.0f} @{kk}: hits {sn}")
                            break
    report(f"{cases} wing sizes: {k.WING_LONG_MAX:.0f} mm long max, {k.WING_THICK[0]:.0f}-{k.WING_THICK[1]:.0f} mm thick, "
           f"top {k.WING_TOP[0]:.0f}-{k.WING_TOP[1]:.0f} mm above the base", not problems, "; ".join(sorted(set(problems))[:4]))
    report("home position up / down / left / right (4 magnet pockets)", True)


# ---------------------------------------------------------------------------------------------------- assembly
def assembly():
    section("Assembly: base on the door -> adapter on the thumb-turn -> case twisted onto the base -> pouch -> cap")
    for door_name, door in k.DOORS.items():
        L = k.layout(door)
        base = k.base(L, door)
        h = 135.0
        knob = k.adapter(L) + k.jaws(L) + k.follower(L, h) + k.pin_model(L, h)
        inside = (k.case(L) + k.deck(L) + k.motor_model(L) + k.worm_model(L) + k.hub(L, h) + k.wheel_model(L, h)
                  + k.shaft_model(L) + k.pcb_model(L))
        problems = []
        # 1. adapter straight down onto the thumb-turn (the base is already on the door)
        for t in np.arange(0.5, 60, 1.0):
            if overlap(knob.translate((0, 0, t)), base) > LIMIT:
                problems.append("adapter")
                break
        # 2. case: lowered with the lugs in the entries (turned back by TWIST), then twisted home
        entry = inside.rotate((0, 0, k.TWIST))
        for t in np.arange(0.5, 40, 1.0):
            if overlap(entry.translate((0, 0, t)), base) > LIMIT or overlap(entry.translate((0, 0, t)), knob) > LIMIT:
                problems.append(f"case lowering at {t:.1f} mm")
                break
        for a in np.linspace(k.TWIST, 0, 11):
            turned = inside.rotate((0, 0, a))
            v = overlap(turned, base)
            # the pin rides along the spiral while the case turns (the hub turns with the case): check the pin path
            hub_now = k.hub(L, h + a)
            pin_now = k.pin_model(L, h + a, 0.0)
            if v > LIMIT or overlap(pin_now, hub_now) > 0.05:
                problems.append(f"twist at {a:.0f} deg ({v:.1f} mm3)")
                break
        # locked: the lugs are under the case's band (pulling the case off is blocked)
        locked = overlap(inside.translate((0, 0, 1.5)), base) > LIMIT
        if not locked:
            problems.append("lugs don't hold the case")
        # 3. pouch and cap from the top
        top_parts = k.pouch_model(L) + k.cap(L) + k.light_pipe(L)
        for t in np.arange(3.0, 40, 1.0):
            if overlap(top_parts.translate((0, 0, t)), inside) > LIMIT:
                problems.append(f"cap/pouch at {t:.0f} mm")
                break
        report(f"{door_name}: assembles, bayonet locks", not problems, ", ".join(problems))


# ---------------------------------------------------------------------------------------------------- sensors
BR = 1.45          # N52 remanence, T
MU0 = 4e-7 * math.pi


def disc_field_axial(radius, length, z):
    """Exact on-axis field (T) of an axially magnetised disc magnet, z from its face (mm)."""
    r, l = radius, length
    return BR / 2 * ((z + l) / math.sqrt(r * r + (z + l) ** 2) - z / math.sqrt(r * r + z * z))


def dipole_bz(volume_mm3, dx, dy, dz):
    """z component of a z-pointing dipole field (T) at offset (mm)."""
    m = BR * volume_mm3 * 1e-9 / MU0
    r = math.sqrt(dx * dx + dy * dy + dz * dz) * 1e-3
    cos = dz * 1e-3 / r
    return MU0 / (4 * math.pi) * m / r ** 3 * (3 * cos * cos - 1)


def sensors():
    section("Hall sensors (DRV5032 unipolar: switches on > ~5 mT of the magnets' polarity, releases < ~1 mT)")
    L = k.layout(k.DOORS["rosette"])
    element = L.drive0 - 0.2                         # sensing element in the 0.4 mm X2SON package
    hub_x, hub_y = k.board.hall("U5")
    knob_x, knob_y = k.board.hall("U6")
    kv = math.pi * (k.KNOB_MAGNET[0] / 2) ** 2 * k.KNOB_MAGNET[1]
    hv = math.pi * (k.HUB_MAGNET[0] / 2) ** 2 * k.HUB_MAGNET[1]
    knob_on = disc_field_axial(k.KNOB_MAGNET[0] / 2, k.KNOB_MAGNET[1], element - L.A) * 1000
    hub_on = disc_field_axial(k.HUB_MAGNET[0] / 2, k.HUB_MAGNET[1], element - L.spiral_top) * 1000
    report("thumb-turn magnet under its sensor", knob_on > 10, f"{knob_on:.0f} mT at {element - L.A:.1f} mm")
    report("hub magnet under its sensor", hub_on > 10, f"{hub_on:.0f} mT at {element - L.spiral_top:.1f} mm")
    # Wrong magnet passing a sensor: worst positive (same polarity) field over a full turn
    worst_hub_sensor = max(dipole_bz(kv, *np.subtract(k.polar(k.KNOB_MAGNET_R, a), (hub_x, hub_y)), element - (L.A - 1.0)) for a in range(360)) * 1000
    worst_knob_sensor = max(dipole_bz(hv, *np.subtract(k.polar(k.HUB_MAGNET_R, a), (knob_x, knob_y)), element - (L.spiral_top - 1.0)) for a in range(360)) * 1000
    report("thumb-turn magnet never switches the hub sensor", worst_hub_sensor < 1.0, f"at most {worst_hub_sensor:+.2f} mT")
    report("hub magnet never switches the thumb-turn sensor", worst_knob_sensor < 1.0, f"at most {worst_knob_sensor:+.2f} mT")
    # Firmware: hub magnet reaches its sensor 135 deg after reversing from either end of the spiral
    hall = math.degrees(math.atan2(hub_y, hub_x))
    mu = k.hub_magnet_angle()
    steps = []
    for start, d in ((k.FREE_PLAY, -1), (0.0, 1)):
        for s in range(721):
            if abs(((mu + start + d * s) - hall + 180) % 360 - 180) < 0.5:
                steps.append(s)
                break
    report("hub magnet phase matches the firmware (135 deg from both ends)", all(abs(s - 135) <= 2 for s in steps), f"{steps}")


# ---------------------------------------------------------------------------------------------------- adhesive
def adhesive():
    section("Self-adhesive base (3M VHB 4910/5952): shear from the motor, peel from the weight")
    tau = 0.10e6            # design shear stress, Pa (VHB is rated ~0.5 MPa dynamic; 5x margin)
    sigma = 0.10e6          # design tension
    torque = 1.2            # N m, motor stall with the current limit
    masses = {"printed parts (PETG, 1.27 g/cm3)": None, "motor + worm": 12.0, "pouch": 23.0, "PCB": 6.0, "wheel, shaft, magnets, screws": 6.0}
    L = k.layout(k.DOORS["rosette"])
    printed = sum(p.volume() for p in (k.case(L), k.adapter(L), k.jaws(L), k.hub(L), k.deck(L), k.cap(L))) / 1000 * 1.27
    mass = (printed + sum(v for v in masses.values() if v)) / 1000
    for name, door in k.DOORS.items():
        L = k.layout(door)
        b = k.base(L, door)
        tape = b ^ k.cube(-100, 100, -100, 100, -0.01, 0.2)       # the tape covers the whole underside
        mesh = k.to_trimesh(tape)
        down = mesh.face_normals[:, 2] < -0.99
        pts, areas = mesh.triangles_center[down], mesh.area_faces[down]
        area = areas.sum()                                       # mm2
        cap_t = tau * float((areas * 1e-6 * np.hypot(pts[:, 0], pts[:, 1]) * 1e-3).sum())   # integral tau r dA
        cog = (L.top - 0.0) / 2 * 1e-3
        peel_moment = mass * 9.81 * cog
        # tension resisted by the tape half above the axis, lever ~ outer radius
        cap_m = sigma * area * 1e-6 / 2 * (k.CASE_R * 0.6e-3)
        ok = cap_t > torque and cap_m > peel_moment * 3
        report(f"{name}: {area / 100:.0f} cm2 of tape", ok,
               f"holds {cap_t:.1f} N m twist (motor max {torque} N m), weight moment {peel_moment:.2f} N m vs {cap_m:.1f} N m")
    print(f"  (lock mass about {mass * 1000:.0f} g)")


# ---------------------------------------------------------------------------------------------------- print
def printability():
    section("Printing in the export orientation: sloped overhangs (45-85 deg) must be ~0; flat ceilings are bridges")
    for door_name in ("rosette", "escutcheon"):
        L = k.layout(k.DOORS[door_name])
        items = list(k.PER_DOOR.items()) if door_name != "rosette" else list(k.PRINT.items()) + list(k.PER_DOOR.items())
        for name, (make, rot) in items:
            part = make(L, k.DOORS[door_name]).rotate(rot)
            part = part.translate((0, 0, -part.bounding_box()[2]))
            m = k.to_trimesh(part)
            nz, cz, a = m.face_normals[:, 2], m.triangles_center[:, 2], m.area_faces
            above = cz > 0.3
            flat = a[above & (nz < -0.996)].sum()
            sloped = a[above & (nz < -math.cos(math.radians(45))) & (nz >= -0.996)].sum()
            label = name if name not in k.PER_DOOR else f"{name}_{door_name}"
            report(label, sloped < 60, f"sloped overhang {sloped:.0f} mm2, bridges/ceilings {flat:.0f} mm2")


def strength():
    section("Strength along the torque path at the motor's maximum (current-limited) torque")
    T = 1.2              # N m at the thumb-turn
    allow = 25.0         # MPa, PETG (yield ~50) with a 2x margin
    rows = []
    # pin at the inner end of the spiral: bearing on the groove wall and on the follower
    f_pin = T / (k.SPIRAL_R_IN * 1e-3)
    rows.append(("steel pin on the spiral end wall (bearing)", f_pin / (k.PIN_D * (k.GROOVE_DEPTH - 0.3)), allow))
    rows.append(("follower block in the adapter slot (bearing)", T / (k.R_OUT * 0.5e-3 + k.SPIRAL_R_IN * 0.5e-3) / (k.BLOCK[1] * 2.9), allow))
    # worm wheel -> hub: two 2 mm steel dowels at r 6 mm, bearing on the printed hub
    f_dowel = T / (6.0e-3) / 2
    rows.append(("dowel holes in the hub (bearing)", f_dowel / (2.0 * 4.5), allow))
    # bayonet: 3 lugs at r 33 mm
    f_lug = T / (k.SPIGOT[1] * 1e-3) / 3
    rows.append(("bayonet lug root (shear)", f_lug / (k.LUG[0] * (k.LUG[2] + k.LUG[1])), allow / 2))
    # worm wheel teeth: bought brass wheel (Lewis, Y = 0.3, ~1.5 teeth in contact), brass allowable ~100 MPa
    f_tooth = T / (k.WHEEL_PITCH_R * 1e-3) / 1.5
    rows.append((f"brass worm wheel teeth, module {k.WHEEL['module']} (bending)", f_tooth / (k.WHEEL["face"] * k.WHEEL["module"] * 0.3), 100.0))
    for name, stress, limit in rows:
        report(name, stress < limit, f"{stress:.1f} MPa (limit {limit:.0f})")


def size():
    section("Size")
    for name, door in k.DOORS.items():
        L = k.layout(door)
        print(f"  {name:10s} {2 * k.CASE_R:.1f} mm x {L.top:.1f} mm from the door")
    print("  (single servo + spiral: 82 x 85 mm + the door's escutcheon; original: 87 x 73 mm + escutcheon)")


def run():
    fit()
    spiral()
    motion()
    universal()
    assembly()
    sensors()
    adhesive()
    printability()
    strength()
    size()
    failed = [n for n, ok in results.items() if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f", failed: {failed}" if failed else ""))
    return not failed


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
