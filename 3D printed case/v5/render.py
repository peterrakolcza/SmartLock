"""Images for the v5 README: cutaway, exploded, the three door presets, size next to the earlier versions.

    pip install manifold3d trimesh vtk pillow
    python render.py
"""

import sys
from pathlib import Path

from manifold3d import Manifold
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "docs" / "renders"))

import lock as k  # noqa: E402
from render_lib import Scene, callouts, caption, font  # noqa: E402

IMAGES = ROOT / "images"
HALF = Manifold.cube((400, 400, 400)).translate((-200, -400, -100))
CUT = {"base", "case", "deck", "cap", "pcb", "pouch", "adapter"}


def door():
    return Manifold.cube((200, 240, 3)).translate((-100, -120, -3))


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
    parts = k.assembly("rosette", h=k.FREE_PLAY - 135 - 720)
    render(scene, parts, cut=CUT)
    L = k.layout(k.DOORS["rosette"])
    scene.camera(position=(-170, -230, 110), focal=(0, 0, 32), angle=29)
    img = scene.image()
    callouts(img, scene, [
        ("cap + light pipe", (-10, 0, L.top)),
        ("1200 mAh Li-ion pouch (USB-C charging)", (-20, -3, L.pouch0 + 3)),
        ("deck", (-30, 0, L.deck0 + 0.6)),
        ("N20 gearmotor + brass worm", (16, k.CENTRE - 5, L.wheel_mid)),
        ("steel worm wheel 40:1, pinned to the hub", (0, -k.WHEEL_OUT_R, L.wheel_mid)),
        ("crescent PCB: ESP32-C6, Matter over Thread", (-25, -5, L.drive0 + 1)),
        ("spiral hub", (-k.HUB_R * 0.7, -k.HUB_R * 0.7, L.hub0 + 2)),
        ("universal adapter: 2 screw jaws", (-20, -14, L.A - 12)),
        ("adhesive base (3M VHB)", (-k.CASE_R + 2, 0, 4)),
    ], margin=270)
    caption(img, "v5: self-adhesive, universal, battery, one motor",
            f"{2 * k.CASE_R:.0f} mm x {L.top:.0f} mm from the door (rosette door)").save(IMAGES / "v5_cutaway.png")


def exploded():
    scene = Scene(1400, 1100)
    parts = k.assembly("rosette", h=135.0)
    offsets = {"base": -10, "thumb_turn": -10, "adapter": 0, "jaws": 0, "knob_magnet": 0, "follower": 8, "pin": 8,
               "hub": 18, "hub_magnet": 18, "shaft": 18, "wheel": 26, "worm": 34, "motor": 34, "pcb": 44,
               "deck": 56, "light_pipe": 66, "pouch": 66, "cap": 80, "case": 30}
    exp = {n: (p.translate((0, 0, offsets.get(n, 0) * 1.4)), c) for n, (p, c) in parts.items()}
    render(scene, exp, cut={"case"})
    scene.camera(position=(-250, -330, 200), focal=(0, 0, 70), angle=37)
    caption(scene.image(), "Exploded", "base · adapter + jaws + follower · spiral hub · wheel · worm + motor · PCB · deck · pouch · cap").save(IMAGES / "v5_exploded.png")


def presets():
    tiles = []
    scene = Scene(700, 620)
    for name, label in (("rosette", "round rosette"), ("escutcheon", "long escutcheon"), ("flat", "flush cylinder")):
        door_ = k.DOORS[name]
        L = k.layout(door_)
        scene.clear()
        scene.add(door(), "door", specular=0.05)
        if door_.rosette_d:
            scene.add(k.cyl(door_.rosette_d / 2 - 1.0, 0, door_.base_h - 0.5), "metal")
        if door_.escutcheon_w:
            scene.add(k.cube(-door_.escutcheon_w / 2, door_.escutcheon_w / 2, -60, 110, 0, door_.base_h - 2.5), "metal")
        scene.add(k.base(L, door_) - HALF, (0.92, 0.92, 0.9))
        scene.add(k.case(L) - HALF, "case")
        scene.add(k.cap(L) - HALF, "case")
        scene.camera(position=(-160, -210, 90), focal=(0, 0, 25), angle=30)
        tiles.append(caption(scene.image(), f"{label}: base {door_.base_h:.1f} mm", f"lock {L.top:.0f} mm from the door"))
    sheet = Image.new("RGB", (2100, 620), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * 700, 0))
    sheet.save(IMAGES / "v5_presets.png")


def size():
    scene = Scene(1700, 820)
    orig = k.from_stl(k.ROOT / "3D printed case" / "bottom.stl")
    middle = k.from_stl(k.ROOT / "3D printed case" / "middle.stl").rotate((180, 0, 0))
    original = orig + middle.translate((0, 0, 73))
    spiral = k.cyl(41.1, 0, 85.4)
    L = k.layout(k.DOORS["rosette"])
    v5 = k.base(L, k.DOORS["rosette"]) + k.case(L) + k.cap(L)
    spots = [("original (USB, key blocked)", -190, original.translate((0, 0, 9)), "case", 87, 73 + 9),
             ("single servo + spiral (USB)", 0, spiral.translate((0, 0, 9)), "hub", 82, 85 + 9),
             ("v5 (battery, self-adhesive)", 190, v5, (0.3, 0.65, 0.45), 2 * k.CASE_R, L.top)]
    scene.clear()
    scene.add(Manifold.cube((600, 240, 3)).translate((-300, -60, -3)), "door", specular=0.05)
    for _, x, part, color, _, _ in spots:
        scene.add(part.translate((x, 0, 0)), color, specular=0.3)
    scene.camera(position=(0, -620, 220), focal=(0, 0, 35), angle=30)
    img = scene.image()
    draw = ImageDraw.Draw(img, "RGBA")
    for name, x, _, _, w, h in spots:
        px, py = scene.project((x, -60, 0))
        draw.text((px, py + 30), name, font=font(26), fill=(25, 28, 36), anchor="mm")
        draw.text((px, py + 62), f"{w:.0f} x {h:.0f} mm from the door", font=font(22), fill=(80, 86, 98), anchor="mm")
    caption(img, "Size (rosette door, 9 mm)", "v5 is the smallest and carries its own battery").save(IMAGES / "v5_size.png")


def versions():
    """Both versions closed, on a door with a rosette: what you see on the door."""
    scene = Scene(1600, 900)
    scene.clear()
    scene.add(Manifold.cube((420, 240, 3)).translate((-210, -120, -3)), (0.55, 0.42, 0.3), specular=0.05)
    door_ = k.DOORS["rosette"]
    for x, power in ((-58, "battery"), (58, "usb")):
        L = k.layout(door_, power)
        place = lambda m: m.rotate((0, 0, -35)).translate((x, 0, 0))  # noqa: E731
        scene.add(place(k.case(L)), (0.92, 0.92, 0.9), specular=0.35)                  # white / light grey PETG
        scene.add(place(k.base(L, door_) + k.cap(L)), (0.2, 0.21, 0.23), specular=0.45)  # anthracite PETG
        scene.add(k.light_pipe(L).rotate((0, 0, -35)).translate((x, 0, 0.05)), (0.55, 0.85, 1.0), specular=0.6)
    scene.camera(position=(0, -330, 260), focal=(0, 0, 28), angle=30)
    img = scene.image()
    draw = ImageDraw.Draw(img, "RGBA")
    for x, power, text in ((-58, "battery", "battery"), (58, "usb", "USB powered")):
        L = k.layout(door_, power)
        px, py = scene.project((x, -48, 0))
        draw.text((px, py + 26), text, font=font(30), fill=(250, 248, 244), anchor="mm")
        draw.text((px, py + 60), f"78 x {L.top:.1f} mm from the door", font=font(22), fill=(235, 228, 218), anchor="mm")
    caption(img, "Two versions", "same mechanism and PCB; the USB one has no pouch and is 3.5 mm shorter").save(IMAGES / "v5_versions.png")


if __name__ == "__main__":
    versions()
    cutaway()
    exploded()
    presets()
    size()
    print("done")
