"""v5 smart lock: self-adhesive, universal, battery powered, one motor, the key always turns freely.

    door | adhesive base (per door: rosette / escutcheon / flat) | case (bayonet) with:
         universal thumb-turn adapter (2 screw jaws) + follower | spiral hub + worm wheel | worm + N20 motor and the
         crescent PCB side by side | deck | Li-ion pouch | cap

* Nothing is screwed to the door: the base sticks on with 3M VHB around the cylinder.
* Universal: the base comes in presets for a round rosette, a long escutcheon or a flush cylinder; the adapter's two
  jaws grip thumb-turn wings 4-22 mm thick and 12-22 mm tall; the thumb-turn magnet goes into one of 4 pockets so
  the home position can be up, down, left or right.
* The spiral coupling (from `3D printed case/spiral`) lets the key turn freely; a self-locking worm drives the hub.

Coordinates: z = 0 is the door surface, +z away from the door, +y up. Hub rotation h (deg) = spiral position.

    pip install manifold3d trimesh
    python lock.py      # exports the STLs (all presets) and runs checks.py
"""

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold, Mesh

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "PCB" / "v5"))
import layout as board  # noqa: E402  (shared with the PCB generator)

SEG = 96
FIT = 0.3

# ---------------------------------------------------------------------------------------------------- door presets
@dataclass
class Door:
    name: str
    base_h: float            # height of the base = what sticks out of the door around the cylinder (+ clearance)
    rosette_d: float = 0.0   # round rosette around the cylinder
    escutcheon_w: float = 0.0  # long plate (handle + cylinder), runs along y


DOORS = {
    "rosette": Door("rosette", base_h=9.0, rosette_d=56.0),
    "escutcheon": Door("escutcheon", base_h=11.0, escutcheon_w=34.0),
    "flat": Door("flat", base_h=2.5, rosette_d=36.0),
}

# Universal thumb-turn range (above the base top)
WING_TOP = (12.0, 22.0)      # top of the thumb-turn wing
WING_THICK = (4.0, 22.0)     # jaw gap range
WING_LONG_MAX = 46.0
JAW_SCREW_Z = 7.0            # jaw screw axis above the bottom of the cage
JAW_SCREW_LEN = 16.0         # M3 x 16 reaches the jaws for every wing thickness
JAW_INSERT_D = 4.0           # hole for an M3 x 3 x 4.2 heat-set insert
JAW_DIMPLE = 0.8

# ---------------------------------------------------------------------------------------------------- spiral
SPIRAL_TURNS = 2.75          # = MOTION_SPIRAL_TURNS in the firmware
SPIRAL_R_IN = 8.0
SPIRAL_PITCH = 5.0
PIN_D = 3.0
GROOVE_W = PIN_D + 0.4
GROOVE_DEPTH = 2.6
HUB_FLOOR = 1.4
SLOT_ANGLE = 90.0
BLOCK = (5.8, 4.6, 2.9)
R_OUT = SPIRAL_R_IN + SPIRAL_PITCH * SPIRAL_TURNS
HUB_R = R_OUT + GROOVE_W / 2 + 1.6
FREE_PLAY = SPIRAL_TURNS * 360.0

# ---------------------------------------------------------------------------------------------------- bought drive parts
WHEEL = dict(module=0.6, teeth=30, face=6.0, bore=3.0)        # brass worm wheel, 30:1 with a single-start steel worm
WHEEL_PITCH_R = WHEEL["module"] * WHEEL["teeth"] / 2
WHEEL_OUT_R = WHEEL_PITCH_R + WHEEL["module"]
WORM = dict(pitch_r=3.3, length=13.0)                        # steel worm, module 0.6, 3 mm bore on the motor's D-shaft
MOTOR = dict(gearbox=9.0, can=15.0, width=10.0, height=12.0, tail=1.5)   # N20, 10 wide x 12 tall lying flat
CENTRE = WHEEL_PITCH_R + WORM["pitch_r"]                     # worm axis to lock axis
POUCH = (50.0, 34.0, 6.0)                                    # 603450 Li-ion pouch, 1200 mAh
SHAFT_D = 3.0
KNOB_MAGNET = (5.0, 2.0)                                     # diametric no: axial disc magnets
HUB_MAGNET = (3.0, 2.0)
KNOB_MAGNET_R = 27.5
HUB_MAGNET_R = 18.0

# ---------------------------------------------------------------------------------------------------- case
BORE_R = board.BORE_R
WALL = 1.8
CASE_R = BORE_R + WALL
DECK_T = 1.2
CAP_T = 1.5
SPIGOT = (31.2, 33.2, 4.0)        # base bayonet ring: inner r, outer r, height
LUG = (8.0, 1.4, 2.0)             # tangential width, radial, height
TWIST = 25.0
CASE_BOSSES = (0.0, 100.0, 170.0)


@dataclass
class Layout:
    base_top: float
    A: float          # adapter top
    hub0: float
    spiral_top: float
    drive0: float     # bottom of the drive layer (motor, PCB)
    wheel_mid: float
    drive1: float
    deck0: float
    pouch0: float
    cap0: float
    top: float


def layout(door):
    b = door.base_h
    A = b + WING_TOP[1] + 0.5 + 4.0                 # 4 mm adapter disc above the tallest wing
    hub0 = A + 0.3
    spiral_top = hub0 + GROOVE_DEPTH + HUB_FLOOR
    drive0 = spiral_top + 1.45                      # the hall sensors (SOT-23, 1.12 mm) hang under the PCB
    wheel_mid = drive0 + MOTOR["height"] / 2
    drive1 = drive0 + MOTOR["height"]
    deck0 = drive1 + 0.3
    pouch0 = deck0 + DECK_T + 0.2
    cap0 = pouch0 + POUCH[2] + 0.2
    return Layout(b, A, hub0, spiral_top, drive0, wheel_mid, drive1, deck0, pouch0, cap0, cap0 + CAP_T)


# ---------------------------------------------------------------------------------------------------- helpers
def cube(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl(r, z0, z1, seg=SEG, x=0.0, y=0.0):
    return Manifold.cylinder(z1 - z0, r, circular_segments=seg).translate((x, y, z0))


def cyl_x(r, x0, x1, y, z, seg=32):
    return Manifold.cylinder(x1 - x0, r, circular_segments=seg).rotate((0, 90, 0)).translate((x0, y, z))


def cyl_y(r, y0, y1, x, z, seg=32):
    return Manifold.cylinder(y1 - y0, r, circular_segments=seg).rotate((-90, 0, 0)).translate((x, y0, z))


def ring(r_in, r_out, z0, z1, seg=SEG):
    return cyl(r_out, z0, z1, seg) - cyl(r_in, z0 - 1, z1 + 1, seg)


def polar(r, a):
    a = math.radians(a)
    return r * math.cos(a), r * math.sin(a)


def rounded_box(lx, ly, r, z0, z1, x=0.0, y=0.0):
    r = min(r, lx / 2 - 0.01, ly / 2 - 0.01)
    cs = CrossSection.square((lx - 2 * r, ly - 2 * r), center=True).offset(r, JoinType.Round, circular_segments=24)
    return cs.extrude(z1 - z0).translate((x, y, z0))


def largest(part):
    return max(part.decompose(), key=lambda p: p.volume())


def to_trimesh(part):
    m = part.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(m.vert_properties)[:, :3], faces=np.asarray(m.tri_verts))


def from_stl(path):
    mesh = trimesh.load(path)
    return Manifold(Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32), tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))


# ---------------------------------------------------------------------------------------------------- spiral
def spiral_point(t):
    return polar(SPIRAL_R_IN + SPIRAL_PITCH * t, SLOT_ANGLE - 360.0 * t)


def pin_radius(h, k=0.0):
    return SPIRAL_R_IN + SPIRAL_PITCH * (h - k) / 360.0


def spiral_groove(z0, z1):
    steps = int(SPIRAL_TURNS * 48)
    disk = lambda t: cyl(GROOVE_W / 2, z0, z1, 24, *spiral_point(t))  # noqa: E731
    groove, prev = Manifold(), disk(0.0)
    for i in range(1, steps + 1):
        cur = disk(SPIRAL_TURNS * i / steps)
        groove += Manifold.hull(prev + cur)
        prev = cur
    return groove


# ---------------------------------------------------------------------------------------------------- bought parts (models)
def thumb_turn(L, length=40.0, thick=11.0, top=None, k=0.0):
    """A thumb-turn wing (any size in the universal range) on its rosette."""
    top = L.base_top + (top if top is not None else 17.0)
    wing = rounded_box(length, thick, min(4.0, thick / 2 - 0.1), L.base_top + 1.0, top)
    stem = cyl(5.0, 0.0, L.base_top + 1.01)
    return (wing + stem).rotate((0, 0, k))


def motor_model(L):
    x0 = WORM_X[1] + 0.5
    w, hgt = MOTOR["width"], MOTOR["height"]
    body = cube(x0, x0 + MOTOR["gearbox"] + MOTOR["can"], CENTRE - w / 2, CENTRE + w / 2, L.wheel_mid - hgt / 2, L.wheel_mid + hgt / 2)
    tail = cube(x0 + MOTOR["gearbox"] + MOTOR["can"], x0 + MOTOR["gearbox"] + MOTOR["can"] + MOTOR["tail"], CENTRE - 3, CENTRE + 3, L.wheel_mid - 3, L.wheel_mid + 3)
    return body + tail


WORM_X = (-8.0, 6.1)


def worm_model(L):
    r = WORM["pitch_r"] + WHEEL["module"]
    return cyl_x(r, WORM_X[0] + 1.5, WORM_X[1], CENTRE, L.wheel_mid) + cyl_x(1.0, WORM_X[0], WORM_X[1] + 0.6, CENTRE, L.wheel_mid, 16)


def wheel_model(L, h=0.0):
    z0, z1 = L.wheel_mid - WHEEL["face"] / 2, L.wheel_mid + WHEEL["face"] / 2
    root = WHEEL_PITCH_R - 1.25 * WHEEL["module"]
    wheel = cyl(root, z0, z1, 64) - cyl(WHEEL["bore"] / 2, z0 - 1, z1 + 1, 24)
    tooth = cube(-0.4, 0.4, root - 0.1, WHEEL_OUT_R, z0, z1)
    for i in range(WHEEL["teeth"]):
        wheel += tooth.rotate((0, 0, 360.0 * i / WHEEL["teeth"]))
    # two 2.2 mm holes drilled through the web: pins into the hub
    for a in (0.0, 180.0):
        x, y = polar(6.0, a)
        wheel -= cyl(1.1, z0 - 1, z1 + 1, 16, x, y)
    return wheel.rotate((0, 0, h))


def dowels_model(L, h=0.0):
    z = L.wheel_mid - WHEEL["face"] / 2
    return (cyl(1.0, z - 4.5, z + 3.5, 16, 6.0, 0.0) + cyl(1.0, z - 4.5, z + 3.5, 16, -6.0, 0.0)).rotate((0, 0, h))


def shaft_model(L):
    return cyl(SHAFT_D / 2, L.A - 3.0, L.deck0 + DECK_T - 0.1, 24)   # its lower end is the journal in the adapter


def pouch_model(L):
    lx, ly, t = POUCH
    return rounded_box(lx, ly, 2.0, L.pouch0, L.pouch0 + t)


def pcb_model(L):
    z0 = L.drive0
    part = CrossSection([board.outline()]).extrude(board.THICKNESS).translate((0, 0, z0))
    for name, p in board.placement().items():
        (w, d, hgt), (ox, oy) = p["body"], p["offset"]
        x, y, side = p["x"] + ox, p["y"] + oy, p["side"]
        body = cube(-w / 2, w / 2, -d / 2, d / 2, 0, hgt).rotate((0, 0, p["rot"]))
        if side == "top":
            part += body.translate((x, y, z0 + board.THICKNESS - 0.01))
        else:
            part += body.translate((x, y, z0 - hgt + 0.01))
    return part


KNOB_POCKETS = tuple((board.SENSOR_ANGLE + a) % 360 for a in (0.0, 90.0, 180.0, 270.0))


def magnets(L, h=0.0, k=0.0, knob_pocket=KNOB_POCKETS[0]):
    kx, ky = polar(KNOB_MAGNET_R, knob_pocket + k)
    knob = cyl(KNOB_MAGNET[0] / 2, L.A - KNOB_MAGNET[1], L.A, 24, kx, ky)
    hx, hy = polar(HUB_MAGNET_R, hub_magnet_angle() + h)
    hub = cyl(HUB_MAGNET[0] / 2, L.spiral_top - HUB_MAGNET[1], L.spiral_top, 24, hx, hy)
    return knob, hub


def pin_model(L, h=0.0, k=0.0):
    x, y = polar(pin_radius(h, k), SLOT_ANGLE + k)
    return cyl(PIN_D / 2, L.A - 3.0, L.hub0 + GROOVE_DEPTH - 0.5, 24, x, y)


def hub_magnet_angle():
    # The hub magnet passes the hub hall sensor 135 deg after reversing from either end of the spiral
    hx, hy = board.hall("U5")
    hall = math.degrees(math.atan2(hy, hx))
    return (hall - (FREE_PLAY - 135.0)) % 360.0


# ---------------------------------------------------------------------------------------------------- printed parts
def base(L, door):
    """Sticks to the door with VHB; bayonet spigot on top."""
    b = door.base_h
    part = cyl(CASE_R, 0.0, b)
    if door.rosette_d:
        part -= cyl(door.rosette_d / 2 + 1.0, -1, b + 1)
    if door.escutcheon_w:
        part -= cyl(door.escutcheon_w / 2 + 2.0, -1, b + 1)                      # around the cylinder
        part -= cube(-door.escutcheon_w / 2 - 0.5, door.escutcheon_w / 2 + 0.5, -100, 100, -1, b - 2.0)  # channel, 2 mm bridge on top
    spigot = ring(SPIGOT[0], SPIGOT[1], b - 0.01, b + SPIGOT[2])
    for i in range(3):
        lug = cube(-LUG[0] / 2, LUG[0] / 2, SPIGOT[1] - 0.01, SPIGOT[1] + LUG[1], b + SPIGOT[2] - LUG[2], b + SPIGOT[2])
        lug = Manifold.hull(lug + cube(-LUG[0] / 2, LUG[0] / 2, SPIGOT[1] - 0.01, SPIGOT[1] + 0.01, b + SPIGOT[2] - LUG[2] - LUG[1], b + SPIGOT[2]))
        spigot += lug.rotate((0, 0, 90.0 + 120.0 * i))   # 45 deg underneath, prints without support
    part += spigot
    lock_hole = cyl_y(1.25, -SPIGOT[1] - 1, -SPIGOT[0] + 0.5, 0.0, b + SPIGOT[2] / 2).rotate((0, 0, 30.0))
    part -= lock_hole
    return largest(part)


def adapter(L, k=0.0):
    """Disc with the follower slot + a cage with two screw jaws that grip the thumb-turn wing."""
    A = L.A
    disc = cyl(29.0, A - 4.0, A)
    slot_len = (SPIRAL_R_IN - BLOCK[1] / 2 - 0.6, R_OUT + BLOCK[1] / 2 + 0.6)
    slot = cube(-BLOCK[0] / 2 - 0.2, BLOCK[0] / 2 + 0.2, slot_len[0], slot_len[1], A - 3.0, A + 1)
    disc -= slot.rotate((0, 0, SLOT_ANGLE - 90))
    disc -= cyl(SHAFT_D / 2 + 0.15, A - 3.5, A + 1, 24)                        # journal for the hub shaft
    for a in KNOB_POCKETS:                                                     # magnet pockets: home up / down / left / right
        disc -= cyl(KNOB_MAGNET[0] / 2 + 0.1, A - KNOB_MAGNET[1] - 0.2, A + 1, 24, *polar(KNOB_MAGNET_R, a))
    # Cage: two walls along x (the wing's length), jaws slide in y
    z_bottom = A - 4.0 - (WING_TOP[1] - WING_TOP[0]) - 8.0 - 2.0
    walls = cube(-24.0, 24.0, 14.0, 17.0, z_bottom, A - 3.99) + cube(-24.0, 24.0, -17.0, -14.0, z_bottom, A - 3.99)
    for sx in (-12.0, 12.0):                                                   # M3 x 3 heat-set inserts: the screws push the jaws
        walls -= cyl_y(JAW_INSERT_D / 2, -18, 18, sx, z_bottom + JAW_SCREW_Z)
    part = disc + walls
    return part.rotate((0, 0, k))


def jaws(L, k=0.0, gap=11.0):
    A = L.A
    z_bottom = A - 4.0 - (WING_TOP[1] - WING_TOP[0]) - 8.0 - 2.0
    out = Manifold()
    for side in (-1, 1):
        y0, y1 = sorted((side * gap / 2, side * (gap / 2 + 3.0)))
        jaw = cube(-22.0, 22.0, y0, y1, z_bottom, A - 4.3)
        outer = y0 if side < 0 else y1
        for sx in (-12.0, 12.0):                                               # dimple that keeps the screw tip in place
            jaw -= cyl_y(1.7, *sorted((outer - side * JAW_DIMPLE, outer + side)), sx, z_bottom + JAW_SCREW_Z)
        # grip ridges on the wing side (0.3 mm, they bite into the wing)
        face = y1 if side < 0 else y0
        for i in range(8):
            z = z_bottom + 2.0 + i * 2.2
            jaw += cube(-21.0, 21.0, face - 0.3 if side > 0 else face, face if side > 0 else face + 0.3, z, z + 0.6)
        out += jaw
    return out.rotate((0, 0, k))


def jaw_screws(L, k=0.0, gap=11.0):
    """M3 x JAW_SCREW_LEN socket screws through the wall inserts, tips in the jaw dimples."""
    z = L.A - 4.0 - (WING_TOP[1] - WING_TOP[0]) - 8.0 - 2.0 + JAW_SCREW_Z
    out = Manifold()
    for side in (-1, 1):
        tip = side * (gap / 2 + 3.0 - JAW_DIMPLE)
        head = tip + side * JAW_SCREW_LEN
        for sx in (-12.0, 12.0):
            a, b = sorted((tip, head))
            out += cyl_y(1.45, a, b, sx, z, 16)
            ha, hb = sorted((head, head + side * 3.0))
            out += cyl_y(2.75, ha, hb, sx, z, 24)
    return out.rotate((0, 0, k))


def follower(L, h=0.0, k=0.0):
    bx, by, bz = BLOCK
    r = pin_radius(h, k)
    block = cube(-bx / 2, bx / 2, r - by / 2, r + by / 2, L.A - 3.0 + 0.1, L.A - 3.0 + 0.1 + bz)
    block -= cyl(PIN_D / 2 - 0.05, L.A - 4, L.A + 1, 24, 0, r)
    return block.rotate((0, 0, SLOT_ANGLE - 90 + k))


def hub(L, h=0.0):
    """Spiral groove underneath, hub magnet, seat for the bought worm wheel on top."""
    part = cyl(HUB_R, L.hub0, L.spiral_top)
    part -= spiral_groove(L.hub0 - 1, L.hub0 + GROOVE_DEPTH)
    part += cyl(5.5, L.spiral_top - 0.01, L.wheel_mid - WHEEL["face"] / 2, 48)  # neck up to the wheel
    for a in (0.0, 180.0):                                                     # 2 x 8 mm steel dowels into the wheel web
        x, y = polar(6.0, a)
        part -= cyl(0.95, L.wheel_mid - WHEEL["face"] / 2 - 5.0, L.wheel_mid, 16, x, y)
    part -= cyl(SHAFT_D / 2 - 0.05, L.hub0 - 4, L.wheel_mid, 24)               # steel shaft, pressed in
    hx, hy = polar(HUB_MAGNET_R, hub_magnet_angle())
    part -= cyl(HUB_MAGNET[0] / 2 + 0.1, L.spiral_top - HUB_MAGNET[1] - 0.2, L.spiral_top + 1, 24, hx, hy)
    return part.rotate((0, 0, h))


def deck(L):
    """Over the drive layer: shaft bushing, motor clamp, worm end bearing; the pouch sits on it."""
    z0, z1 = L.deck0, L.deck0 + DECK_T
    part = cyl(BORE_R - 0.3, z0, z1)
    part += cyl(3.5, z0 - 3.0, z1, 32)                                         # bushing boss
    part -= cyl(SHAFT_D / 2 + 0.1, z0 - 4, z1 + 1, 24)
    # Worm end bearing: hanger down to the worm axis
    hx0 = WORM_X[0] - 2.4
    hanger = cube(hx0, WORM_X[0] + 0.6, CENTRE - 3.0, CENTRE + 3.0, L.wheel_mid - 3.0, z0 + 0.01)
    hanger -= cyl_x(1.15, hx0 - 1, WORM_X[0] + 1, CENTRE, L.wheel_mid, 16)
    # Motor clamp: cheeks down beside the gearbox
    x0 = WORM_X[1] + 0.5
    cheeks = Manifold()
    for y0, y1 in ((CENTRE + MOTOR["width"] / 2 + 0.1, CENTRE + MOTOR["width"] / 2 + 1.8),
                   (CENTRE - MOTOR["width"] / 2 - 1.8, CENTRE - MOTOR["width"] / 2 - 0.1)):
        cheeks += cube(x0 + 1.0, x0 + MOTOR["gearbox"] - 1.0, y0, y1, L.wheel_mid - 2.0, z0 + 0.01)
    part += hanger + cheeks
    for x, y in board.CLAMPS:                                                  # posts that hold the PCB down
        part += cyl(1.6, L.drive0 + board.THICKNESS + 0.05, z0 + 0.01, 16, x, y)
    for a in CASE_BOSSES:
        part -= cyl(1.25, z0 - 1, z1 + 1, 16, *polar(BORE_R - 2.0, a))       # clearance for M2 x 5 screws into the case
    part -= cyl(1.7, z0 - 1, z1 + 1, 16, *board.FIXED["D1"][:2])               # light pipe
    part -= cube(-33.0, -24.0, -12.0, -6.0, z0 - 1, z1 + 1)                    # motor + battery leads
    return largest(part)


def case(L):
    b = L.base_top
    part = ring(BORE_R, CASE_R, b, L.cap0)
    # Bayonet band: thicker inside the bottom, three L-slots for the base lugs
    band = ring(SPIGOT[1] + 0.3, BORE_R + 0.01, b, b + SPIGOT[2] + 2.0)
    for i in range(3):
        a0 = 90.0 + 120.0 * i
        entry = cube(-LUG[0] / 2 - 0.3, LUG[0] / 2 + 0.3, SPIGOT[1] - 0.5, SPIGOT[1] + LUG[1] + 0.3, b - 1, b + SPIGOT[2] + 0.3).rotate((0, 0, a0 - TWIST))
        run = Manifold()
        for s in np.linspace(0, TWIST, 11):
            run += cube(-LUG[0] / 2 - 0.3, LUG[0] / 2 + 0.3, SPIGOT[1] - 0.5, SPIGOT[1] + LUG[1] + 0.3, b + SPIGOT[2] - LUG[2] - LUG[1] - 0.3, b + SPIGOT[2] + 0.3).rotate((0, 0, a0 - s))  # room for the lug's chamfer
        band -= entry + run
    part += band
    part -= cyl_y(1.6, -CASE_R - 1, -SPIGOT[1], 0.0, b + SPIGOT[2] / 2).rotate((0, 0, 30.0))   # M3 lock screw
    # Deck bosses
    for a in CASE_BOSSES:
        x, y = polar(BORE_R - 2.0, a)
        boss = (cyl(3.2, L.deck0 - 4.0, L.deck0, 32, x, y) ^ cyl(BORE_R + 0.5, 0, 200)) - cyl(0.8, L.deck0 - 5, L.deck0 + 1, 16, x, y)   # M2 self-tapping
        cone = Manifold.cylinder(3.2, 0.01, 3.2, circular_segments=32).translate((x, y, L.deck0 - 7.2)) ^ cyl(BORE_R + 0.5, 0, 200)
        part += boss + cone
    # USB-C opening and the flexure side button (both at the PCB)
    jx, jy = board.FIXED["J1"][:2]
    usb_z = L.drive0 + board.THICKNESS + 1.6
    part -= cube(jx - 6.0, jx + 6.0, -CASE_R - 1, -28.0, usb_z - 2.6, usb_z + 2.6)
    sx, sy, srot = board.FIXED["SW1"][:3]
    a = math.degrees(math.atan2(sy, sx))
    bz = L.drive0 + board.THICKNESS + 1.8
    slot = cube(BORE_R - 1, CASE_R + 1, -5.3, 5.3, bz - 6.5, bz + 6.5) - cube(BORE_R - 1, CASE_R + 1, -4.5, 4.5, bz - 7.0, bz + 5.7)
    nub = cube(BORE_R - 0.25, BORE_R + 0.01, -1.4, 1.4, bz - 1.4, bz + 1.4)
    part -= slot.rotate((0, 0, a))
    part -= (cube(BORE_R + 0.9, CASE_R + 1, -4.6, 4.6, bz - 4.0, bz + 7.0)).rotate((0, 0, a))  # thinner tongue
    part += nub.rotate((0, 0, a))
    # PCB ledges (the deck's posts hold the board down from above)
    for x, y in board.CLAMPS:
        ledge = cyl(board.CLAMP_R, L.drive0 - 2.0, L.drive0, 24, x, y) + Manifold.cylinder(3.0, 0.01, board.CLAMP_R, circular_segments=24).translate((x, y, L.drive0 - 5.0))   # 54 deg: no support
        part += ledge ^ cyl(BORE_R + 0.5, 0, 200)
    # Snap groove for the cap
    part -= ring(BORE_R - 0.01, BORE_R + 0.5, L.cap0 - 2.4, L.cap0 - 1.4)
    return largest(part)


def cap(L):
    part = cyl(CASE_R, L.cap0, L.top)
    spigot = ring(BORE_R - 1.4, BORE_R - 0.2, L.cap0 - 2.6, L.cap0 + 0.01)
    for a in (30.0, 150.0, 270.0):
        spigot += cyl(0.8, L.cap0 - 2.3, L.cap0 - 1.5, 16, *polar(BORE_R - 0.2, a)) ^ cyl(BORE_R + 0.3, 0, 200)
    part += spigot
    dx, dy = board.FIXED["D1"][:2]
    part -= cyl(1.7, L.cap0 - 1, L.top + 1, 24, dx, dy)                           # light pipe window
    return largest(part)


def light_pipe(L):
    dx, dy = board.FIXED["D1"][:2]
    return cyl(1.5, L.drive0 + board.THICKNESS + 0.7, L.top - 0.01, 24, dx, dy)


def install_jig(L, door):
    """Centres the base on the thumb-turn while the tape sets: sits in the base, the wing goes through its slot."""
    b = door.base_h
    jig = cyl(SPIGOT[0] - 0.3, b, b + 3.0) + cyl(SPIGOT[1] + 2.0, b + 3.0, b + 5.0)
    jig -= rounded_box(WING_LONG_MAX + 1.0, WING_THICK[1] + 1.0, 3.0, b - 1, b + 6)
    return jig


def height_gauge(L, door):
    """C-shaped spacer: stands on the base spigot and holds the adapter disc at the right height while tightening."""
    b = door.base_h
    g = ring(29.5, SPIGOT[1], b + SPIGOT[2], L.A - 4.0) - cube(-8, 8, 0, 50, -10, 200)
    return g


# ---------------------------------------------------------------------------------------------------- assembly
def assembly(door_name="rosette", h=FREE_PLAY / 2, k=0.0, wing=(40.0, 11.0, 17.0), knob_pocket=KNOB_POCKETS[0]):
    door = DOORS[door_name]
    L = layout(door)
    knob_mag, hub_mag = magnets(L, h, k, knob_pocket)
    return {
        "base": (base(L, door), (0.92, 0.92, 0.9)),
        "case": (case(L), "case"),
        "adapter": (adapter(L, k), "adapter"),
        "jaws": (jaws(L, k, gap=wing[1]), (0.5, 0.52, 0.56)),
        "jaw_screws": (jaw_screws(L, k, gap=wing[1]), "metal"),
        "follower": (follower(L, h, k), "slider"),
        "pin": (pin_model(L, h, k), "metal"),
        "hub": (hub(L, h), "hub"),
        "wheel": (wheel_model(L, h), (0.95, 0.95, 0.9)),
        "shaft": (shaft_model(L), "metal"),
        "dowels": (dowels_model(L, h), "metal"),
        "worm": (worm_model(L), (0.8, 0.65, 0.3)),
        "motor": (motor_model(L), (0.75, 0.6, 0.25)),
        "pcb": (pcb_model(L), (0.1, 0.45, 0.25)),
        "deck": (deck(L), "bracket"),
        "pouch": (pouch_model(L), (0.55, 0.55, 0.6)),
        "cap": (cap(L), "case"),
        "light_pipe": (light_pipe(L), (0.95, 0.97, 1.0)),
        "knob_magnet": (knob_mag, (0.6, 0.6, 0.65)),
        "hub_magnet": (hub_mag, (0.6, 0.6, 0.65)),
        "thumb_turn": (thumb_turn(L, *wing[:2], top=wing[2], k=k), "metal"),
    }


PRINT = {   # part: (function, print rotation)
    "case": (lambda L, d: case(L), (0, 0, 0)),
    "adapter": (lambda L, d: adapter(L), (180, 0, 0)),
    "jaws": (lambda L, d: jaws(L, gap=11.0).decompose()[0], (90, 0, 0)),
    "follower": (lambda L, d: follower(L), (0, 0, 0)),
    "hub": (lambda L, d: hub(L), (0, 0, 0)),
    "deck": (lambda L, d: deck(L), (180, 0, 0)),
    "cap": (lambda L, d: cap(L), (180, 0, 0)),
    "light_pipe": (lambda L, d: light_pipe(L), (0, 0, 0)),
}
PER_DOOR = {
    "base": (lambda L, d: base(L, d), (0, 0, 0)),
    "install_jig": (lambda L, d: install_jig(L, d), (180, 0, 0)),
    "height_gauge": (lambda L, d: height_gauge(L, d), (0, 0, 0)),
}


def export():
    out = HERE / "stl"
    out.mkdir(exist_ok=True)

    def save(part, rot, name):
        p = part.rotate(rot)
        p = p.translate((0, 0, -p.bounding_box()[2]))
        assert p.status().name == "NoError" and len(p.decompose()) == 1, name
        m = to_trimesh(p)
        m.export(out / f"{name}.stl")
        print(f"  {name + '.stl':30s} {np.round(m.extents, 1)} mm  {m.volume / 1000:5.1f} cm3")

    L = layout(DOORS["rosette"])
    for name, (make, rot) in PRINT.items():
        save(make(L, None), rot, name)
    for door in DOORS.values():
        L = layout(door)
        for name, (make, rot) in PER_DOOR.items():
            save(make(L, door), rot, f"{name}_{door.name}")


if __name__ == "__main__":
    for door in DOORS.values():
        L = layout(door)
        print(f"{door.name:10s}: {2 * CASE_R:.1f} mm x {L.top:.1f} mm from the door (base {door.base_h} mm)")
    print()
    export()
    import checks
    sys.exit(0 if checks.run() else 1)
