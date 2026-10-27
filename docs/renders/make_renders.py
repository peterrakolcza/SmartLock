"""Renders and animations for the README.

  pip install manifold3d trimesh vtk pillow
  python docs/renders/make_renders.py            # everything
  python docs/renders/make_renders.py lock       # only the single-servo lock images and animation

Writes to images/.
"""

import math
import sys
from pathlib import Path

from manifold3d import Manifold
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "3D printed case" / "spiral"))
sys.path.insert(0, str(Path(__file__).parent))

import lock as k  # noqa: E402
from render_lib import Scene, callouts, caption, chips, font  # noqa: E402

IMAGES = ROOT / "images"
ORIGINAL = ROOT / "3D printed case"

L = k.L
FP = k.FREE_PLAY
TURNS = 2                                   # a two-turn lock in the animation
PARK_AFTER_UNLOCK = 135.0 + TURNS * 360.0   # hub position after an unlock + park (h, with the thumb-turn at 0)
# Cut away the half of the case that faces the camera
HALF = Manifold.cube((400, 400, 400)).translate((-200, -400, -100))
CUT = {"shell", "cap", "pcb", "chassis"}


def door():
    return Manifold.cube((180, 220, 3)).translate((-90, -110, -12))


def render(scene, parts, cut=(), see_through=()):
    scene.clear()
    scene.add(door(), "door", specular=0.05)
    for name, (part, color, _) in parts.items():
        if name in cut:
            part = part - HALF
            if part.is_empty():
                continue
        scene.add(part, color, opacity=0.35 if name in see_through else 1.0, specular=0.3)


# ------------------------------------------------------------------------------------------------- stills
def lock_stills():
    scene = Scene(1400, 1000)
    render(scene, k.assembly(h=PARK_AFTER_UNLOCK), cut=CUT)
    scene.camera(position=(-190, -230, 105), focal=(0, 0, 40), angle=30)
    img = scene.image()
    callouts(img, scene, [
        ("cap + LED diffuser", (-20, 0, L.top + k.CAP_T)),
        ("V3 PCB (unchanged)", (-30, 0, L.pcb + 0.8)),
        ("main servo (MG996R 360)", (-9.9, 8, L.F + 22)),
        ("chassis plate", (-30, 0, L.plate + 1.5)),
        ("hall sensor (hub turns)", (k.polar(k.HALL_R, k.HALL_ANGLE)[0] - 2, 0, L.hub_top + 3)),
        ("spiral hub", (-k.HUB_R * 0.7, -k.HUB_R * 0.7, L.hub0 + 3)),
        ("thumb-turn adapter + follower", (-14, -9, L.A - 9)),
        ("shell with door tab", (-41, 0, 25)),
    ], margin=230)
    caption(img, "Single-servo lock, cut open", f"{2 * k.SHELL_R:.0f} mm x {L.top + k.CAP_T:.0f} mm, one servo, the V3 PCB unchanged").save(IMAGES / "lock_cutaway.png")

    parts = k.assembly(h=PARK_AFTER_UNLOCK)
    offsets = {"thumb_turn": -16, "knob_adapter": -4, "follower": 4, "pin": 4, "hub": 16, "horn": 16, "hall": 30,
               "chassis": 30, "reed": 30, "servo": 46, "pcb": 66, "cap": 82, "shell": 0}
    exploded = {n: (p.translate((0, 0, offsets.get(n, 0))), c, pr) for n, (p, c, pr) in parts.items()}
    exploded["diffuser"] = (k.diffuser().translate((0, 0, L.top + k.CAP_T - 1.2 + 88)), (0.98, 0.97, 0.92), True)
    render(scene, exploded, cut={"shell"})
    scene.camera(position=(-250, -320, 190), focal=(0, 0, 70), angle=36)
    caption(scene.image(), "Exploded", "shell · adapter + follower + pin · spiral hub · chassis + sensors · servo · PCB · cap + diffuser").save(IMAGES / "lock_exploded.png")
    print("lock stills done")


def spiral_explained():
    """The hub lifted and tipped over, so you see the spiral groove, next to the adapter with the follower."""
    scene = Scene(1500, 900)
    h = PARK_AFTER_UNLOCK
    lift = 46
    hub = k.hub(h).translate((0, 0, -L.hub0)).rotate((180, 0, 0)).translate((0, 0, L.hub0 + lift))  # upside down
    adapter = k.knob_adapter()
    follower = k.follower(0, h)
    pin = k.pin_model(0, h)
    scene.clear()
    scene.add(adapter, "adapter")
    scene.add(follower, "slider")
    scene.add(pin, "metal")
    scene.add(hub.translate((62, 0, -lift + 4)), "hub")
    scene.camera(position=(10, -170, 150), focal=(30, 0, L.A), angle=34)
    img = scene.image()
    px, py = k.polar(k.pin_radius(h), k.SLOT_ANGLE)
    callouts(img, scene, [
        ("steel pin on the follower", (px, py, L.A + 2.2)),
        ("follower slides in this slot", (0, 22, L.A)),
        ("thumb-turn adapter", (-20, -8, L.A - 6)),
        ("spiral groove under the hub, 2.75 turns", (62 + k.HUB_R - 2, 0, L.hub0 + 4.0)),
    ], margin=260)
    caption(img, "The spiral coupling", "the pin rides in the groove; the hub only drives the thumb-turn at the two ends of the spiral").save(IMAGES / "spiral_explained.png")
    print("spiral explained done")


def size_comparison():
    scene = Scene(1600, 820)
    bottom = k.from_stl(ORIGINAL / "bottom.stl")
    middle = k.from_stl(ORIGINAL / "middle.stl").rotate((180, 0, 0))
    cover = k.diffuser()
    original = bottom + middle.translate((0, 0, 73)) + cover.translate((0, 0, 71.8))
    clutch_h = 89.9  # compact clutch version (feature/clutch)
    clutch = k.cyl(k.SHELL_R, 0, clutch_h) + k.cyl(10, -1, 0)
    single = k.shell() + k.cap() + k.diffuser().translate((0, 0, L.top + k.CAP_T - 1.2))
    scene.clear()
    scene.add(Manifold.cube((520, 240, 3)).translate((-260, -60, -3)), "door", specular=0.05)
    spots = {"original (no clutch)": (-170, original, "case", 87, 73.0),
             "compact clutch (2 servos)": (0, clutch, (0.62, 0.5, 0.75), 2 * k.SHELL_R, clutch_h),
             "single servo + spiral": (170, single, "hub", 2 * k.SHELL_R, L.top + k.CAP_T)}
    for _, (x, part, color, _, _) in spots.items():
        scene.add(part.translate((x, 0, 0)), color, specular=0.3)
    scene.camera(position=(0, -560, 210), focal=(0, 0, 30), angle=30)
    img = scene.image()
    draw = ImageDraw.Draw(img, "RGBA")
    for name, (x, _, _, w, h) in spots.items():
        px, py = scene.project((x, -60, 0))
        draw.text((px, py + 30), name, font=font(26), fill=(25, 28, 36), anchor="mm")
        draw.text((px, py + 62), f"{w:.0f} x {h:.0f} mm", font=font(22), fill=(80, 86, 98), anchor="mm")
    caption(img, "Size", "one servo, no clutch parts, and 4.5 mm lower than the two-servo clutch version").save(IMAGES / "size_comparison.png")
    print("size comparison done")


# ------------------------------------------------------------------------------------------------- animation
def spiral_diagram(h, kk, size=300):
    """Top view of the spiral (in the hub's frame) with the pin, drawn with PIL."""
    img = Image.new("RGB", (size, size), (247, 248, 250))
    d = ImageDraw.Draw(img, "RGBA")
    c = size / 2
    scale = (size / 2 - 18) / k.HUB_R
    d.ellipse([c - k.HUB_R * scale, c - k.HUB_R * scale, c + k.HUB_R * scale, c + k.HUB_R * scale], fill=(214, 228, 250), outline=(40, 110, 220), width=3)
    pts = []
    for i in range(0, 331):
        t = k.SPIRAL_TURNS * i / 330
        x, y = k.spiral_point(t)
        pts.append((c + x * scale, c - y * scale))
    d.line(pts, fill=(60, 70, 90), width=int(k.GROOVE_W * scale), joint="curve")
    for t, label in ((0, "end"), (k.SPIRAL_TURNS, "end")):
        x, y = k.spiral_point(t)
        d.ellipse([c + x * scale - 6, c - y * scale - 6, c + x * scale + 6, c - y * scale + 6], outline=(220, 70, 60), width=3)
    t = min(max((h - kk) / 360.0, 0.0), k.SPIRAL_TURNS)
    x, y = k.spiral_point(t)
    r = k.PIN_D / 2 * scale + 2
    d.ellipse([c + x * scale - r, c - y * scale - r, c + x * scale + r, c - y * scale + r], fill=(245, 150, 40), outline=(30, 34, 44), width=2)
    d.text((c, 14), "spiral, seen from above", font=font(18), fill=(25, 28, 36), anchor="mm")
    at_end = t <= 0.002 or t >= k.SPIRAL_TURNS - 0.002
    d.text((c, size - 14), "pin at the end: hub drives" if at_end else "pin free: key / hub turn alone", font=font(17),
           fill=(220, 70, 60) if at_end else (52, 140, 80), anchor="mm")
    return img


def lock_animation(fps=15):
    steps = []  # (h, k, step, title, subtitle)

    def hold(n, state, *text):
        steps.extend([(*state, *text)] * n)

    def move(n, start, end, *text, ease=True):
        for i in range(n):
            t = (i + 1) / n
            if ease:
                t = 0.5 - 0.5 * math.cos(math.pi * t)
            steps.append((*[a + (b - a) * t for a, b in zip(start, end)], *text))

    park = PARK_AFTER_UNLOCK
    t1 = ("1", "Idle: the servo is parked in the spiral", "The pin is free to walk along the groove")
    t2 = ("2", "Key from outside: locked by hand, 2 turns", "The pin walks along the spiral, the servo does not move")
    t3 = ("3", "Unlock command: the servo takes up the free play", "The hub turns alone until the pin reaches the end of the spiral")
    t4 = ("4", "The servo turns the lock", "Pin at the end of the spiral: hub and thumb-turn turn together")
    t5 = ("5", "The servo backs off into the spiral", "The hall sensor counts the hub turns: 2 + 1 magnet passes")
    t6 = ("6", "Done: unlocked, and the key turns freely again", "The lock reports its new state to Apple Home")
    hold(12, (park, 0.0), *t1)
    move(54, (park, 0.0), (park, 720.0), *t2)
    hold(6, (park, 720.0), *t2)
    move(14, (park, 720.0), (720.0, 720.0), *t3, ease=False)
    move(54, (720.0, 720.0), (0.0, 0.0), *t4)
    move(40, (0.0, 0.0), (park, 0.0), *t5, ease=False)
    hold(16, (park, 0.0), *t6)

    scene = Scene(960, 680)
    static = {n: v for n, v in k.assembly().items() if n in ("shell", "cap", "pcb", "chassis", "servo", "hall", "reed")}
    side_half = Manifold.cube((400, 400, 400)).translate((0, -200, -100))
    static_cut = {n: ((p - side_half) if n in CUT else p, c, pr) for n, (p, c, pr) in static.items()}
    adapter, turn, hub0 = k.knob_adapter(), k.thumb_turn(), k.hub(0.0)
    _, horn = k.servo_model()
    frames = []
    prev = None
    for i, (h, kk, step, title, subtitle) in enumerate(steps):
        moving = {
            "knob_adapter": (adapter.rotate((0, 0, kk)), "adapter", True),
            "thumb_turn": (turn.rotate((0, 0, kk)), "metal", False),
            "follower": (k.follower(kk, h), "slider", True),
            "pin": (k.pin_model(kk, h), "metal", False),
            "hub": (hub0.rotate((0, 0, h)), "hub", True),
            "horn": (horn.rotate((0, 0, h)), "metal", False),
        }
        render(scene, {**static_cut, **moving}, see_through={"hub"})
        scene.camera(position=(230, -90, 95), focal=(0, -4, 42), angle=25)
        frame = scene.image()
        frame.paste(spiral_diagram(h, kk), (frame.width - 312, 12))
        frame = caption(frame, title, subtitle, step)
        motor = prev is not None and abs(h - prev) > 1e-6
        prev = h
        chips(frame, [("servo running" if motor else "servo idle", (245, 150, 40) if motor else (160, 165, 175))])
        frames.append(frame)
        if i % 30 == 0:
            print(f"  frame {i}/{len(steps)}")
    save_gif(frames, IMAGES / "lock_operation.gif", fps)
    print("lock animation done")


def save_gif(frames, path, fps):
    quantized = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    quantized[0].save(path, save_all=True, append_images=quantized[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print(f"  {path.name}: {len(frames)} frames, {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"lock", "homekey"}
    if "lock" in which:
        lock_stills()
        spiral_explained()
        size_comparison()
        lock_animation()
    if "homekey" in which:
        import homekey_flow
        homekey_flow.main(IMAGES)
