"""Single-servo smart lock with a spiral (scroll) lost-motion coupling, around the unchanged V3 PCB.

No second servo, no clutch to engage. Under the servo hub is a spiral groove (~2.75 turns). A steel pin on a small
block, which slides in a radial slot of the thumb-turn adapter, runs in that groove:

    * inside the spiral the hub and the thumb-turn turn independently: the key turns freely (the pin just walks
      along the spiral, the block slides in its slot)
    * at either end of the spiral the hub drives the thumb-turn
    * after every movement the servo backs off into the spiral (counted by a hall sensor on the hub), leaving room
      for the key to undo that movement by hand

    door side                                                                           cap side
    floor + door tab | thumb-turn adapter + follower | spiral hub | servo | PCB | cap

Coordinates: z = 0 is the door side of the floor, +z away from the door, +y up (towards the door tab / handle).
Angles: world frame with the thumb-turn at home; the hub rotation h (deg) is the spiral position: h = 0 inner end of
the spiral, h = SPIRAL_TURNS * 360 outer end (q = h - thumb-turn angle in motion.h).

    pip install manifold3d trimesh
    python lock.py      # exports the STLs and runs every check (fit, motion over the whole spiral, assembly, ...)
"""

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold, Mesh

HERE = Path(__file__).parent
ORIGINAL = HERE.parent  # the original V3 case STLs

SEG = 96
FIT = 0.3

# ---------------------------------------------------------------------------------------------------- your door
THUMBTURN_HEIGHT = 23.5    # MEASURE: escutcheon / door surface (where the lock's floor sits) to the top of the thumb-turn

# ---------------------------------------------------------------------------------------------------- bought parts
PCB_DIAMETER = 78.0        # V3 PCB, unchanged
PCB_THICKNESS = 1.6
PCB_BELOW = 2.0            # solder joints under the PCB (wires go onto the header pins from the top)
PCB_ABOVE = 5.0            # tallest part on top: ESP-12F 3 mm, header plastic 2.5 mm + soldered wire (pins cut short)

SERVO_W, SERVO_L = 19.9, 40.9           # MG996R 360 (continuous rotation) body (+0.2), shaft 10.2 mm from one end
SERVO_SHAFT_FROM_END = 10.2
SERVO_HEIGHT = 36.5                     # output face to back
SERVO_TAB_FROM_FACE = 7.0               # underside of the mounting tabs
SERVO_TAB_T = 2.5
SERVO_TAB_LENGTH = 54.0
SERVO_TAB_HOLE_SPACING = 49.5
SERVO_FACE_GAP = 3.2                    # hub top to servo face: horn + spline boss
HORN_SLOT = (30.6, 6.8, 2.4)            # straight servo horn cut to 30 mm, sits in the hub top

HALL = (4.6, 4.2, 1.6)                  # A3144 hall switch, TO-92S lying flat
REED = (2.6, 14.5)                      # reed glass diameter, length
PIN_D = 3.0                             # steel dowel pin (or a piece of 3 mm rod)

# ---------------------------------------------------------------------------------------------------- spiral coupling
SPIRAL_TURNS = 2.75        # free play; must match MOTION_SPIRAL_TURNS in code/smart_lock/motion.h
SPIRAL_R_IN = 8.0          # pin centre at the inner end
SPIRAL_PITCH = 5.0         # radial step per turn: groove + wall between the turns
GROOVE_W = PIN_D + 0.4
GROOVE_DEPTH = 2.6
HUB_GAP = 0.3              # hub underside above the adapter
HUB_FLOOR = 1.3            # between the groove and the horn pocket
SLOT_ANGLE = 90.0          # direction of the follower slot in the adapter (+y)
BLOCK = (5.8, 4.6, 2.9)    # follower block: tangential, radial, height
SLOT_DEPTH = 3.0
ADAPTER_FLOOR = 5.0        # thumb-turn pocket floor (original 7.5), holds the 3 mm deep slot
MAGNET_R = 24.2            # knob magnet hole in the original adapter (+x)
KNOB_REED_ANGLE = 0.0      # knob reed beside the magnet when the thumb-turn is home
KNOB_REED_R = 30.9         # just outside the adapter's sweep (its corners reach r 29.2)
HALL_ANGLE = 180.0         # hub sensor position
HALL_R = 18.0
HUB_MAGNET_PHASE = 135.0   # the hub magnet passes the hall sensor 135 deg after reversing from either spiral end

# ---------------------------------------------------------------------------------------------------- case
WALL = 1.8
BORE = PCB_DIAMETER / 2 + 0.3
SHELL_R = BORE + WALL
PLATE_T = 3.0
CAP_T = 1.5
BOSS_ANGLES = (90.0, 210.0, 330.0)      # chassis screw bosses
LEDGE_ANGLES = (45.0, 135.0, 225.0, 315.0)
BUTTON_NUB = 0.2                        # how far the button tongue's nub reaches inside the bore (PCB must slide past)
DIFFUSER_TABS = (70.0, 160.0, 290.0)    # the LED diffuser rests on these, clear of the headers

# PCB parts that matter for the case (x, y from the EasyEDA file, mm from the board centre)
USB = (-35.5, -0.3)
BUTTON = (34.4, -0.2)


# ---------------------------------------------------------------------------------------------------- layout
@dataclass
class Layout:
    A: float = 0       # adapter top
    hub0: float = 0    # hub underside
    hub_top: float = 0
    F: float = 0       # servo output face
    plate: float = 0   # chassis plate underside
    pcb: float = 0     # PCB underside
    top: float = 0     # shell rim = cap underside


def layout(thumbturn=THUMBTURN_HEIGHT):
    L = Layout()
    L.A = thumbturn + 0.5 + ADAPTER_FLOOR
    L.hub0 = L.A + HUB_GAP
    L.hub_top = L.hub0 + GROOVE_DEPTH + HUB_FLOOR + HORN_SLOT[2]
    L.F = L.hub_top + SERVO_FACE_GAP
    L.plate = L.F + SERVO_TAB_FROM_FACE - PLATE_T
    L.pcb = L.F + SERVO_HEIGHT + PCB_BELOW
    L.top = L.pcb + PCB_THICKNESS + PCB_ABOVE
    return L


L = layout()
R_OUT = SPIRAL_R_IN + SPIRAL_PITCH * SPIRAL_TURNS          # pin centre at the outer end
HUB_R = R_OUT + GROOVE_W / 2 + 1.6
FREE_PLAY = SPIRAL_TURNS * 360.0


# ---------------------------------------------------------------------------------------------------- helpers
def cube(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl(r, z0, z1, seg=SEG, x=0.0, y=0.0):
    return Manifold.cylinder(z1 - z0, r, circular_segments=seg).translate((x, y, z0))


def ring(r_in, r_out, z0, z1):
    return cyl(r_out, z0, z1) - cyl(r_in, z0 - 1, z1 + 1)


def polar(r, angle_deg):
    a = math.radians(angle_deg)
    return r * math.cos(a), r * math.sin(a)


def from_stl(path):
    mesh = trimesh.load(path)
    return Manifold(Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32), tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))


def largest(part):
    return max(part.decompose(), key=lambda p: p.volume())


def to_trimesh(part):
    mesh = part.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts))


# ---------------------------------------------------------------------------------------------------- spiral geometry
def spiral_point(t):
    """Pin centre in the hub's own frame at spiral position t (turns from the inner end)."""
    return polar(SPIRAL_R_IN + SPIRAL_PITCH * t, SLOT_ANGLE - 360.0 * t)


def pin_radius(h, k=0.0):
    """Radius of the pin for hub rotation h and thumb-turn rotation k (deg)."""
    t = (h - k) / 360.0
    return SPIRAL_R_IN + SPIRAL_PITCH * t


def spiral_groove(z0, z1):
    """Groove along the spiral, round ends, built from hulls of short segments."""
    steps = int(SPIRAL_TURNS * 48)
    disk = lambda t: cyl(GROOVE_W / 2, z0, z1, 24, *spiral_point(t))  # noqa: E731
    groove = Manifold()
    prev = disk(0.0)
    for i in range(1, steps + 1):
        cur = disk(SPIRAL_TURNS * i / steps)
        groove += Manifold.hull(prev + cur)
        prev = cur
    return groove


# ---------------------------------------------------------------------------------------------------- bought parts (for checks and renders)
def servo_model():
    sy0, sy1 = -SERVO_SHAFT_FROM_END, SERVO_L - SERVO_SHAFT_FROM_END
    body = cube(-SERVO_W / 2 + 0.1, SERVO_W / 2 - 0.1, sy0 + 0.1, sy1 - 0.1, L.F, L.F + SERVO_HEIGHT)
    mid = (sy0 + sy1) / 2
    tabs = cube(-SERVO_W / 2 + 0.1, SERVO_W / 2 - 0.1, mid - SERVO_TAB_LENGTH / 2, mid + SERVO_TAB_LENGTH / 2,
                L.F + SERVO_TAB_FROM_FACE, L.F + SERVO_TAB_FROM_FACE + SERVO_TAB_T)
    boss = cyl(6.0, L.F - 1.2, L.F + 0.01) + cyl(2.9, L.hub_top - 0.1, L.F)
    horn = cube(-HORN_SLOT[0] / 2 + 0.3, HORN_SLOT[0] / 2 - 0.3, -3.2, 3.2, L.hub_top - HORN_SLOT[2], L.hub_top + 0.2)
    horn += cyl(4.6, L.hub_top - HORN_SLOT[2] - 1.0, L.hub_top + 0.2, 32)
    return body + tabs + boss, horn


def pcb_model():
    z0, z1 = L.pcb, L.pcb + PCB_THICKNESS
    board = cyl(PCB_DIAMETER / 2, z0, z1)
    parts = [
        cube(USB[0] - 3.7, USB[0] + 3.7, USB[1] - 4.0, USB[1] + 4.0, z1, z1 + 2.9),     # micro USB, opening at -x
        cube(BUTTON[0] - 2.5, BUTTON[0] + 4.3, BUTTON[1] - 3.0, BUTTON[1] + 3.0, z1, z1 + 3.6),  # side button
        cube(21.3 - 8, 21.3 + 8, -4.7 - 12, -4.7 + 12, z1, z1 + 3.0),               # ESP-12F
        cube(-3.5 - 3.9, -3.5 + 3.9, 34.7 - 1.3, 34.7 + 1.3, z1, z1 + 4.5),         # programming header (pins cut)
        cube(-20.7 - 3.9, -20.7 + 3.9, -23 - 1.3, -23 + 1.3, z1, z1 + 4.5),         # servo header H2
        cube(28.8 - 1.3, 28.8 + 1.3, 17.5 - 2.6, 17.5 + 2.6, z1, z1 + 4.5),         # H3
        cube(-18.9 - 1.3, -18.9 + 1.3, 0.4 - 2.6, 0.4 + 2.6, z1, z1 + 4.5),         # H5
        cube(-29 - 3.3, -29 + 3.3, 10.5 - 3.5, 10.5 + 3.5, z1, z1 + 1.8),           # AMS1117
    ]
    for p in parts:
        board += p
    pins = Manifold()
    for x, y, n, horizontal in ((-3.5, 34.7, 3, True), (-20.7, -23, 3, True), (28.8, 17.5, 2, False), (-18.9, 0.4, 2, False)):
        for i in range(n):
            off = (i - (n - 1) / 2) * 2.54
            px, py = (x + off, y) if horizontal else (x, y + off)
            pins += cube(px - 0.4, px + 0.4, py - 0.4, py + 0.4, z0 - 1.5, z0)
    return board + pins


def thumb_turn():
    wing = CrossSection.square((40, 11), center=True).offset(2.5, JoinType.Round, circular_segments=24).extrude(15.5)
    rosette = cyl(24, -9, -1) + cyl(5.5, -1, THUMBTURN_HEIGHT - 15.5)
    return wing.translate((0, 0, THUMBTURN_HEIGHT - 15.5)) + rosette


def hall_model():
    hx, hy, hz = HALL
    x, y = polar(HALL_R, HALL_ANGLE)
    return cube(x - hx / 2, x + hx / 2, y - hy / 2, y + hy / 2, L.hub_top + 0.8, L.hub_top + 0.8 + hz)


def reed_model():
    x, y = polar(KNOB_REED_R, KNOB_REED_ANGLE)
    z = L.A - 4.5
    return Manifold.cylinder(REED[1], REED[0] / 2, circular_segments=24).rotate((-90, 0, 0)).translate((x, y - REED[1] / 2, z))


def pin_model(k=0.0, h=None):
    """Steel pin, rides with the follower."""
    r = pin_radius(h if h is not None else 0.0, k)
    x, y = polar(r, SLOT_ANGLE + k)
    return cyl(PIN_D / 2, L.A - BLOCK[2] - 0.05, L.hub0 + GROOVE_DEPTH - 0.5, 24, x, y)


# ---------------------------------------------------------------------------------------------------- printed parts
def knob_adapter():
    """Original thumb-turn adapter, floor thinned, a disc on top with the radial slot for the follower."""
    original = from_stl(ORIGINAL / "doorknob_servo_adapter.stl")
    solid = original + (Manifold.hull(original) ^ cube(-100, 100, -100, 100, 0, 7.49))
    trimmed = solid ^ cube(-100, 100, -100, 100, 7.5 - ADAPTER_FLOOR, 100)
    adapter = trimmed.rotate((180, 0, 0)).translate((0, 0, L.A + 7.5 - ADAPTER_FLOOR))
    slot_len = (SPIRAL_R_IN - BLOCK[1] / 2 - 0.6, R_OUT + BLOCK[1] / 2 + 0.6)
    disc = cyl(slot_len[1] + 1.4, L.A - 4.0, L.A)
    part = adapter + disc
    slot = cube(-BLOCK[0] / 2 - 0.2, BLOCK[0] / 2 + 0.2, slot_len[0], slot_len[1], L.A - SLOT_DEPTH, L.A + 1)
    part -= slot.rotate((0, 0, SLOT_ANGLE - 90))
    # Knob magnet: 5 x 3 mm, at the bottom of a 6 mm hole beside the knob reed
    part -= cyl(2.6, L.A - 6.0, L.A + 1, 32, x=MAGNET_R)
    return largest(part)


def follower(k=0.0, h=0.0):
    """Block that slides in the adapter slot; the steel pin is pressed into it."""
    bx, by, bz = BLOCK
    r = pin_radius(h, k)
    block = cube(-bx / 2, bx / 2, r - by / 2, r + by / 2, L.A - SLOT_DEPTH + 0.1, L.A - SLOT_DEPTH + 0.1 + bz)
    block -= cyl(PIN_D / 2 - 0.05, L.A - SLOT_DEPTH, L.A + 1, 24, 0, r)  # press fit
    return block.rotate((0, 0, SLOT_ANGLE - 90 + k))


def hub(h=0.0):
    """Spiral groove underneath, servo horn on top. h = hub rotation (deg), 0 = pin at the inner end."""
    part = cyl(HUB_R, L.hub0, L.hub_top)
    part -= spiral_groove(L.hub0 - 1, L.hub0 + GROOVE_DEPTH)
    hx, hy, hz = HORN_SLOT
    part -= cube(-hx / 2, hx / 2, -hy / 2, hy / 2, L.hub_top - hz, L.hub_top + 1)
    part -= cyl(4.9, L.hub_top - hz - 1.0, L.hub_top + 1, 48)
    # Long M3 horn screw from below through the hub into the servo spline, head sunk in
    part -= cyl(1.7, L.hub0 - 1, L.hub_top, 24)
    part -= cyl(3.0, L.hub0 - 1, L.hub0 + GROOVE_DEPTH, 32)
    # Hub magnet (3 x 2 mm) in the top face, passes the hall sensor 135 deg after reversing from a spiral end
    mx, my = polar(HALL_R, hub_magnet_angle())
    part -= cyl(1.6, L.hub_top - 2.2, L.hub_top + 1, 24, mx, my)
    return part.rotate((0, 0, h))


def hub_magnet_angle():
    # Reversing from the outer end (h = FREE_PLAY) the magnet must reach the sensor after HUB_MAGNET_PHASE deg:
    # h + mu = sensor  with h = FREE_PLAY - phase. From the inner end (h = 0) going forward this is phase deg too
    # when FREE_PLAY - 2 * phase is a whole number of turns (2.75 turns, 135 deg).
    return (HALL_ANGLE - (FREE_PLAY - HUB_MAGNET_PHASE)) % 360.0


def chassis():
    """Plate the servo hangs from, knob reed holder, hall sensor arm."""
    z0, z1 = L.plate, L.plate + PLATE_T
    plate = cyl(BORE - 0.3, z0, z1)
    for a in LEDGE_ANGLES:                 # notches so the plate passes the PCB ledges
        x, y = polar(BORE, a)
        plate -= cyl(4.5, z0 - 1, z1 + 1, 32, x=x, y=y)
    sy0, sy1 = -SERVO_SHAFT_FROM_END, SERVO_L - SERVO_SHAFT_FROM_END
    plate -= cube(-SERVO_W / 2, SERVO_W / 2, sy0, sy1, z0 - 1, z1 + 1)
    mid = (sy0 + sy1) / 2
    for dy in (-SERVO_TAB_HOLE_SPACING / 2, SERVO_TAB_HOLE_SPACING / 2):
        for dx in (-5, 5):
            plate -= cyl(1.25, z0 - 1, z1 + 1, 16, x=dx, y=mid + dy)
    for a in BOSS_ANGLES:
        x, y = polar(BORE - 2.0, a)
        plate -= cyl(1.7, z0 - 1, z1 + 1, 24, x=x, y=y)
    # Knob reed holder: a leg down beside the adapter (outside its sweep), the reed lies tangentially
    rx, _ = polar(KNOB_REED_R, KNOB_REED_ANGLE)
    reed_z = L.A - 4.5
    leg = cube(rx - 1.5, rx + 2.4, -8.0, 8.0, reed_z - 2.6, z0 + 0.01)
    leg -= Manifold.cylinder(20, REED[0] / 2 + 0.15, circular_segments=24).rotate((-90, 0, 0)).translate((rx, -10, reed_z))
    leg -= cube(rx - 0.5, rx + 0.5, -10, 10, reed_z, reed_z + 3)          # wire channel
    # Hall sensor arm above the hub
    hx, hy = polar(HALL_R, HALL_ANGLE)
    arm = cube(hx - 3.8, hx + 3.0, hy - 4.0, hy + 4.0, L.hub_top + 0.6, z0 + 0.01)
    arm -= cube(hx - HALL[0] / 2 - 0.1, hx + HALL[0] / 2 + 0.1, hy - HALL[1] / 2 - 0.1, hy + HALL[1] / 2 + 0.1, L.hub_top + 0.5, L.hub_top + 0.8 + HALL[2] + 0.2)
    arm -= cube(hx - 1.0, hx + 1.0, hy - 6, hy + 6, L.hub_top + 0.8, z0 + 1)  # leads up to the plate
    # Wire passages up to the PCB
    plate -= cube(14.0, 22.0, -26.0, -18.0, z0 - 1, z1 + 1)
    plate -= cube(-26.0, -14.0, -6.0, 6.0, z0 - 1, z1 + 1)
    return largest(plate + leg + arm)


def shell():
    original = from_stl(ORIGINAL / "bottom.stl")
    # Door end from the original bottom: floor with its cut-outs, and the mounting tab
    floor = original ^ cyl(BORE + 0.2, -1, 1.0)
    tab = original ^ cube(-50, 50, SHELL_R - 0.5, 100, -1, 50)
    root = tab ^ cube(-50, 50, 43.6, 45.0, -1, 50)
    tab += Manifold.hull(root + root.translate((0, -(43.6 - BORE), 0)))
    tube = ring(BORE, SHELL_R, 0, L.top)
    part = floor + tab + tube
    # Chassis bosses with M3 self-tapping holes
    for a in BOSS_ANGLES:
        x, y = polar(BORE - 2.0, a)
        boss = (cyl(3.6, L.plate - 5.0, L.plate, 32, x=x, y=y) + cube(-3.6, 3.6, 0, 4, L.plate - 5.0, L.plate).rotate((0, 0, a - 90)).translate((x, y, 0))) ^ cyl(BORE + 0.5, 0, L.top)
        boss -= cyl(1.25, L.plate - 6, L.plate + 1, 16, x=x, y=y)
        cone = Manifold.cylinder(3.6, 0.01, 3.6, circular_segments=32).translate((x, y, L.plate - 8.6))  # prints without support
        part += boss + (cone ^ cyl(BORE + 0.5, 0, L.top))
    # PCB ledges
    for a in LEDGE_ANGLES:
        x, y = polar(BORE, a)
        ledge = cyl(3.2, L.pcb - 2.0, L.pcb, 32, x=x, y=y) + Manifold.cylinder(3.2, 0.01, 3.2, circular_segments=32).translate((x, y, L.pcb - 5.2))
        part += ledge ^ cyl(BORE + 0.5, 0, L.top) - cyl(BORE - 1.6, 0, L.top + 1)
    # Micro USB opening (-x)
    usb_z = L.pcb + PCB_THICKNESS + 1.45
    part -= cube(-SHELL_R - 1, -BORE + 1, USB[1] - 6.0, USB[1] + 6.0, usb_z - 3.8, usb_z + 3.8)
    # Side button (+x): a flexure tongue in the wall with a nub that presses the switch
    btn_z = L.pcb + PCB_THICKNESS + 1.8
    tongue_w, tongue_h = 9.0, 13.0
    slot = cube(BORE - 1, SHELL_R + 1, BUTTON[1] - tongue_w / 2 - 0.8, BUTTON[1] + tongue_w / 2 + 0.8, btn_z - tongue_h / 2, btn_z + tongue_h / 2 + 0.8)
    keep = cube(BORE - 1, SHELL_R + 1, BUTTON[1] - tongue_w / 2, BUTTON[1] + tongue_w / 2, btn_z - tongue_h / 2 - 1, btn_z + tongue_h / 2)
    part -= slot - keep
    part -= cube(BORE + 1.0, SHELL_R + 1, BUTTON[1] - tongue_w / 2 - 1, BUTTON[1] + tongue_w / 2 + 1, btn_z - tongue_h / 2 + 2.5, btn_z + tongue_h / 2 + 1)  # thinner tongue
    part += cube(BORE - BUTTON_NUB, BORE + 0.01, BUTTON[1] - 1.5, BUTTON[1] + 1.5, btn_z - 1.5, btn_z + 1.5)  # nub
    part += cube(SHELL_R - 0.6, SHELL_R + 0.6, BUTTON[1] - 2.5, BUTTON[1] + 2.5, btn_z - 2.5, btn_z + 2.5) ^ cyl(SHELL_R + 0.6, 0, L.top) - cyl(SHELL_R - 0.9, 0, L.top + 1)  # finger pad
    # Snap groove for the cap
    part -= ring(BORE - 0.01, BORE + 0.6, L.top - 2.6, L.top - 1.4)
    return largest(part)


def cap():
    """Holds the PCB down; the original LED diffuser (cover_led.stl, 58 mm) drops into its window."""
    z0 = L.top
    part = cyl(SHELL_R, z0, z0 + CAP_T)
    part -= cyl(29.4, z0 - 1, z0 + CAP_T + 1)            # LED window
    for a in DIFFUSER_TABS:                              # the diffuser rests on three small tabs
        x, y = polar(30.6, a)
        part += cube(-1.6, 1.6, -2.5, 2.5, z0 - 0.8, z0 + 0.01).rotate((0, 0, a - 90)).translate((x, y, 0))
    spigot = ring(BORE - 1.4, BORE - 0.25, L.pcb + PCB_THICKNESS, z0 + 0.01)
    for (x, y), half in ((USB, 17), (BUTTON, 14)):       # clear the USB socket and the side button
        a = math.degrees(math.atan2(y, x))
        wedge = CrossSection([[(0, 0), polar(60, a - half), polar(60, a + half)]]).extrude(PCB_ABOVE + 1).translate((0, 0, L.pcb + PCB_THICKNESS - 0.5))
        spigot -= wedge
    for a in (90, 210, 330):
        x, y = polar(BORE - 0.25, a)
        spigot += cyl(0.9, L.top - 2.4, L.top - 1.6, 16, x=x, y=y) ^ cyl(BORE + 0.35, 0, L.top)
    return largest(part + spigot)


def diffuser():
    """The original LED diffuser (its STL is not centred)."""
    part = from_stl(ORIGINAL / "cover_led.stl")
    x0, y0, z0, x1, y1, _ = part.bounding_box()
    return part.translate((-(x0 + x1) / 2, -(y0 + y1) / 2, -z0))


# ---------------------------------------------------------------------------------------------------- assembly
def assembly(h=FREE_PLAY / 2, k=0.0):
    """h: hub rotation (spiral position, 0 .. FREE_PLAY when k = 0), k: thumb-turn rotation (deg)."""
    servo, horn = servo_model()
    return {
        # name: (part, colour, printed)
        "shell": (shell(), "case", True),
        "knob_adapter": (knob_adapter().rotate((0, 0, k)), "adapter", True),
        "follower": (follower(k, h), "slider", True),
        "pin": (pin_model(k, h), "metal", False),
        "hub": (hub(h), "hub", True),
        "chassis": (chassis(), "bracket", True),
        "cap": (cap(), "case", True),
        "servo": (servo, "servo", False),
        "horn": (horn.rotate((0, 0, h)), "metal", False),
        "hall": (hall_model(), (0.15, 0.15, 0.15), False),
        "reed": (reed_model(), (0.8, 0.85, 0.9), False),
        "pcb": (pcb_model(), (0.1, 0.45, 0.25), False),
        "thumb_turn": (thumb_turn().rotate((0, 0, k)), "metal", False),
    }


PRINT_ROTATION = {
    "shell": (0, 0, 0),           # floor on the plate
    "knob_adapter": (180, 0, 0),  # slotted top on the plate
    "follower": (0, 0, 0),
    "hub": (180, 0, 0),           # horn side on the plate, the spiral groove faces up
    "chassis": (180, 0, 0),       # plate on the bed
    "cap": (180, 0, 0),           # outside face on the plate
}

PARTS = {"shell": shell, "knob_adapter": knob_adapter, "follower": follower, "hub": hub, "chassis": chassis, "cap": cap}


def export():
    for name, make in PARTS.items():
        p = make().rotate(PRINT_ROTATION[name])
        p = p.translate((0, 0, -p.bounding_box()[2]))
        assert p.status().name == "NoError" and len(p.decompose()) == 1, name
        mesh = to_trimesh(p)
        mesh.export(HERE / f"{name}.stl")
        print(f"  {name + '.stl':20s} {np.round(mesh.extents, 1)} mm  {mesh.volume / 1000:5.1f} cm3")


if __name__ == "__main__":
    print(f"Layout for a {THUMBTURN_HEIGHT} mm thumb-turn: adapter top {L.A:.1f}, hub {L.hub0:.1f}-{L.hub_top:.1f}, "
          f"servo face {L.F:.1f}, PCB {L.pcb:.1f}, cap {L.top + CAP_T:.1f} mm")
    print(f"Envelope: {2 * SHELL_R:.1f} mm diameter x {L.top + CAP_T:.1f} mm from the door")
    print(f"Spiral: {SPIRAL_TURNS} turns, pin radius {SPIRAL_R_IN}-{R_OUT} mm, hub radius {HUB_R:.1f} mm\n")
    export()
    import checks
    checks.run()
