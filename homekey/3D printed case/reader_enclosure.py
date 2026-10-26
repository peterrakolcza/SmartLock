"""Compact enclosure for the HomeKey reader: ESP32 DevKitC + PN532 (red V3 board).

Two parts, both print without supports:
  reader_base.stl   wall side, holds the ESP32 on two slotted rails, USB cable exits at the bottom
  reader_cover.stl  front, 1.2 mm face so the PN532 antenna reads through it, PN532 drops into a pocket

Regenerate the STLs after changing a parameter:
  pip install manifold3d trimesh
  python reader_enclosure.py
"""

from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold

# Boards (mm)
ESP32_LENGTH = 55.0
ESP32_WIDTH = 28.2
ESP32_PCB = 1.6
ESP32_LEDGE = 5.0        # the DevKit lies face down (pins up) on two ledges, clear of the ESP32 module
PN532_LENGTH = 43.0
PN532_WIDTH = 41.0
PN532_THICKNESS = 1.6

# Enclosure (mm)
WALL = 2.6
FLOOR = 2.4
FACE = 1.2               # NFC reads through ~1.2 mm of PLA/PETG reliably
INNER_LENGTH = 62.0
INNER_WIDTH = 48.0
BASE_HEIGHT = 26.0       # floor to rim
COVER_DEPTH = 8.0        # skirt that slides over the base lip
LIP = 1.4                # base wall step that the cover skirt sits on
FIT = 0.25               # sliding clearance, increase if the cover is too tight
CORNER = 4.0

OUT = Path(__file__).parent


def rounded_rect(length, width, radius):
    radius = min(radius, length / 2 - 0.01, width / 2 - 0.01)
    square = CrossSection.square((length - 2 * radius, width - 2 * radius), center=True)
    return square.offset(radius, JoinType.Round, circular_segments=48)


def box(length, width, height, radius=CORNER):
    return rounded_rect(length, width, radius).extrude(height)


def cube(x, y, z, cx=0.0, cy=0.0, z0=0.0):
    return Manifold.cube((x, y, z), center=True).translate((cx, cy, z0 + z / 2))


def cylinder(radius, height, cx=0.0, cy=0.0, z0=0.0):
    return Manifold.cylinder(height, radius, circular_segments=64).translate((cx, cy, z0))


def save(part, name):
    mesh = part.to_mesh()
    tm = trimesh.Trimesh(vertices=np.asarray(mesh.vert_properties)[:, :3], faces=np.asarray(mesh.tri_verts))
    assert tm.is_watertight, name
    tm.export(OUT / name)
    print(f"{name}: {np.round(tm.extents, 1)} mm, {tm.volume / 1000:.1f} cm3")


def reader_base():
    outer_l = INNER_LENGTH + 2 * WALL
    outer_w = INNER_WIDTH + 2 * WALL
    shell = box(outer_l, outer_w, BASE_HEIGHT)
    shell -= box(INNER_LENGTH, INNER_WIDTH, BASE_HEIGHT, CORNER - WALL).translate((0, 0, FLOOR))

    # Outer step at the rim for the cover skirt
    step = box(outer_l + 1, outer_w + 1, COVER_DEPTH, CORNER + 0.5) - box(outer_l - 2 * LIP, outer_w - 2 * LIP, COVER_DEPTH, CORNER - LIP)
    shell -= step.translate((0, 0, BASE_HEIGHT - COVER_DEPTH))

    # Ledges under the long PCB edges, with a side fence so the board can't slide; fix it with tape or hot glue
    board_x = -INNER_LENGTH / 2 + ESP32_LENGTH / 2 + 1.0
    for side in (-1, 1):
        ledge = cube(ESP32_LENGTH - 8, 2.4, ESP32_LEDGE, cx=board_x, cy=side * (ESP32_WIDTH / 2 - 1.0), z0=FLOOR)
        fence = cube(ESP32_LENGTH - 8, 1.2, ESP32_LEDGE + ESP32_PCB + 1.0, cx=board_x, cy=side * (ESP32_WIDTH / 2 + 0.85), z0=FLOOR)
        shell += ledge + fence

    # USB cable exit in the end wall, the port hangs under the face down board
    shell -= cube(WALL * 3, 12.0, ESP32_LEDGE + 4.0, cx=-(INNER_LENGTH / 2 + WALL / 2), z0=FLOOR)

    # Two keyhole slots for screws, plus a shallow recess for double sided tape
    for x in (-18.0, 18.0):
        shell -= cylinder(4.2, FLOOR + 1, cx=x, z0=-0.5)
        shell -= cube(3.6, 7.0, FLOOR + 1, cx=x, cy=3.5, z0=-0.5)
    shell -= box(INNER_LENGTH - 20, INNER_WIDTH - 22, 0.6, 2).translate((0, 0, -0.01))
    return shell


def reader_cover():
    outer_l = INNER_LENGTH + 2 * WALL
    outer_w = INNER_WIDTH + 2 * WALL
    cover = box(outer_l, outer_w, FACE + COVER_DEPTH)
    inner_l = outer_l - 2 * LIP + 2 * FIT
    inner_w = outer_w - 2 * LIP + 2 * FIT
    cover -= box(inner_l, inner_w, COVER_DEPTH + 1, CORNER - LIP).translate((0, 0, FACE))

    # PN532 pocket, the antenna side lies flat against the face
    pocket_wall = 1.2
    frame = cube(PN532_LENGTH + 2 * pocket_wall, PN532_WIDTH + 2 * pocket_wall, PN532_THICKNESS + 1.0, z0=FACE)
    frame -= cube(PN532_LENGTH + 0.4, PN532_WIDTH + 0.4, PN532_THICKNESS + 2, z0=FACE - 0.5)
    frame -= cube(PN532_LENGTH + 4, 14, PN532_THICKNESS + 2, z0=FACE - 0.5)  # gaps for the header pins and fingers
    cover += frame

    # Tap target on the face: shallow ring, print face down for a clean surface
    ring = cylinder(15.0, 0.5, z0=-0.01) - cylinder(13.6, 0.7, z0=-0.1)
    cover -= ring
    return cover


if __name__ == "__main__":
    save(reader_base(), "reader_base.stl")
    save(reader_cover(), "reader_cover.stl")
