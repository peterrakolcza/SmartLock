"""Renders and animations for the README.

  pip install manifold3d trimesh vtk pillow
  python docs/renders/make_renders.py            # everything
  python docs/renders/make_renders.py clutch     # only the lock / clutch images and animation

Writes to images/.
"""

import math
import sys
from pathlib import Path

from manifold3d import Manifold
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "3D printed case" / "clutch"))
sys.path.insert(0, str(Path(__file__).parent))

import lock as k  # noqa: E402
from render_lib import Scene, callouts, caption, chips, font  # noqa: E402

IMAGES = ROOT / "images"
ORIGINAL = ROOT / "3D printed case"

L = k.L
RELIEF_DEG = -3.0
# Cut away the half of the case that faces the camera
HALF = Manifold.cube((400, 400, 400)).translate((-200, -400, -100))
SIDE_HALF = Manifold.cube((400, 400, 400)).translate((0, -200, -100))  # the +x half, for the animation
CUT = {"shell", "cap", "pcb", "chassis", "sg90_clip"}


def door():
    return Manifold.cube((180, 220, 3)).translate((-90, -110, -12))


def render(scene, parts, cut=()):
    scene.clear()
    scene.add(door(), "door", specular=0.05)
    for name, (part, color, _) in parts.items():
        if name in cut:
            part = part - HALF
            if part.is_empty():
                continue
        scene.add(part, color, specular=0.3)


CAM = dict(position=(-190, -230, 115), focal=(0, 0, 42), angle=31)


# ------------------------------------------------------------------------------------------------- stills
def lock_stills():
    scene = Scene(1400, 1000)

    render(scene, k.assembly(0.0), cut=CUT)
    scene.camera(**CAM)
    img = scene.image()
    callouts(img, scene, [
        ("cap + LED diffuser", (-20, 0, L.top + k.CAP_T)),
        ("V3 PCB (unchanged)", (-30, 0, L.pcb + 0.8)),
        ("main servo", (-9.9, 8, L.F + 22)),
        ("chassis plate", (-30, 0, L.plate + 1.5)),
        ("SG90 clutch servo", (-6.0, k.PIVOT_Y - 6.1, L.G + 9)),
        ("slider on the hub", (0, -k.SLIDER_R, L.A + k.OPEN_GAP + 5)),
        ("fork", (-14.4, -14.4, L.G + 1.5)),
        ("thumb-turn adapter", (-14, -9, L.A - 9)),
        ("shell with door tab", (-41, 0, 25)),
    ], margin=230)
    caption(img, "Compact clutch lock, cut open", f"{2 * k.SHELL_R:.0f} mm x {L.top + k.CAP_T:.0f} mm, the V3 PCB unchanged").save(IMAGES / "lock_cutaway.png")

    parts = k.assembly(0.0)
    offsets = {"thumb_turn": -18, "knob_adapter": -6, "slider": 10, "hub": 22, "horn": 22, "fork": 10, "sg90": 34,
               "sg90_horn": 34, "sg90_clip": 46, "chassis": 46, "servo": 62, "pcb": 82, "cap": 98, "shell": 0}
    exploded = {n: (p.translate((0, 0, offsets.get(n, 0))), c, pr) for n, (p, c, pr) in parts.items()}
    exploded["diffuser"] = (k.diffuser().translate((0, 0, L.top + k.CAP_T - 1.2 + 104)), (0.98, 0.97, 0.92), True)
    render(scene, exploded, cut={"shell"})
    scene.camera(position=(-260, -330, 200), focal=(0, 0, 78), angle=36)
    caption(scene.image(), "Exploded", "shell · adapter · slider + fork · hub · SG90 + clip + chassis · servo · PCB · cap + diffuser").save(IMAGES / "lock_exploded.png")

    tiles = []
    keep_half = Manifold.cube((400, 400, 400)).translate((-200, 0, -100))
    for closed, title, note in ((0.0, "Clutch open: the key turns freely", "teeth lifted out"),
                                (1.0, "Clutch closed: the servo drives the lock", "teeth in the adapter's slots")):
        parts = k.assembly(closed)
        scene.clear()
        for name in ("knob_adapter", "hub", "slider", "fork", "horn", "sg90", "sg90_horn"):
            part, color, _ = parts[name]
            scene.add(part ^ keep_half, color, specular=0.3)
        scene.camera(position=(15, -250, L.A + 12), focal=(4, 0, L.A + 4), angle=15)
        img = scene.image()
        tips = L.A + k.OPEN_GAP - k.TRAVEL * closed
        callouts(img, scene, [
            (note, (sum(k.TOOTH_R) / 2, 0, tips + 0.8)),
            ("fork pin in the groove", (k.SLIDER_R - k.GROOVE_DEPTH + 1.5, 0, L.G + k.pin_offset(k.fork_angle(closed)))),
            ("hub (hex)", (-6, 0, L.hub_top - 4)),
            ("adapter", (-k.DOG_DISC_R + 2, 0, L.A - 2)),
        ], margin=300)
        tiles.append(caption(img.crop((150, 0, 1250, 900)), title))
    section = Image.new("RGB", (2200, 900), "white")
    section.paste(tiles[0], (0, 0))
    section.paste(tiles[1], (1100, 0))
    section.save(IMAGES / "clutch_section.png")
    print("lock stills done")


def size_comparison():
    """Original case, the first clutch version (+22 mm ring) and the compact version, side by side on a door."""
    scene = Scene(1600, 820)
    bottom = k.from_stl(ORIGINAL / "bottom.stl")
    middle = k.from_stl(ORIGINAL / "middle.stl").rotate((180, 0, 0))
    cover = k.diffuser()
    original = bottom + middle.translate((0, 0, 73)) + cover.translate((0, 0, 71.8))
    ring = k.ring(40.0, 43.5, 0, 22)
    first_clutch = bottom + ring.translate((0, 0, 73)) + middle.translate((0, 0, 95)) + cover.translate((0, 0, 93.8))
    compact = k.shell() + k.cap() + k.diffuser().translate((0, 0, L.top + k.CAP_T - 1.2))
    scene.clear()
    scene.add(Manifold.cube((520, 240, 3)).translate((-260, -60, -3)), "door", specular=0.05)
    spots = {"original (no clutch)": (-170, original, "case"), "first clutch version": (0, first_clutch, (0.62, 0.5, 0.75)),
             "compact clutch": (170, compact, "hub")}
    for _, (x, part, color) in spots.items():
        scene.add(part.translate((x, 0, 0)), color, specular=0.3)
    scene.camera(position=(0, -560, 210), focal=(0, 0, 30), angle=30)
    img = scene.image()
    draw = ImageDraw.Draw(img, "RGBA")
    heights = {"original (no clutch)": 73.0, "first clutch version": 95.0, "compact clutch": L.top + k.CAP_T}
    widths = {"original (no clutch)": 87.0, "first clutch version": 87.0, "compact clutch": 2 * k.SHELL_R}
    for name, (x, _, _) in spots.items():
        px, py = scene.project((x, -60, 0))
        draw.text((px, py + 30), name, font=font(26), fill=(25, 28, 36), anchor="mm")
        draw.text((px, py + 62), f"{widths[name]:.0f} x {heights[name]:.0f} mm", font=font(22), fill=(80, 86, 98), anchor="mm")
    caption(img, "Size", "the compact clutch lock is smaller than the first clutch version, the clutch adds ~17 mm to the original").save(IMAGES / "size_comparison.png")
    print("size comparison done")


# ------------------------------------------------------------------------------------------------- animation
def clutch_animation(fps=15):
    """Key turned by hand (clutch open), then a motorised cycle: close, find the slots, turn, unload, open."""
    steps = []  # (closed_fraction, hub_rot, adapter_rot, step, title, subtitle)

    def hold(n, state, *text):
        steps.extend([(*state, *text)] * n)

    def move(n, start, end, *text, ease=True):
        for i in range(n):
            t = (i + 1) / n
            if ease:
                t = 0.5 - 0.5 * math.cos(math.pi * t)
            steps.append((*[a + (b - a) * t for a, b in zip(start, end)], *text))

    manual = 340.0                      # the key leaves the thumb-turn 20 deg away from where the teeth were
    resting = k.OPEN_GAP / k.TRAVEL     # teeth resting on the flange between the slots
    slot = 40.0                         # next slot ahead of the hub (adapter at 340 = slots at -20, 40, 100, ...)
    t1 = ("1", "Idle: clutch open", "Nothing connects the servo to the thumb-turn")
    t2 = ("2", "Key from outside / thumb-turn by hand", "The thumb-turn spins freely, the servo does not move")
    t3 = ("3", "Lock command: the SG90 closes the clutch", "The teeth land between the slots and rest on the adapter")
    t4 = ("4", "The servo starts, the teeth find the slots", "At most ~50 deg, the chamfers guide them in")
    t5 = ("5", "The servo turns the lock", "Until the reed sensor has seen the magnet the learned number of times")
    t6 = ("6", "Short reverse, then the clutch opens", "The key turns freely again")

    idle = (0.0, RELIEF_DEG, 0.0)
    hold(12, idle, *t1)
    move(44, idle, (0.0, RELIEF_DEG, manual), *t2)
    move(12, (0.0, RELIEF_DEG, manual), (resting, RELIEF_DEG, manual), *t3)
    hold(6, (resting, RELIEF_DEG, manual), *t3)
    move(14, (resting, RELIEF_DEG, manual), (resting, slot, manual), *t4, ease=False)
    move(6, (resting, slot, manual), (1.0, slot, manual), *t4)
    move(50, (1.0, slot, manual), (1.0, slot + 360, manual + 360), *t5)
    move(4, (1.0, slot + 360, manual + 360), (1.0, slot + 360 + RELIEF_DEG, manual + 360), *t6, ease=False)
    move(12, (1.0, slot + 360 + RELIEF_DEG, manual + 360), (0.0, slot + 360 + RELIEF_DEG, manual + 360), *t6)
    hold(14, (0.0, slot + 360 + RELIEF_DEG, manual + 360), *t6)

    scene = Scene(960, 680)
    static = {n: v for n, v in k.assembly(0.0).items() if n in ("shell", "cap", "pcb", "chassis", "sg90_clip", "servo", "sg90")}
    static_cut = {n: ((p - SIDE_HALF) if n in CUT else p, c, pr) for n, (p, c, pr) in static.items()}
    adapter, turn, hub = k.knob_adapter(), k.thumb_turn(), k.hub()
    _, horn = k.servo_model()
    frames = []
    previous_hub = None
    for i, (closed, hub_rot, adapter_rot, step, title, subtitle) in enumerate(steps):
        angle = k.fork_angle(closed)
        moving = {
            "knob_adapter": (adapter.rotate((0, 0, adapter_rot)), "adapter", True),
            "thumb_turn": (turn.rotate((0, 0, adapter_rot)), "metal", False),
            "hub": (hub.rotate((0, 0, hub_rot)), "hub", True),
            "horn": (horn.rotate((0, 0, hub_rot)), "metal", False),
            "slider": (k.slider(closed).rotate((0, 0, hub_rot)), "slider", True),
            "fork": (k.fork(angle), "fork", True),
            "sg90_horn": (k.sg90_horn(angle), "metal", False),
        }
        render(scene, {**static_cut, **moving})
        scene.camera(position=(230, -70, 85), focal=(0, -4, 46), angle=25)
        frame = caption(scene.image(), title, subtitle, step)
        motor = previous_hub is not None and abs(hub_rot - previous_hub) > 1e-6
        previous_hub = hub_rot
        engaged = closed > 0.99
        chips(frame, [
            ("clutch closed" if engaged else ("clutch closing" if closed > 0.01 else "clutch open"),
             (40, 170, 80) if engaged else ((245, 190, 60) if closed > 0.01 else (160, 165, 175))),
            ("main servo running" if motor else "main servo idle", (245, 150, 40) if motor else (160, 165, 175)),
        ])
        frames.append(frame)
        if i % 30 == 0:
            print(f"  frame {i}/{len(steps)}")
    save_gif(frames, IMAGES / "clutch_operation.gif", fps)
    print("clutch animation done")


def save_gif(frames, path, fps):
    quantized = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    quantized[0].save(path, save_all=True, append_images=quantized[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print(f"  {path.name}: {len(frames)} frames, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"clutch", "homekey"}
    if "clutch" in which:
        lock_stills()
        size_comparison()
        clutch_animation()
    if "homekey" in which:
        import homekey_flow
        homekey_flow.main(IMAGES)
