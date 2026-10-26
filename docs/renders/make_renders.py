"""Renders and animations for the README.

  pip install manifold3d trimesh vtk pillow
  python docs/renders/make_renders.py            # everything
  python docs/renders/make_renders.py clutch     # only the clutch images / animation

Writes to images/.
"""

import math
import sys
from pathlib import Path

from manifold3d import CrossSection, JoinType, Manifold
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "3D printed case" / "clutch"))
sys.path.insert(0, str(ROOT / "3D printed case" / "battery"))
sys.path.insert(0, str(Path(__file__).parent))

import adhesive_mount as am  # noqa: E402
import clutch as c  # noqa: E402
from render_lib import Scene, callouts, caption, chips  # noqa: E402

IMAGES = ROOT / "images"

OPEN_ANGLE = -math.degrees(math.asin((c.TRAVEL / 2) / c.FORK_PIVOT_Y))
CLOSED_ANGLE = -OPEN_ANGLE
RELIEF_DEG = -3.0


# ------------------------------------------------------------------------------------------------- clutch scene

def thumb_turn():
    """Door, rosette and thumb-turn wing, for context (not printed)."""
    wing = CrossSection.square((40, 11), center=True).offset(2.5, JoinType.Round, circular_segments=24).extrude(16)
    return wing.translate((0, 0, -38))


def rosette():
    return Manifold.cylinder(6, 25, circular_segments=96).translate((0, 0, -44)) + Manifold.cylinder(4, 9, circular_segments=48).translate((0, 0, -40))


def door():
    return Manifold.cube((170, 170, 3)).translate((-85, -85, -47))


def main_servo():
    sx, sy = c.SERVO_BODY
    near = c.SERVO_SHAFT_FROM_END
    body = Manifold.cube((sx - 0.4, sy - 0.4, 40)).translate((-sx / 2 + 0.2, -(sy - near) + 0.2, c.SERVO_FACE_Z))
    tabs = Manifold.cube((sx - 2, sy + 14, 2.5)).translate((-sx / 2 + 1, -(sy - near) - 7, c.SERVO_FACE_Z + 11))
    horn = Manifold.cube((30, 6, 2.6)).translate((-15, -3, c.HUB_TOP - 2.4))
    return body + tabs, horn


def clutch_parts(fork_angle, hub_rot, adapter_rot, explode=0.0):
    """Every part placed for a given state. Rotations in degrees about the lock axis."""
    z = c.pin_offset(fork_angle)
    servo, horn = main_servo()
    e = explode
    return [
        (door().translate((0, 0, -3 * e)), "door"),
        (rosette().translate((0, 0, -3 * e)), "metal"),
        (thumb_turn().rotate((0, 0, adapter_rot)).translate((0, 0, -2 * e)), "metal"),
        (c.knob_adapter().rotate((0, 0, adapter_rot)).translate((0, 0, -1.2 * e)), "adapter"),
        (c.slider(-c.GROOVE_CENTER_IN_SLIDER + z).rotate((0, 0, hub_rot)).translate((0, 0, 0.0 * e)), "slider"),
        (c.hub().rotate((0, 0, hub_rot)).translate((0, 0, 1.0 * e)), "hub"),
        (horn.rotate((0, 0, hub_rot)).translate((0, 0, 1.5 * e)), "metal"),
        (c.fork(fork_angle).translate((0, 0, 0.0 * e)), "fork"),
        (c.sg90_box().translate((0, 18 * e / 10, 0.4 * e)), "sg90"),
        (c.bracket().translate((0, 0, 2.2 * e)), "bracket"),
        (servo.translate((0, 0, 2.6 * e)), "servo"),
    ]


def render_parts(scene, parts, cut=False):
    scene.clear()
    keep = Manifold.cube((300, 300, 300)).translate((-150, 0, -150))
    for part, color in parts:
        if cut and color not in ("door",):
            part = part ^ keep
            if part.is_empty():
                continue
        scene.add(part, color, specular=0.1 if color in ("door",) else 0.3)


CAM_MAIN = dict(position=(-200, 165, 95), focal=(0, 0, -6), angle=28)


def clutch_stills():
    scene = Scene(1400, 900)

    render_parts(scene, clutch_parts(OPEN_ANGLE, 0, 0))
    scene.camera(**CAM_MAIN)
    img = scene.image()
    callouts(img, scene, [
        ("main servo", (-9.9, -4, c.SERVO_FACE_Z + 26)),
        ("bracket", (-12.3, 2, c.SERVO_FACE_Z + 3)),
        ("SG90 clutch servo", (-6.0, c.FORK_PIVOT_Y + 6.2, -2)),
        ("hub (hex shaft)", (-11.5, 9.6, c.HEX_TOP + 2)),
        ("fork", (-18.3, 18.0, 0)),
        ("slider (6 dog teeth)", (-9.0, 10.5, c.SLIDER_OPEN_Z + 9.0)),
        ("thumb-turn adapter", (-26.0, 0, c.FLANGE_BOTTOM - 12)),
        ("thumb-turn rosette on the door", (-15.0, 18.0, -44)),
    ])
    caption(img, "Servo clutch, assembled", "The main servo drives the thumb-turn only while the SG90 holds the clutch closed").save(IMAGES / "clutch_render.png")

    render_parts(scene, clutch_parts(OPEN_ANGLE, 0, 0, explode=14))
    scene.camera(position=(-250, 210, 120), focal=(0, 0, -6), angle=33)
    caption(scene.image(), "Exploded view", "door · thumb-turn · adapter with slotted flange · slider · hub · fork + SG90 · bracket · servo").save(IMAGES / "clutch_exploded.png")

    tiles = []
    context = ("door", "metal")
    states = (
        (OPEN_ANGLE, "Clutch open: thumb-turn turns freely", "teeth lifted out", c.SLIDER_OPEN_Z),
        (CLOSED_ANGLE, "Clutch closed: servo drives the lock", "teeth in the adapter's slots", c.SLIDER_CLOSED_Z),
    )
    for angle, title, note, tooth_z in states:
        parts = [(p, col) for p, col in clutch_parts(angle, 0, 0) if col not in context]
        render_parts(scene, parts, cut=True)
        scene.camera(position=(10, -260, 30), focal=(4, 0, -2), angle=15)
        img = scene.image()
        callouts(img, scene, [
            (note, (c.TOOTH_R_OUT - 1.5, 0, tooth_z + 0.6)),
            ("fork pin in the groove", (c.GROOVE_RADIUS + 1.5, 0, c.pin_offset(angle))),
            ("hex shaft", (-3.5, 0, c.HEX_TOP - 4)),
            ("adapter flange", (-c.FLANGE_RADIUS + 2, 0, c.FLANGE_BOTTOM + 1.5)),
        ], margin=300)
        tiles.append(caption(img.crop((150, 0, 1250, 900)), title))
    section = Image.new("RGB", (2200, 900), "white")
    section.paste(tiles[0], (0, 0))
    section.paste(tiles[1], (1100, 0))
    section.save(IMAGES / "clutch_section.png")
    print("clutch stills done")


def clutch_animation(fps=15):
    """Storyboard: manual turn with the clutch open, then one motorised locking cycle."""
    steps = []  # (fork_angle, hub_rot, adapter_rot, step, title, subtitle)

    def hold(n, state, *text):
        steps.extend([(*state, *text)] * n)

    def move(n, start, end, *text, ease=True):
        for i in range(n):
            t = (i + 1) / n
            if ease:
                t = 0.5 - 0.5 * math.cos(math.pi * t)
            steps.append((*[a + (b - a) * t for a, b in zip(start, end)], *text))

    idle = (OPEN_ANGLE, RELIEF_DEG, 0.0)
    t1 = ("1", "Idle: clutch open", "Nothing connects the servo to the thumb-turn")
    t2 = ("2", "Key from outside / thumb-turn by hand", "The thumb-turn spins freely, the servo does not move")
    t3 = ("3", "Lock command (Home Key, Home app, button)", "The SG90 tilts the fork, the slider's teeth drop into the adapter")
    t4 = ("4", "Main servo turns the lock", "Hub, slider and thumb-turn turn together")
    t5 = ("5", "Short reverse, then the clutch opens", "Unloads the teeth so the slider lifts out easily")
    t6 = ("6", "Done: locked, and the key turns freely again", "The lock reports its new state to Apple Home")

    hold(14, idle, *t1)
    move(48, idle, (OPEN_ANGLE, RELIEF_DEG, 360.0), *t2)
    hold(6, (OPEN_ANGLE, RELIEF_DEG, 360.0), *t2)
    after_manual = (OPEN_ANGLE, RELIEF_DEG, 0.0)  # 360 deg == 0 deg
    # The 3 deg left over from the last reverse is within the dog backlash, the teeth still drop in
    move(14, after_manual, (CLOSED_ANGLE, RELIEF_DEG, 0.0), *t3)
    hold(6, (CLOSED_ANGLE, RELIEF_DEG, 0.0), *t3)
    move(4, (CLOSED_ANGLE, RELIEF_DEG, 0.0), (CLOSED_ANGLE, 0.0, 0.0), *t4, ease=False)
    move(54, (CLOSED_ANGLE, 0.0, 0.0), (CLOSED_ANGLE, -360.0, -360.0), *t4)
    move(5, (CLOSED_ANGLE, -360.0, -360.0), (CLOSED_ANGLE, -360.0 + RELIEF_DEG, -360.0), *t5, ease=False)
    move(14, (CLOSED_ANGLE, -360.0 + RELIEF_DEG, -360.0), (OPEN_ANGLE, -360.0 + RELIEF_DEG, -360.0), *t5)
    hold(18, (OPEN_ANGLE, RELIEF_DEG, 0.0), *t6)

    scene = Scene(960, 640)
    frames = []
    previous_hub = None
    for i, (fork_angle, hub_rot, adapter_rot, step, title, subtitle) in enumerate(steps):
        render_parts(scene, clutch_parts(fork_angle, hub_rot, adapter_rot))
        scene.camera(position=(-150, -175, 62), focal=(0, 0, -9), angle=29)
        frame = caption(scene.image(), title, subtitle, step)
        closed = fork_angle > 0
        motor_running = previous_hub is not None and abs(hub_rot - previous_hub) > 1e-6
        previous_hub = hub_rot
        chips(frame, [
            ("clutch closed" if closed else "clutch open", (40, 170, 80) if closed else (160, 165, 175)),
            ("main servo running" if motor_running else "main servo idle", (245, 150, 40) if motor_running else (160, 165, 175)),
        ])
        frames.append(frame)
        if i % 20 == 0:
            print(f"  frame {i}/{len(steps)}")
    save_gif(frames, IMAGES / "clutch_operation.gif", fps)
    print("clutch animation done")


def save_gif(frames, path, fps):
    quantized = [f.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    quantized[0].save(path, save_all=True, append_images=quantized[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print(f"  {path.name}: {len(frames)} frames, {path.stat().st_size / 1e6:.1f} MB")


# ------------------------------------------------------------------------------------------------- battery scene

def battery_scene():
    """Self-adhesive mount on a door with a long escutcheon, the lock body and the battery box."""
    scene = Scene(1100, 900)
    door_part = Manifold.cube((260, 360, 4)).translate((-130, -230, -4))
    escutcheon = CrossSection.square((am.ESCUTCHEON_WIDTH - 2, 230), center=True).offset(1, JoinType.Round).extrude(am.ESCUTCHEON_DEPTH - 1).translate((0, 45, 0))
    handle = (Manifold.cylinder(18, 9, circular_segments=48).translate((0, 72, am.ESCUTCHEON_DEPTH - 1))
              + Manifold.cube((110, 18, 14), center=True).translate((-50, 72, am.ESCUTCHEON_DEPTH + 22)))
    mount = am.adhesive_mount()
    lock_body = (Manifold.cylinder(70, am.LOCK_DIAMETER / 2, circular_segments=128)
                 - Manifold.cylinder(80, am.LOCK_DIAMETER / 2 - 3.5, circular_segments=128).translate((0, 0, 3))).translate((0, 0, am.ESCUTCHEON_DEPTH))
    cap = Manifold.cylinder(3, am.LOCK_DIAMETER / 2 - 0.5, circular_segments=128).translate((0, 0, am.ESCUTCHEON_DEPTH + 70))
    led = (Manifold.cylinder(1.2, am.LOCK_DIAMETER / 2 - 5, circular_segments=128) - Manifold.cylinder(2, am.LOCK_DIAMETER / 2 - 9, circular_segments=128).translate((0, 0, -0.5))).translate((0, 0, am.ESCUTCHEON_DEPTH + 73))
    box = am.battery_box().translate((0, -115, 0))
    lid = am.battery_lid().rotate((180, 0, 0)).translate((0, -115, am.HOLDER[2] + am.BOX_WALL + 0.5 + 1.6))

    scene.add(door_part, "door", specular=0.05)
    scene.add(escutcheon, "metal", specular=0.6)
    scene.add(handle, "metal", specular=0.6)
    scene.add(mount, "plate")
    scene.add(lock_body, "case")
    scene.add(cap, "case")
    scene.add(led, (1.0, 0.98, 0.9), specular=0.0)
    scene.add(box, "plate")
    scene.add(lid, "plate")
    # Door upright: +y (handle) is up, the camera stands in front of the door, a bit to the right and below
    scene.camera(position=(260, -120, 360), focal=(-10, -25, 20), up=(0, 1, 0), angle=40)
    img = scene.image()
    r_plate = am.PLATE_DIAMETER / 2 - 4
    callouts(img, scene, [
        ("adhesive plate", (-r_plate * 0.75, -r_plate * 0.6, am.PLATE_THICKNESS)),
        ("collar, 3 screws into the lock body", (am.LOCK_DIAMETER / 2 + 3, 0, am.PLATE_THICKNESS + 8)),
        ("lock body", (am.LOCK_DIAMETER / 2 * 0.9, -am.LOCK_DIAMETER / 2 * 0.3, 50)),
        ("handle escutcheon", (am.ESCUTCHEON_WIDTH / 2 - 2, 120, am.ESCUTCHEON_DEPTH - 1)),
        ("4 x AA NiMH battery box", (am.HOLDER[0] / 2 + 3, -115, 10)),
    ], margin=230)
    front = caption(img, "On the door", "No screws in the door, the plate is stuck on around the cylinder")

    # Back of the plate: VHB tape and the escutcheon channel
    scene.clear()
    tape = (Manifold.cylinder(1.0, am.PLATE_DIAMETER / 2 - 2.5, circular_segments=128)
            - Manifold.cylinder(3, am.LOCK_DIAMETER / 2 + 2.5, circular_segments=128).translate((0, 0, -1)))
    tape -= Manifold.cube((am.ESCUTCHEON_WIDTH + 4, 300, 4), center=True)
    tape -= Manifold.cube((am.TAB_WIDTH + 4, 150, 4)).translate((-(am.TAB_WIDTH + 4) / 2, 0, -2))
    scene.add(mount, "plate")
    scene.add(tape.translate((0, 0, -0.6)), (0.35, 0.62, 0.95), specular=0.05)
    scene.camera(position=(-90, -150, -230), focal=(0, 0, 8), up=(0, 1, 0), angle=36)
    img = scene.image()
    callouts(img, scene, [
        ("VHB tape (~40 cm2)", (-r_plate * 0.7, -r_plate * 0.55, -1)),
        ("channel for the escutcheon", (0, -am.PLATE_DIAMETER / 2 + 6, am.ESCUTCHEON_DEPTH)),
        ("notch for the original tab", (0, am.PLATE_DIAMETER / 2 - 6, 4)),
    ], margin=230)
    back = caption(img, "Back of the plate", "Tape ring on both sides of the escutcheon channel")

    sheet = Image.new("RGB", (2 * front.width, front.height), "white")
    sheet.paste(front, (0, 0))
    sheet.paste(back, (front.width, 0))
    sheet.save(IMAGES / "battery_mount_render.png")
    print("battery render done")


if __name__ == "__main__":
    which = set(sys.argv[1:]) or {"clutch", "battery", "homekey"}
    if "clutch" in which:
        clutch_stills()
        clutch_animation()
    if "battery" in which:
        battery_scene()
    if "homekey" in which:
        import homekey_flow
        homekey_flow.main(IMAGES)
