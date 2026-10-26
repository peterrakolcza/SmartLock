"""Servo clutch: lets the key and the thumb-turn spin freely when the motor is idle.

The main (continuous rotation) servo no longer drives the thumb-turn directly. Between them sits an axial dog
clutch, shifted by a small SG90 servo:

    main servo -> horn -> clutch_hub (hex shaft) -> clutch_slider (slides on the hex, 6 dog teeth)
                                                         | engaged only while the lock is moving
                                                         v
    thumb-turn <- knob_adapter_clutch (the original adapter + a slotted dog flange)

    clutch_fork: ring yoke around the slider, two pins ride in the slider's groove. It pivots on the SG90 shaft
                 (one side) and an M3 screw (other side), rotating a few degrees moves the slider ~3.5 mm.
    clutch_bracket: band that slips over the main servo body (standard 40 x 20 mm servo), holds the SG90 and the
                 fork pivot, so the clutch is positioned relative to the servo and not to the case.

When the clutch is open, the thumb-turn only drags the adapter, so you can turn it any number of times in either
direction without fighting the servo gearbox.

Assembly coordinates: z axis = lock axis, +z points from the door towards the servo, z = 0 is the fork pivot,
which is also the middle of the slider groove at half travel. The bracket goes on the side of the servo where the
output shaft is closest to the end of the body (+y here).

Regenerate the STLs after changing a parameter:
  pip install manifold3d trimesh
  python clutch.py            # writes the STLs + checks for collisions over the full motion range
"""

import math
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold, Mesh

HERE = Path(__file__).parent
ORIGINAL_ADAPTER = HERE.parent / "doorknob_servo_adapter.stl"

SEGMENTS = 96
FIT = 0.3  # clearance between sliding / rotating parts

# Dog clutch
TEETH = 6
TOOTH_ANGLE = 26.0        # slider tooth width (deg)
SLOT_ANGLE = 34.0         # adapter slot width (deg), the difference is backlash that makes engaging easy
TOOTH_HEIGHT = 2.5
TOOTH_R_IN = 8.8
TOOTH_R_OUT = 14.0
TRAVEL = 3.5              # slider stroke, tooth height + 1 mm clearance when open

# Hub: hex shaft from the servo horn
HEX_AF = 14.0             # across flats
HUB_RADIUS = 15.0         # cut a longer servo horn down to 30 mm, so the hub and horn sweep stays small
HUB_DISC = 4.0
HORN_SLOT_WIDTH = 6.6     # pocket for a straight (double arm) servo horn
HORN_SLOT_DEPTH = 2.4
HORN_HUB_DIAMETER = 9.5   # the horn's round centre that sits on the spline
PILOT_DIAMETER = 6.0

# Slider
SLIDER_RADIUS = 14.0
GROOVE_RADIUS = 11.0
GROOVE_HEIGHT = 3.5
SLIDER_HEIGHT = 10.0      # teeth 2.5 + lower flange 2 + groove 3.5 + upper flange 2

# Adapter flange
FLANGE_RADIUS = 18.0
FLANGE_HEIGHT = 5.5

# Fork
FORK_PIVOT_Y = 29.4       # pivot axis (parallel to x) distance from the lock axis = SG90 shaft position
FORK_ARM_X = (15.8, 18.3) # arm |x| range, the +x arm is screwed onto the SG90 horn
FORK_THICKNESS = 3.0
FORK_PIN_DIAMETER = 2.8

# SG90 micro servo
SG90_BODY = (22.7, 12.2, 22.5)   # along x (shaft axis), y, z
SG90_SHAFT_FROM_END = 5.9        # shaft centre from the end of the 22.5 mm side
SG90_TAB_LENGTH = 32.2
SG90_TAB_HOLE_SPACING = 27.5
SG90_TAB_FROM_TOP = 4.6          # tab top surface below the shaft side face
SG90_SHAFT_X = 11.3              # shaft side face of the SG90 body

# Main servo (MG996R / standard size)
SERVO_BODY = (19.9, 40.9)        # x, y with a little clearance
SERVO_SHAFT_FROM_END = 10.2      # shaft centre from the near end of the body
SERVO_FACE_Z = 13.0              # servo output face, hub top + horn
BAND_HEIGHT = 6.0
BAND_WALL = 2.4
ORIGINAL_FACE_GAP = 2.0          # servo face to adapter base in the original build (horn recessed into the adapter)
BORE_RADIUS = 39.5               # inside of the case (80 mm) minus a little

OUT = HERE


# ------------------------------------------------------------------------------------------------- helpers

def cube(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def cylinder(radius, z0, z1, segments=SEGMENTS):
    return Manifold.cylinder(z1 - z0, radius, circular_segments=segments).translate((0, 0, z0))


def cylinder_x(radius, x0, x1, y, z, segments=48):
    return Manifold.cylinder(x1 - x0, radius, circular_segments=segments).rotate((0, 90, 0)).translate((x0, y, z))


def hexagon(across_flats, z0, z1):
    radius = across_flats / math.sqrt(3)
    points = [(radius * math.cos(math.radians(60 * i)), radius * math.sin(math.radians(60 * i))) for i in range(6)]
    return CrossSection([points]).extrude(z1 - z0).translate((0, 0, z0))


def sectors(count, width_deg, r_in, r_out, z0, z1):
    """`count` annular sectors, evenly spaced, centred on angle 0."""
    steps = 12
    result = Manifold()
    for i in range(count):
        centre = 360.0 * i / count
        angles = [math.radians(centre - width_deg / 2 + width_deg * k / steps) for k in range(steps + 1)]
        outer = [(r_out * math.cos(a), r_out * math.sin(a)) for a in angles]
        inner = [(r_in * math.cos(a), r_in * math.sin(a)) for a in reversed(angles)]
        result += CrossSection([outer + inner]).extrude(z1 - z0).translate((0, 0, z0))
    return result


def from_stl(path):
    mesh = trimesh.load(path)
    return Manifold(Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                         tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))


def to_trimesh(part):
    mesh = part.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts))


def save(part, name, print_rotation=(0, 0, 0)):
    """Export lying on the build plate in its print orientation."""
    printable = part.rotate(print_rotation)
    low = printable.bounding_box()[2]
    printable = printable.translate((0, 0, -low))
    mesh = to_trimesh(printable)
    assert printable.status().name == "NoError" and len(printable.decompose()) == 1, name
    mesh.export(OUT / name)
    print(f"{name:28s} {np.round(mesh.extents, 1)} mm  {mesh.volume / 1000:5.1f} cm3")


# ------------------------------------------------------------------------------------------------- z layout

GROOVE_CENTER_IN_SLIDER = TOOTH_HEIGHT + 2.0 + GROOVE_HEIGHT / 2
SLIDER_OPEN_Z = -GROOVE_CENTER_IN_SLIDER + TRAVEL / 2      # slider bottom (tooth tips) when the clutch is open
SLIDER_CLOSED_Z = SLIDER_OPEN_Z - TRAVEL                    # ... and when engaged
FLANGE_TOP = SLIDER_CLOSED_Z + TOOTH_HEIGHT - 0.3           # teeth bottom out 0.3 mm above the slot floor
FLANGE_BOTTOM = FLANGE_TOP - FLANGE_HEIGHT
HEX_BOTTOM = FLANGE_TOP + 0.3
HEX_TOP = SLIDER_OPEN_Z + SLIDER_HEIGHT + 0.3
HUB_TOP = HEX_TOP + HUB_DISC


# ------------------------------------------------------------------------------------------------- parts

def knob_adapter():
    """The original thumb-turn adapter, horn pocket filled, with a slotted dog flange on the servo side."""
    original = from_stl(ORIGINAL_ADAPTER)
    # In the original file the servo side is at z = 0 and the thumb-turn pocket opens towards +z
    floor_top = 7.5
    filled = original + (Manifold.hull(original) ^ cube(-100, 100, -100, 100, 0, floor_top - 0.01))
    adapter = filled.rotate((180, 0, 0)).translate((0, 0, FLANGE_BOTTOM))

    flange = cylinder(FLANGE_RADIUS, FLANGE_BOTTOM - 0.01, FLANGE_TOP)
    flange -= sectors(TEETH, SLOT_ANGLE, TOOTH_R_IN - 0.6, TOOTH_R_OUT + 0.6, FLANGE_TOP - TOOTH_HEIGHT, FLANGE_TOP + 1)
    flange -= cylinder(PILOT_DIAMETER / 2 + FIT, FLANGE_BOTTOM - 4, FLANGE_TOP + 1, 48)
    # The original STL contains a few loose slivers inside its pockets, keep the main body only
    return max((adapter + flange).decompose(), key=lambda piece: piece.volume())


def hub():
    disc = cylinder(HUB_RADIUS, HEX_TOP, HUB_TOP)
    shaft = hexagon(HEX_AF, HEX_BOTTOM, HEX_TOP + 0.01)
    pilot = cylinder(PILOT_DIAMETER / 2, FLANGE_TOP - FLANGE_HEIGHT + 1.5, HEX_BOTTOM + 0.01, 48)
    part = disc + shaft + pilot
    part -= cube(-HUB_RADIUS - 1, HUB_RADIUS + 1, -HORN_SLOT_WIDTH / 2, HORN_SLOT_WIDTH / 2, HUB_TOP - HORN_SLOT_DEPTH, HUB_TOP + 1)
    part -= cylinder(HORN_HUB_DIAMETER / 2, HUB_TOP - HORN_SLOT_DEPTH - 1.5, HUB_TOP + 1, 48)
    # Pilot holes for M2 self-tapping screws through the horn, drill out to match your horn if needed
    for x in (-11.0, -7.5, 7.5, 11.0):
        part -= cylinder(0.8, HEX_TOP - 1, HUB_TOP + 1, 16).translate((x, 0, 0))
    return part


def slider(z_bottom):
    hex_radius = (HEX_AF + 2 * FIT) / math.sqrt(3)
    body = cylinder(SLIDER_RADIUS, TOOTH_HEIGHT, SLIDER_HEIGHT)
    groove_low = TOOTH_HEIGHT + 2.0
    body -= cylinder(SLIDER_RADIUS + 1, groove_low, groove_low + GROOVE_HEIGHT) - cylinder(GROOVE_RADIUS, groove_low - 1, groove_low + GROOVE_HEIGHT + 1)
    teeth = sectors(TEETH, TOOTH_ANGLE, TOOTH_R_IN, TOOTH_R_OUT, 0, TOOTH_HEIGHT + 0.01)
    part = body + teeth
    part -= hexagon(HEX_AF + 2 * FIT, -1, SLIDER_HEIGHT + 1)
    assert hex_radius < TOOTH_R_IN
    return part.translate((0, 0, z_bottom))


def pin_offset(angle):
    """Vertical movement of the fork pins for a fork angle (deg), positive angle = pins down = clutch closed."""
    return -FORK_PIVOT_Y * math.sin(math.radians(angle))


def fork(angle=0.0):
    """Ring yoke + arms, rotates about the x axis line y = FORK_PIVOT_Y, z = 0."""
    t = FORK_THICKNESS / 2
    ring_in = SLIDER_RADIUS + 0.8
    ring = cylinder(FORK_ARM_X[1], -t, t) - cylinder(ring_in, -t - 1, t + 1)
    part = ring
    for side in (-1, 1):
        x0, x1 = sorted((side * FORK_ARM_X[0], side * FORK_ARM_X[1]))
        part += cube(x0, x1, 0, FORK_PIVOT_Y, -t, t)
        part += cylinder_x(4.0, x0, x1, FORK_PIVOT_Y, 0)
        # Pins riding in the slider groove
        pin_x0, pin_x1 = sorted((side * (GROOVE_RADIUS + 0.6), side * (ring_in + 0.5)))
        part += cylinder_x(FORK_PIN_DIAMETER / 2, pin_x0, pin_x1, 0, 0, 24)
    # -x: M3 screw pivot, +x: SG90 horn hub recess + the horn arm pocket along the fork arm
    part -= cylinder_x(1.7, -FORK_ARM_X[1] - 1, -FORK_ARM_X[0] + 1, FORK_PIVOT_Y, 0)
    part -= cylinder_x(3.8, FORK_ARM_X[0] - 1, FORK_ARM_X[0] + 1.2, FORK_PIVOT_Y, 0)
    part -= cube(FORK_ARM_X[0] - 1, FORK_ARM_X[0] + 1.2, FORK_PIVOT_Y - 16, FORK_PIVOT_Y, -2.4, 2.4)
    part -= cylinder_x(1.0, FORK_ARM_X[0], FORK_ARM_X[1] + 1, FORK_PIVOT_Y, 0, 16)  # horn screw
    return part.translate((0, -FORK_PIVOT_Y, 0)).rotate((angle, 0, 0)).translate((0, FORK_PIVOT_Y, 0))


def sg90_box():
    """SG90 envelope incl. tabs, shaft on the pivot axis pointing +x."""
    bx, by, bz = SG90_BODY
    z0 = -SG90_SHAFT_FROM_END
    y0 = FORK_PIVOT_Y - by / 2
    body = cube(SG90_SHAFT_X - bx, SG90_SHAFT_X, y0, y0 + by, z0, z0 + bz)
    tab_x = SG90_SHAFT_X - SG90_TAB_FROM_TOP
    centre_z = z0 + bz / 2
    tabs = cube(tab_x - 2.5, tab_x, y0, y0 + by, centre_z - SG90_TAB_LENGTH / 2, centre_z + SG90_TAB_LENGTH / 2)
    gear = cylinder_x(5.9, SG90_SHAFT_X - 0.1, SG90_SHAFT_X + 4.0, FORK_PIVOT_Y, 0)
    return body + tabs + gear


def bracket():
    """Band around the main servo body + SG90 cradle + pivot ear for the fork's -x arm."""
    sx, sy = SERVO_BODY
    near_end = SERVO_SHAFT_FROM_END + 0.15
    servo_y0, servo_y1 = -(sy - near_end), near_end
    band_z0, band_z1 = SERVO_FACE_Z, SERVO_FACE_Z + BAND_HEIGHT
    w = BAND_WALL
    band = cube(-sx / 2 - w, sx / 2 + w, servo_y0 - w, servo_y1 + w, band_z0, band_z1)
    band -= cube(-sx / 2, sx / 2, servo_y0, servo_y1, band_z0 - 1, band_z1 + 1)

    bx, by, bz = SG90_BODY
    sg_y0 = FORK_PIVOT_Y - by / 2 - FIT
    sg_y1 = FORK_PIVOT_Y + by / 2 + FIT
    sg_z0 = -SG90_SHAFT_FROM_END
    sg_z1 = sg_z0 + bz
    tab_x = SG90_SHAFT_X - SG90_TAB_FROM_TOP
    centre_z = (sg_z0 + sg_z1) / 2

    # Bridge from the band over the horn to the cradle; the cradle grips the SG90 between the tab plate and the end
    bridge = cube(-sx / 2 - w, sx / 2 + w, servo_y1, sg_y1 + w, band_z0, band_z1)
    tab_plate = cube(tab_x, tab_x + 3.0, sg_y0 - 0.01, sg_y1 + w, sg_z1 - 1.0, centre_z + SG90_TAB_LENGTH / 2 + 1.0)
    back = cube(SG90_SHAFT_X - bx - 2.5, tab_x + 3.0, sg_y1, sg_y1 + w, sg_z1 - 6.0, band_z1)
    end_stop = cube(SG90_SHAFT_X - bx - 2.5, SG90_SHAFT_X - bx, sg_y0 + 2.0, sg_y1 + w, sg_z0 + 2.0, band_z1)
    # Pivot ear on -x, tied to the end stop
    ear_x0, ear_x1 = -FORK_ARM_X[1] - FIT - 3.0, -FORK_ARM_X[1] - FIT
    ear = cube(ear_x0, ear_x1, FORK_PIVOT_Y - 5.0, sg_y1 + w, -5.0, band_z1)
    ear += cube(ear_x0, SG90_SHAFT_X - bx, sg_y1 - 2.0, sg_y1 + w, -5.0, band_z1)
    part = band + bridge + tab_plate + back + end_stop + ear
    part -= sg90_box()
    part -= cylinder_x(1.25, ear_x0 - 1, ear_x1 + 1, FORK_PIVOT_Y, 0)               # M3 self-tapping pivot screw
    part -= cylinder_x(0.9, tab_x - 1, tab_x + 4, FORK_PIVOT_Y, centre_z + SG90_TAB_HOLE_SPACING / 2, 16)
    return part ^ cylinder(BORE_RADIUS, -100, 100)


def extension_ring(height):
    """Spacer between the bottom and middle parts, lifts the servo by the extra clutch height."""
    outer, inner = 43.5, 40.0
    spigot = 8.0
    spigot_in = inner - FIT - 1.6
    ring = cylinder(outer, 0, height) - cylinder(inner, -1, height + 1)
    ring += cylinder(inner - FIT, -spigot, 0) + cylinder(outer, 0, 2.0)
    ring -= cylinder(spigot_in, -spigot - 1, 3)
    return ring


# ------------------------------------------------------------------------------------------------- checks

def check_collisions():
    """Static parts vs moving parts over the full fork / slider / thumb-turn range."""
    adapter = knob_adapter()
    hub_part = hub()
    bracket_part = bracket()
    servo_horn_sweep = cylinder(HUB_RADIUS, HUB_TOP, SERVO_FACE_Z)
    problems = []

    def overlap(a, b):
        return (a ^ b).volume()

    max_angle = math.degrees(math.atan((TRAVEL / 2 + 0.2) / FORK_PIVOT_Y))
    for angle in (-max_angle, 0.0, max_angle):
        f = fork(angle)
        s = slider(-GROOVE_CENTER_IN_SLIDER + pin_offset(angle))
        for name, other in (("bracket", bracket_part), ("hub", hub_part), ("adapter", adapter), ("slider", s), ("horn", servo_horn_sweep)):
            v = overlap(f, other)
            if v > 0.5:
                problems.append(f"fork @ {angle:+.1f} deg overlaps {name}: {v:.1f} mm3")
    for z in (SLIDER_OPEN_Z, SLIDER_CLOSED_Z):
        s = slider(z)
        for name, other in (("hub", hub_part), ("adapter", adapter), ("bracket", bracket_part)):
            v = overlap(s, other)
            # Engaged teeth sit inside the flange slots, the hex sits inside the slider bore
            if v > 0.5:
                problems.append(f"slider @ z {z:+.1f} overlaps {name}: {v:.1f} mm3")
    for rot in range(0, 360, 15):
        a = adapter.rotate((0, 0, rot))
        for name, other in (("bracket", bracket_part),):
            v = overlap(a, other)
            if v > 0.5:
                problems.append(f"thumb-turn adapter @ {rot} deg overlaps {name}: {v:.1f} mm3")
    for name, part in (("bracket", bracket_part), ("hub", hub_part)):
        outside = overlap(part, Manifold.cube((200, 200, 200), center=True) - cylinder(BORE_RADIUS + 0.01, -100, 100))
        if outside > 0.5:
            problems.append(f"{name} sticks out of the 80 mm bore: {outside:.1f} mm3")
    return problems


def assembly(angle=0.0):
    return {
        "knob_adapter_clutch": knob_adapter(),
        "clutch_hub": hub(),
        "clutch_slider": slider(-GROOVE_CENTER_IN_SLIDER + pin_offset(angle)),
        "clutch_fork": fork(angle),
        "clutch_bracket": bracket(),
    }


if __name__ == "__main__":
    extra_height = SERVO_FACE_Z - FLANGE_BOTTOM - ORIGINAL_FACE_GAP
    print(f"stack: adapter base at z {FLANGE_BOTTOM:.1f}, hub top at z {HUB_TOP:.1f}, servo face at z {SERVO_FACE_Z:.1f}")
    print(f"the servo sits {extra_height:.1f} mm further from the thumb-turn than before -> extension ring height\n")
    save(knob_adapter(), "knob_adapter_clutch.stl", (180, 0, 0))   # flange on the plate
    save(hub(), "clutch_hub.stl", (180, 0, 0))                     # disc on the plate
    save(slider(0), "clutch_slider.stl", (180, 0, 0))              # upper flange on the plate
    save(fork(), "clutch_fork.stl")
    save(bracket(), "clutch_bracket.stl", (180, 0, 0))
    save(extension_ring(round(extra_height)), "extension_ring.stl")
    problems = check_collisions()
    print("\ncollision check:", "OK" if not problems else "")
    for p in problems:
        print("  " + p)
