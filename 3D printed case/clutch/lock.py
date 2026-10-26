"""Compact smart lock with servo clutch, built around the unchanged V3 PCB (round, 78 mm).

One shell replaces the old bottom + middle (+ extension ring). Everything inside hangs from a chassis plate:

    door side                                                                           cap side
    floor + door tab | thumb-turn adapter | clutch (hub + slider + fork, SG90) | servo | PCB | cap

    knob_adapter   the original thumb-turn pocket, thinner floor, 6 dog slots in its top face
    hub            hex prism on the servo horn; the slider rides on its OUTSIDE (no separate shaft = shorter)
    slider         6 dog teeth, groove for the fork pins, slides 3.5 mm on the hub
    fork           ring yoke, pivots on the SG90 shaft (+x) and an M3 screw in the chassis ear (-x)
    chassis        plate the main servo hangs from (its tabs), plus the SG90 seat, the fork ear and the reed holder
    shell          the case: original floor + door tab, PCB ledges, USB opening, flexure side button
    cap            holds the PCB down, takes the original LED diffuser (cover_led.stl)

Coordinates: z = 0 is the door side of the floor, +z away from the door, +y up (towards the door tab / handle).

    pip install manifold3d trimesh
    python lock.py      # exports the STLs and runs every check (fit, motion, assembly, clearances)
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

SERVO_W, SERVO_L = 19.9, 40.9           # MG996R body (+0.2), shaft 10.2 mm from one end
SERVO_SHAFT_FROM_END = 10.2
SERVO_HEIGHT = 36.5                     # output face to back
SERVO_TAB_FROM_FACE = 7.0               # underside of the mounting tabs
SERVO_TAB_T = 2.5
SERVO_TAB_LENGTH = 54.0
SERVO_TAB_HOLE_SPACING = 49.5
SERVO_FACE_GAP = 3.2                    # hub top to servo face: horn + spline boss

SG90_BODY = (22.7, 12.2, 22.5)          # along its shaft, width, length
SG90_SHAFT_FROM_END = 5.9
SG90_TAB_FROM_TOP = 4.3
SG90_TAB_EXTRA = 4.85                   # tab sticks out this far past the body (the lower tab is cut off)
SG90_HOLE_FROM_CENTRE = 13.75

# ---------------------------------------------------------------------------------------------------- clutch
TEETH = 6
TOOTH_ANGLE, SLOT_ANGLE = 26.0, 34.0
TOOTH_HEIGHT = 2.5
CHAMFER = 0.6
TRAVEL = 3.5
OPEN_GAP = 1.0                          # tooth tips above the adapter when open
HUB_AF = 24.0                           # hub hex across flats, the slider rides on it
TOOTH_R = (14.4, 18.0)
SLIDER_R = 18.6
GROOVE_DEPTH = 2.5
GROOVE_WIDTH = 3.0
SLIDER_UPPER = 1.2                      # flange above the groove
PIN_D = 2.6
FORK_T = 3.0
FORK_RING = (19.4, 21.4)
HORN_SLOT = (22.6, 6.8, 2.4)            # straight servo horn cut to 22 mm (inside the hub's flats), sits in the hub top
ADAPTER_FLOOR = 5.0                     # thumb-turn pocket floor (original 7.5), holds the 3.1 mm deep slots
DOG_DISC_R = 19.4
MAGNET_R = 24.2                         # magnet hole in the original adapter

# ---------------------------------------------------------------------------------------------------- case
WALL = 1.8
BORE = PCB_DIAMETER / 2 + 0.3
SHELL_R = BORE + WALL
PLATE_T = 3.0
CAP_T = 1.5
BOSS_ANGLES = (0.0, 110.0, 220.0)       # chassis screw bosses
LEDGE_ANGLES = (45.0, 135.0, 225.0, 315.0)
REED_ANGLE = 90.0                       # reed sensor above the magnet when the thumb-turn is home (+y)
BUTTON_NUB = 0.2                        # how far the button tongue's nub reaches inside the bore (PCB must slide past)
DIFFUSER_TABS = (70.0, 160.0, 290.0)    # the LED diffuser rests on these, clear of the headers

# PCB parts that matter for the case (x, y from the EasyEDA file, mm from the board centre)
USB = (-35.5, -0.3)
BUTTON = (34.4, -0.2)


# ---------------------------------------------------------------------------------------------------- layout
@dataclass
class Layout:
    A: float = 0     # adapter top (dog slots)
    G: float = 0     # fork pivot = groove centre at half travel
    hub_top: float = 0
    F: float = 0     # servo output face
    plate: float = 0  # plate underside
    pcb: float = 0   # PCB underside
    top: float = 0   # shell rim = cap underside


def layout(thumbturn=THUMBTURN_HEIGHT):
    L = Layout()
    L.A = thumbturn + 0.5 + ADAPTER_FLOOR
    # The SG90 hangs 5.9 mm below its shaft and must stay above the adapter's sweep
    L.G = L.A + 0.5 + SG90_SHAFT_FROM_END
    groove_from_tips = L.G - (L.A + OPEN_GAP - TRAVEL / 2)
    slider_h = groove_from_tips + GROOVE_WIDTH / 2 + SLIDER_UPPER
    L.slider_h = slider_h
    L.groove_from_tips = groove_from_tips
    L.hub_top = L.A + OPEN_GAP + slider_h + 0.25
    L.F = L.hub_top + SERVO_FACE_GAP
    L.plate = L.F + SERVO_TAB_FROM_FACE - PLATE_T
    L.pcb = L.F + SERVO_HEIGHT + PCB_BELOW
    L.top = L.pcb + PCB_THICKNESS + PCB_ABOVE
    return L


L = layout()
SG90_SX = 11.3                                  # SG90 shaft side face (x)
FORK_ARM_PLUS = (SG90_SX + 4.5, SG90_SX + 7.0)  # +x arm sits on the SG90 horn
FORK_ARM_MINUS = (-14.3, -11.8)                 # -x arm, pivots on the chassis ear
PIVOT_Y = -(FORK_RING[1] + 0.9 + SG90_BODY[1] / 2)


# ---------------------------------------------------------------------------------------------------- helpers
def cube(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cyl(r, z0, z1, seg=SEG, x=0.0, y=0.0):
    return Manifold.cylinder(z1 - z0, r, circular_segments=seg).translate((x, y, z0))


def cyl_x(r, x0, x1, y, z, seg=48):
    return Manifold.cylinder(x1 - x0, r, circular_segments=seg).rotate((0, 90, 0)).translate((x0, y, z))


def cyl_y(r, y0, y1, x, z, seg=48):
    return Manifold.cylinder(y1 - y0, r, circular_segments=seg).rotate((-90, 0, 0)).translate((x, y0, z))


def hexagon(af, z0, z1):
    r = af / math.sqrt(3)
    pts = [(r * math.cos(math.radians(60 * i + 30)), r * math.sin(math.radians(60 * i + 30))) for i in range(6)]
    return CrossSection([pts]).extrude(z1 - z0).translate((0, 0, z0))


def sector_pieces(width_lo, width_hi, r_in, r_out, z0, z1, centre, pieces=8):
    out = Manifold()
    for k in range(pieces):
        slabs = Manifold()
        for width, z in ((width_lo, z0), (width_hi, z1)):
            a0 = math.radians(centre - width / 2 + width * k / pieces)
            a1 = math.radians(centre - width / 2 + width * (k + 1) / pieces)
            quad = [(r_in * math.cos(a0), r_in * math.sin(a0)), (r_out * math.cos(a0), r_out * math.sin(a0)),
                    (r_out * math.cos(a1), r_out * math.sin(a1)), (r_in * math.cos(a1), r_in * math.sin(a1))]
            slabs += CrossSection([quad]).extrude(0.001).translate((0, 0, z))
        out += Manifold.hull(slabs)
    return out


def sectors(count, width_lo, width_hi, r_in, r_out, z0, z1):
    """Annular sectors, evenly spaced from angle 0; the width can change from z0 to z1 (chamfers)."""
    out = Manifold()
    for i in range(count):
        out += sector_pieces(width_lo, width_hi, r_in, r_out, z0, z1, 360.0 * i / count)
    return out


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


# ---------------------------------------------------------------------------------------------------- bought parts (for checks and renders)
def servo_model():
    sy0, sy1 = -SERVO_SHAFT_FROM_END, SERVO_L - SERVO_SHAFT_FROM_END
    body = cube(-SERVO_W / 2 + 0.1, SERVO_W / 2 - 0.1, sy0 + 0.1, sy1 - 0.1, L.F, L.F + SERVO_HEIGHT)
    mid = (sy0 + sy1) / 2
    tabs = cube(-SERVO_W / 2 + 0.1, SERVO_W / 2 - 0.1, mid - SERVO_TAB_LENGTH / 2, mid + SERVO_TAB_LENGTH / 2,
                L.F + SERVO_TAB_FROM_FACE, L.F + SERVO_TAB_FROM_FACE + SERVO_TAB_T)
    boss = cyl(6.0, L.F - 1.2, L.F + 0.01) + cyl(2.9, L.hub_top - 0.1, L.F)
    horn = cube(-HORN_SLOT[0] / 2 + 0.3, HORN_SLOT[0] / 2 - 0.3, -3.2, 3.2, L.hub_top - HORN_SLOT[2], L.hub_top + 0.2)
    horn += cyl(4.6, L.hub_top - HORN_SLOT[2] - 1.4, L.hub_top + 0.2, 32)
    return body + tabs + boss, horn


def sg90_model():
    bx, by, bz = SG90_BODY
    z0 = L.G - SG90_SHAFT_FROM_END
    body = cube(SG90_SX - bx, SG90_SX, PIVOT_Y - by / 2, PIVOT_Y + by / 2, z0, z0 + bz)
    tab_x = SG90_SX - SG90_TAB_FROM_TOP
    tab = cube(tab_x - 2.5, tab_x, PIVOT_Y - by / 2, PIVOT_Y + by / 2, z0 + bz - 0.01, z0 + bz + SG90_TAB_EXTRA)
    gear = cyl_x(5.8, SG90_SX - 0.01, SG90_SX + 1.0, PIVOT_Y, L.G) + cyl_x(3.4, SG90_SX + 1.0, SG90_SX + 4.5, PIVOT_Y, L.G)
    return body + tab + gear


def sg90_horn(angle=0.0):
    arm = cube(SG90_SX + 3.0, SG90_SX + 4.5, PIVOT_Y - 2.3, PIVOT_Y + 11.0, L.G - 2.3, L.G + 2.3)
    return rotate_about_pivot(arm, angle)


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


# ---------------------------------------------------------------------------------------------------- printed parts
def knob_adapter():
    """Original thumb-turn adapter, floor thinned to ADAPTER_FLOOR, dog disc with 6 chamfered slots on top."""
    original = from_stl(ORIGINAL / "doorknob_servo_adapter.stl")
    # Original: servo side at z = 0, pocket floor at z = 7.5, pocket opens towards +z. Fill the old horn recess,
    # remove the floor down to ADAPTER_FLOOR, flip so the pocket opens towards the door.
    solid = original + (Manifold.hull(original) ^ cube(-100, 100, -100, 100, 0, 7.49))
    trimmed = solid ^ cube(-100, 100, -100, 100, 7.5 - ADAPTER_FLOOR, 100)
    adapter = trimmed.rotate((180, 0, 0)).translate((0, 0, L.A + 7.5 - ADAPTER_FLOOR))
    disc = cyl(DOG_DISC_R, L.A - 4.0, L.A)
    part = adapter + disc
    slot_r = (TOOTH_R[0] - 0.5, TOOTH_R[1] + 0.5)
    part -= sectors(TEETH, SLOT_ANGLE, SLOT_ANGLE, *slot_r, L.A - TOOTH_HEIGHT - CHAMFER, L.A + 1)
    cd = math.degrees(CHAMFER / (sum(TOOTH_R) / 2))
    part -= sectors(TEETH, SLOT_ANGLE, SLOT_ANGLE + 2 * cd, *slot_r, L.A - CHAMFER, L.A + 0.001)
    # Magnet: 5 mm hole from the top at the original position
    part -= cyl(2.6, L.A - 6, L.A + 1, 32, x=MAGNET_R)
    return largest(part)


def hub():
    """Hex prism: the slider slides on its outside, the servo horn sits in its top."""
    z0 = L.A + 0.25
    part = hexagon(HUB_AF, z0, L.hub_top)
    hx, hy, hz = HORN_SLOT
    part -= cube(-hx / 2, hx / 2, -hy / 2, hy / 2, L.hub_top - hz, L.hub_top + 1)
    part -= cyl(4.9, L.hub_top - hz - 1.5, L.hub_top + 1, 48)
    part -= cyl(3.2, z0 - 1, L.hub_top, 32)  # screwdriver access to the horn screw
    for x in (-9.5, -7.0, 7.0, 9.5):          # M2 self-tapping screws from below into the horn holes
        part -= cyl(0.8, z0 - 1, L.hub_top, 16, x=x)
        part -= cyl(1.9, z0 - 1, z0 + 3.0, 24, x=x)
    return part


def slider(closed_fraction=0.0):
    """closed_fraction 0 = open (lifted), 1 = teeth in the slots."""
    tips = L.A + OPEN_GAP - TRAVEL * closed_fraction
    h = L.slider_h
    body = cyl(SLIDER_R, TOOTH_HEIGHT, h)
    g0 = L.groove_from_tips - GROOVE_WIDTH / 2
    body -= ring(SLIDER_R - GROOVE_DEPTH, SLIDER_R + 1, g0, g0 + GROOVE_WIDTH)
    cd = math.degrees(CHAMFER / (sum(TOOTH_R) / 2))
    teeth = sectors(TEETH, TOOTH_ANGLE, TOOTH_ANGLE, *TOOTH_R, CHAMFER, TOOTH_HEIGHT + 0.01)
    teeth += sectors(TEETH, TOOTH_ANGLE - 2 * cd, TOOTH_ANGLE, *TOOTH_R, 0, CHAMFER + 0.001)
    part = body + teeth
    part -= hexagon(HUB_AF + 2 * FIT, -1, h + 1)
    return part.translate((0, 0, tips))


def pin_offset(angle):
    """Pin movement (z) for a fork angle in degrees, positive angle = pins up = clutch open."""
    return -PIVOT_Y * math.sin(math.radians(angle))


def fork_angle(closed_fraction):
    return math.degrees(math.asin((TRAVEL * (0.5 - closed_fraction)) / -PIVOT_Y))


def rotate_about_pivot(part, angle):
    return part.translate((0, -PIVOT_Y, -L.G)).rotate((angle, 0, 0)).translate((0, PIVOT_Y, L.G))


def fork(angle=0.0):
    t = FORK_T / 2
    g = L.G
    part = ring(*FORK_RING, g - t, g + t)
    for x0, x1 in (FORK_ARM_PLUS, FORK_ARM_MINUS):
        xm = (x0 + x1) / 2
        meet = -math.sqrt(max(FORK_RING[0] ** 2 - xm ** 2, 0)) + 1.0
        part += cube(x0, x1, PIVOT_Y, meet, g - t, g + t) - cyl(FORK_RING[0], g - 5, g + 5)
        part += cyl_x(4.2, x0, x1, PIVOT_Y, g)
    for side in (-1, 1):
        x0, x1 = sorted((side * (SLIDER_R - GROOVE_DEPTH + 0.5), side * (FORK_RING[0] + 0.6)))
        part += cyl_x(PIN_D / 2, x0, x1, 0, g, 24)
    # -x: M3 pivot screw; +x: SG90 horn arm pocket + screw
    part -= cyl_x(1.7, FORK_ARM_MINUS[0] - 1, FORK_ARM_MINUS[1] + 1, PIVOT_Y, g)
    part -= cyl_x(3.7, FORK_ARM_PLUS[0] - 1, FORK_ARM_PLUS[0] + 1.6, PIVOT_Y, g)
    part -= cube(FORK_ARM_PLUS[0] - 1, FORK_ARM_PLUS[0] + 1.6, PIVOT_Y, PIVOT_Y + 11.5, g - 2.5, g + 2.5)
    part -= cyl_x(0.8, FORK_ARM_PLUS[0], FORK_ARM_PLUS[1] + 1, PIVOT_Y + 9, g, 16)
    return rotate_about_pivot(part, angle)


def chassis():
    """Plate the servo hangs from, SG90 seat, fork ear, reed holder."""
    z0, z1 = L.plate, L.plate + PLATE_T
    plate = cyl(BORE - 0.3, z0, z1)
    # Notches so the plate passes the PCB ledges on the way in
    for a in LEDGE_ANGLES:
        x, y = polar(BORE, a)
        plate -= cyl(4.5, z0 - 1, z1 + 1, 32, x=x, y=y)
    sy0, sy1 = -SERVO_SHAFT_FROM_END, SERVO_L - SERVO_SHAFT_FROM_END
    plate -= cube(-SERVO_W / 2, SERVO_W / 2, sy0, sy1, z0 - 1, z1 + 1)
    mid = (sy0 + sy1) / 2
    for dy in (-SERVO_TAB_HOLE_SPACING / 2, SERVO_TAB_HOLE_SPACING / 2):
        for dx in (-5, 5):
            plate -= cyl(1.25, z0 - 1, z1 + 1, 16, x=dx, y=mid + dy)
    # Chassis screws into the shell bosses
    for a in BOSS_ANGLES:
        x, y = polar(BORE - 2.0, a)
        plate -= cyl(1.7, z0 - 1, z1 + 1, 24, x=x, y=y)
    # SG90 window and the wall its (upper) tab is screwed to
    bx, by, bz = SG90_BODY
    sg_y0, sg_y1 = PIVOT_Y - by / 2 - 0.25, PIVOT_Y + by / 2 + 0.25
    plate -= cube(SG90_SX - bx - 0.3, SG90_SX + 0.3, sg_y0, sg_y1, z0 - 1, z1 + 1)
    for y in clip_screws_y():
        plate -= cyl(0.8, z0 - 1, z1 + 1, 16, x=CLIP_X[0] - 1.6, y=y)
    # Fork ear (-x), hangs from the plate
    ear_x = (FORK_ARM_MINUS[0] - 0.3 - 2.6, FORK_ARM_MINUS[0] - 0.3)
    ear = cube(*ear_x, PIVOT_Y - 4.5, sg_y1, L.G - 4.5, z0 + 0.01)
    ear -= cyl_x(1.25, ear_x[0] - 1, ear_x[1] + 1, PIVOT_Y, L.G)   # M3 self-tapping, the fork turns on the shank
    # Reed holder (+y): bar across the magnet path, two legs up to the plate
    rx, ry = polar(MAGNET_R, REED_ANGLE)
    reed_z = L.A + 1.0
    bar = cube(-13.5, 13.5, ry - 2.2, ry + 2.2, reed_z, reed_z + 2.8)
    bar -= cyl_x(1.35, -10, 10, ry, reed_z + 1.6, 24)       # reed glass, 2.5 x 14 mm
    bar -= cube(-10, 10, ry - 1.0, ry + 1.0, reed_z + 1.6, reed_z + 3)  # press it in from the top
    legs = cube(-13.5, -11.0, ry - 2.2, ry + 2.2, reed_z, z0 + 0.01) + cube(11.0, 13.5, ry - 2.2, ry + 2.2, reed_z, z0 + 0.01)
    # Wire passages: servo + SG90 + reed cables up to the PCB
    plate -= cube(14.0, 22.0, -26.0, -18.0, z0 - 1, z1 + 1)
    plate -= cube(14.5, 20.0, 18.0, 24.0, z0 - 1, z1 + 1)
    return largest(plate + ear + bar + legs)


CLIP_X = (SG90_SX - SG90_TAB_FROM_TOP - 2.5 - 2.6, SG90_SX - SG90_TAB_FROM_TOP - 2.5)


def clip_screws_y():
    by = SG90_BODY[1]
    return (PIVOT_Y - by / 2 - 0.25 - 1.9, PIVOT_Y + by / 2 + 0.25 + 2.3)


def sg90_clip():
    """Bridge over the SG90 window, the SG90's upper tab is screwed to it; two M2 screws hold it on the plate."""
    bx, by, bz = SG90_BODY
    z1 = L.plate + PLATE_T
    sg_y0, sg_y1 = PIVOT_Y - by / 2 - 0.25, PIVOT_Y + by / 2 + 0.25
    body_top = L.G - SG90_SHAFT_FROM_END + bz
    hole_z = L.G - SG90_SHAFT_FROM_END + bz / 2 + SG90_HOLE_FROM_CENTRE
    x0, x1 = CLIP_X
    ya, yb = clip_screws_y()
    part = cube(x0, x1, ya - 1.6, yb + 1.6, body_top + 0.3, hole_z + 3.0)
    for y in (ya, yb):  # feet with a screw hole each
        part += cube(x0 - 3.2, x1, y - 1.6, y + 1.6, z1, body_top + 0.31)
        part -= cyl(1.05, z1 - 1, hole_z + 4, 16, x=x0 - 1.6, y=y)
    part -= cyl_x(0.8, x0 - 1, x1 + 0.1, PIVOT_Y, hole_z, 16)
    return part


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
        # 45 deg underside, prints without support
        cone = Manifold.cylinder(3.6, 0.01, 3.6, circular_segments=32).translate((x, y, L.plate - 8.6))
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
    # Clear the USB socket and the side button
    for (x, y), half in ((USB, 17), (BUTTON, 14)):
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
def assembly(closed_fraction=0.0, adapter_rot=0.0, hub_rot=0.0):
    angle = fork_angle(closed_fraction)
    servo, horn = servo_model()
    return {
        # name: (part, colour, printed)
        "shell": (shell(), "case", True),
        "knob_adapter": (knob_adapter().rotate((0, 0, adapter_rot)), "adapter", True),
        "hub": (hub().rotate((0, 0, hub_rot)), "hub", True),
        "slider": (slider(closed_fraction).rotate((0, 0, hub_rot)), "slider", True),
        "fork": (fork(angle), "fork", True),
        "chassis": (chassis(), "bracket", True),
        "sg90_clip": (sg90_clip(), "bracket", True),
        "cap": (cap(), "case", True),
        "servo": (servo, "servo", False),
        "horn": (horn.rotate((0, 0, hub_rot)), "metal", False),
        "sg90": (sg90_model(), "sg90", False),
        "sg90_horn": (sg90_horn(angle), "metal", False),
        "pcb": (pcb_model(), (0.1, 0.45, 0.25), False),
        "thumb_turn": (thumb_turn().rotate((0, 0, adapter_rot)), "metal", False),
    }


PRINT_ROTATION = {
    "shell": (0, 0, 0),           # floor on the plate
    "knob_adapter": (180, 0, 0),  # slotted top on the plate
    "hub": (180, 0, 0),
    "slider": (180, 0, 0),        # upper flange on the plate
    "fork": (0, 0, 0),
    "chassis": (180, 0, 0),       # plate on the bed
    "sg90_clip": (0, 90, 0),      # on its side
    "cap": (180, 0, 0),           # outside face on the plate
}


def export():
    parts = {"shell": shell(), "knob_adapter": knob_adapter(), "hub": hub(), "slider": slider(0),
             "fork": fork(0), "chassis": chassis(), "sg90_clip": sg90_clip(), "cap": cap()}
    for name, part in parts.items():
        p = part.rotate(PRINT_ROTATION[name])
        p = p.translate((0, 0, -p.bounding_box()[2]))
        assert p.status().name == "NoError" and len(p.decompose()) == 1, name
        mesh = to_trimesh(p)
        mesh.export(HERE / f"{name}.stl")
        print(f"  {name + '.stl':20s} {np.round(mesh.extents, 1)} mm  {mesh.volume / 1000:5.1f} cm3")


if __name__ == "__main__":
    print(f"Layout for a {THUMBTURN_HEIGHT} mm thumb-turn: adapter top {L.A:.1f}, fork pivot {L.G:.1f}, servo face {L.F:.1f}, "
          f"PCB {L.pcb:.1f}, cap {L.top + CAP_T:.1f} mm")
    print(f"Envelope: {2 * SHELL_R:.1f} mm diameter x {L.top + CAP_T:.1f} mm from the door\n")
    export()
    import checks
    checks.run()
