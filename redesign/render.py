"""Images for the redesign proposal: cutaway, exploded, size next to the other versions.

    pip install manifold3d trimesh vtk pillow
    python redesign/render.py
"""

import sys
from pathlib import Path

from manifold3d import Manifold
from PIL import ImageDraw

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "docs" / "renders"))

import concept as c  # noqa: E402
from render_lib import Scene, callouts, caption, font  # noqa: E402

s = c.s
IMAGES = ROOT / "images"
HALF = Manifold.cube((400, 400, 400)).translate((-200, -400, -100))
CUT = {"case", "cap", "chassis", "battery_holder", "pcb"}


def door():
    return Manifold.cube((180, 220, 3)).translate((-90, -110, -12))


def render(scene, parts, cut=()):
    scene.clear()
    scene.add(door(), "door", specular=0.05)
    for name, (part, color) in parts.items():
        if name in cut:
            part = part - HALF
            if part.is_empty():
                continue
        scene.add(part, color, specular=0.3)


def cutaway():
    scene = Scene(1400, 1000)
    render(scene, c.assembly(), cut=CUT)
    scene.camera(position=(-180, -230, 100), focal=(0, 0, 38), angle=29)
    img = scene.image()
    Z = c.Z
    callouts(img, scene, [
        ("4 x AAA", (-15, -6, Z.battery1 - 2)),
        ("PCB: ESP32-C6 (Matter / Thread), motor driver", (-30, 0, Z.pcb1)),
        ("AS5600 encoder over the hub axis", (0, 0, Z.pcb0 - 1.0)),
        ("chassis plate", (-30, 0, Z.plate0 + 1)),
        ("N20 gearmotor, lying flat", (20, c.CENTRE - 5, c.WHEEL_MID)),
        ("brass worm + POM wheel, 40:1", (-4, c.CENTRE - 3, c.WHEEL_MID)),
        ("spiral hub (key turns freely)", (-s.HUB_R * 0.7, -s.HUB_R * 0.7, s.L.hub0 + 2)),
        ("thumb-turn adapter + follower", (-14, -9, s.L.A - 9)),
        ("case with the original door tab", (-c.CASE_R, 0, 20)),
    ], margin=260)
    caption(img, "v5 concept, cut open", f"{2 * c.CASE_R:.0f} mm x {c.Z.top + c.CAP_T:.0f} mm with batteries, one motor, key turns freely").save(IMAGES / "v5_cutaway.png")


def exploded():
    scene = Scene(1400, 1000)
    offsets = {"thumb_turn": -14, "adapter": -4, "follower": 4, "pin": 4, "hub": 14, "worm": 26, "motor": 26,
               "chassis": 38, "knob_sensor": 38, "pcb": 52, "battery_holder": 64, "batteries": 66, "cap": 80, "case": 0}
    parts = {n: (p.translate((0, 0, offsets.get(n, 0))), col) for n, (p, col) in c.assembly().items()}
    render(scene, parts, cut={"case"})
    scene.camera(position=(-240, -310, 175), focal=(0, 0, 62), angle=36)
    caption(scene.image(), "v5 concept, exploded", "case · adapter + follower · spiral hub + worm wheel · worm + motor · chassis · PCB · batteries · cap").save(IMAGES / "v5_exploded.png")


def size():
    scene = Scene(1700, 820)
    bottom = s.from_stl(s.ORIGINAL / "bottom.stl")
    middle = s.from_stl(s.ORIGINAL / "middle.stl").rotate((180, 0, 0))
    cover = s.diffuser()
    original = bottom + middle.translate((0, 0, 73)) + cover.translate((0, 0, 71.8))
    spiral = s.shell() + s.cap()
    v5 = c.case() + c.cap()
    spots = [("original (USB, key blocked)", -190, original, "case", 87, 73),
             ("single servo + spiral (USB)", 0, spiral, "hub", 2 * s.SHELL_R, s.L.top + s.CAP_T),
             ("v5 concept (batteries)", 190, v5, (0.3, 0.65, 0.45), 2 * c.CASE_R, c.Z.top + c.CAP_T)]
    scene.clear()
    scene.add(Manifold.cube((600, 240, 3)).translate((-300, -60, -3)), "door", specular=0.05)
    for _, x, part, color, _, _ in spots:
        scene.add(part.translate((x, 0, 0)), color, specular=0.3)
    scene.camera(position=(0, -620, 220), focal=(0, 0, 30), angle=30)
    img = scene.image()
    draw = ImageDraw.Draw(img, "RGBA")
    for name, x, _, _, w, h in spots:
        px, py = scene.project((x, -60, 0))
        draw.text((px, py + 30), name, font=font(26), fill=(25, 28, 36), anchor="mm")
        draw.text((px, py + 62), f"{w:.0f} x {h:.0f} mm", font=font(22), fill=(80, 86, 98), anchor="mm")
    caption(img, "Size", "the v5 concept is smaller than the original and carries its own batteries").save(IMAGES / "v5_size.png")


if __name__ == "__main__":
    cutaway()
    exploded()
    size()
    print("done")
