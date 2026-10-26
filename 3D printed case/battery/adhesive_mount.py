"""Self-adhesive mounting for renters: no screws in the door, no tab on the handle screw.

adhesive_mount.stl  a flat plate stuck to the door with 3M VHB tape around the lock cylinder. A collar grips the
                    lock's bottom part with 3 small screws. The back has a channel so the plate straddles a long
                    handle escutcheon (set ESCUTCHEON_WIDTH = 0 for doors with a separate round rosette).
battery_box.stl     holds a standard 4 x AA flat battery holder (with leads), also stuck on with VHB,
battery_lid.stl     next to or below the lock. The lid is a press fit.

Holding torque: ~40 cm2 of VHB (after the escutcheon channel) at a conservative 0.1 MPa in shear holds ~400 N at a
~50 mm radius, about 20 N m, roughly 20x what the servo (~1 N m) can push. Clean the door with isopropyl alcohol, press hard for 30 s and let it cure for 24 h before use.

  pip install manifold3d trimesh
  python adhesive_mount.py
"""

import math
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold

OUT = Path(__file__).parent
SEGMENTS = 128

# Lock body (bottom part of the case)
LOCK_DIAMETER = 87.0
LOCK_FIT = 0.4
TAB_WIDTH = 22.0           # notch for the original mounting tab, cut the tab off if you don't need it

# Plate
PLATE_DIAMETER = 118.0
PLATE_THICKNESS = 12.0     # must be thicker than the escutcheon so the back sits flat on the door
COLLAR_HEIGHT = 14.0       # above the plate
COLLAR_WALL = 3.0
ESCUTCHEON_WIDTH = 30.0    # 0 = no channel
ESCUTCHEON_DEPTH = 9.5
SCREW_DIAMETER = 2.6       # M3 self-tapping screws into the lock body wall
TAPE_RECESS = 0.5          # shallow recess so the tape edge is protected

# Battery box for a 4 x AA flat holder
HOLDER = (63.0, 58.0, 16.0)
BOX_WALL = 2.0
CABLE_HOLE = 4.0


def rounded_rect(length, width, radius):
    radius = min(radius, length / 2 - 0.01, width / 2 - 0.01)
    return CrossSection.square((length - 2 * radius, width - 2 * radius), center=True).offset(radius, JoinType.Round, circular_segments=48)


def cylinder(radius, z0, z1):
    return Manifold.cylinder(z1 - z0, radius, circular_segments=SEGMENTS).translate((0, 0, z0))


def cube(x0, x1, y0, y1, z0, z1):
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def save(part, name):
    low = part.bounding_box()[2]
    part = part.translate((0, 0, -low))
    mesh = part.to_mesh()
    tm = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts))
    assert part.status().name == "NoError" and len(part.decompose()) == 1, name
    tm.export(OUT / name)
    print(f"{name:20s} {np.round(tm.extents, 1)} mm  {tm.volume / 1000:5.1f} cm3")


def adhesive_mount():
    bore = LOCK_DIAMETER / 2 + LOCK_FIT
    plate = cylinder(PLATE_DIAMETER / 2, 0, PLATE_THICKNESS)
    collar = cylinder(bore + COLLAR_WALL, PLATE_THICKNESS - 0.01, PLATE_THICKNESS + COLLAR_HEIGHT)
    part = plate + collar
    part -= cylinder(bore, -1, PLATE_THICKNESS + COLLAR_HEIGHT + 1)

    # Door side (z = 0): channel for the escutcheon, it runs up towards the handle (+y) and down (-y)
    if ESCUTCHEON_WIDTH > 0:
        part -= cube(-ESCUTCHEON_WIDTH / 2, ESCUTCHEON_WIDTH / 2, -PLATE_DIAMETER, PLATE_DIAMETER, -1, ESCUTCHEON_DEPTH)
    part -= cube(-TAB_WIDTH / 2, TAB_WIDTH / 2, 0, PLATE_DIAMETER, -1, PLATE_THICKNESS + 0.01)
    ring = cylinder(PLATE_DIAMETER / 2 - 2, -1, TAPE_RECESS) - cylinder(bore + 2, -2, 1)
    part -= ring

    # 3 radial screws through the collar into the lock body
    for angle in (90 + 60, 270, 30):
        a = math.radians(angle)
        hole = Manifold.cylinder(COLLAR_WALL + 4, SCREW_DIAMETER / 2 + 0.3, circular_segments=24).rotate((0, 90, 0))
        hole = hole.translate((bore - 1, 0, PLATE_THICKNESS + COLLAR_HEIGHT / 2)).rotate((0, 0, angle))
        part -= hole
    return part


def battery_box():
    hx, hy, hz = HOLDER
    w = BOX_WALL
    box = rounded_rect(hx + 2 * w + 1, hy + 2 * w + 1, 4).extrude(hz + w + 0.5)
    box -= rounded_rect(hx + 1, hy + 1, 2).extrude(hz + 10).translate((0, 0, w))
    # Cable exit in the top wall, towards the lock
    box -= Manifold.cylinder(w * 4, CABLE_HOLE / 2, circular_segments=24).rotate((-90, 0, 0)).translate((hx / 2 - 8, hy / 2 - w, w + hz / 2))
    box -= cube(hx / 2 - 8 - CABLE_HOLE / 2, hx / 2 - 8 + CABLE_HOLE / 2, hy / 2 - w, hy / 2 + 2 * w, w + hz / 2, hz + w + 1)
    box -= rounded_rect(hx - 10, hy - 10, 3).extrude(TAPE_RECESS + 0.01).translate((0, 0, -0.01))
    return box


def battery_lid():
    hx, hy, _ = HOLDER
    w = BOX_WALL
    lid = rounded_rect(hx + 2 * w + 1, hy + 2 * w + 1, 4).extrude(1.6)
    lip = rounded_rect(hx + 0.6, hy + 0.6, 2).extrude(3.0) - rounded_rect(hx - 2.4, hy - 2.4, 1).extrude(4).translate((0, 0, -0.5))
    return lid + lip.translate((0, 0, 1.59))


if __name__ == "__main__":
    save(adhesive_mount(), "adhesive_mount.stl")
    save(battery_box(), "battery_box.stl")
    save(battery_lid(), "battery_lid.stl")
