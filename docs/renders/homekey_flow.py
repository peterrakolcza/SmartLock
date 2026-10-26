"""2D animation of the Home Key flow: phone -> HomeKey-ESP32 reader -> MQTT -> lock -> state back to Apple Home."""

import math

from PIL import Image, ImageDraw

from render_lib import font

W, H = 1100, 560
BG = (246, 247, 250)
INK = (28, 32, 42)
MUTED = (120, 126, 140)
ORANGE = (245, 150, 40)
GREEN = (52, 168, 83)
RED = (220, 70, 60)
BLUE = (40, 110, 220)

PHONE_HOME = (95, 250)
READER = (330, 250)
LOCK = (800, 250)
HOME_APP = (985, 125)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return a + (b - a) * t


def box(draw, center, size, fill, outline=INK, radius=18, width=3):
    x, y = center
    w, h = size
    draw.rounded_rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], radius, fill=fill, outline=outline, width=width)


def text(draw, xy, s, size=22, fill=INK, anchor="mm"):
    draw.text(xy, s, font=font(size), fill=fill, anchor=anchor)


def phone(draw, center, glow):
    x, y = center
    box(draw, (x, y), (64, 120), (250, 250, 252), radius=14)
    draw.rounded_rectangle([x - 26, y - 48, x + 26, y + 44], 6, fill=(30, 34, 44))
    # Wallet card on screen
    draw.rounded_rectangle([x - 20, y - 22, x + 20, y + 4], 4, fill=(214, 196, 160))
    text(draw, (x, y - 9), "HOME", 11, fill=(60, 50, 30))
    if glow > 0:
        for k in range(3):
            r = 22 + 16 * k + 10 * glow
            alpha = int(200 * (1 - k / 3) * glow)
            draw.arc([x + 30 - r, y - r, x + 30 + r, y + r], -40, 40, fill=(*BLUE, alpha), width=3)


def reader(draw, state):
    x, y = READER
    box(draw, (x, y), (150, 150), (255, 255, 255))
    draw.ellipse([x - 38, y - 52, x + 38, y + 24], outline=(190, 194, 204), width=3)
    text(draw, (x, y - 14), "NFC", 20, MUTED)
    text(draw, (x, y + 52), "HomeKey-ESP32", 18, INK)
    text(draw, (x, y + 100), "reader (ESP32 + PN532)", 18, MUTED)
    if state == "ok":
        draw.ellipse([x + 44, y - 92, x + 84, y - 52], fill=GREEN)
        draw.line([(x + 54, y - 72), (x + 62, y - 63), (x + 76, y - 81)], fill="white", width=5)


def lock(draw, angle, led, label_state):
    x, y = LOCK
    r = 80
    draw.ellipse([x - r - 10, y - r - 10, x + r + 10, y + r + 10], fill=(150, 154, 162), outline=INK, width=3)
    draw.ellipse([x - r + 6, y - r + 6, x + r - 6, y + r - 6], outline=(255, 244, 210) if led else (120, 124, 132), width=8)
    draw.ellipse([x - r + 18, y - r + 18, x + r - 18, y + r - 18], fill=(110, 114, 122))
    # Thumb-turn wing, rotates with the servo
    a = math.radians(angle)
    dx, dy = math.cos(a) * 42, math.sin(a) * 42
    nx, ny = -math.sin(a) * 11, math.cos(a) * 11
    draw.polygon([(x - dx - nx, y - dy - ny), (x + dx - nx, y + dy - ny), (x + dx + nx, y + dy + ny), (x - dx + nx, y - dy + ny)], fill=(220, 222, 226), outline=INK)
    text(draw, (x, y + r + 34), "Smart lock (ESP8266 / ESP32-C3)", 18, INK)
    text(draw, (x, y + r + 58), label_state, 18, MUTED)


def home_app(draw, state):
    x, y = HOME_APP
    colors = {"Locked": (INK, (255, 255, 255)), "Unlocking...": (ORANGE, (255, 248, 236)),
              "Unlocked": (GREEN, (238, 250, 241)), "Locking...": (ORANGE, (255, 248, 236))}
    fg, bg = colors[state]
    box(draw, (x, y), (190, 96), bg, outline=fg, radius=20)
    text(draw, (x, y - 23), "Apple Home", 16, MUTED)
    text(draw, (x, y + 7), "Front Door", 20, INK)
    text(draw, (x, y + 33), state, 18, fg)


def wire(draw, packet_t, direction, payload):
    """MQTT link between reader and lock with a packet travelling on it."""
    x0, x1, y = READER[0] + 80, LOCK[0] - 100, READER[1] - 20
    draw.line([(x0, y), (x1, y)], fill=(190, 194, 204), width=4)
    draw.line([(x0, y + 40), (x1, y + 40)], fill=(190, 194, 204), width=4)
    text(draw, ((x0 + x1) / 2 + 20, y + 78), "Wi-Fi · MQTT (broker built into the lock)", 17, MUTED)
    if packet_t is None:
        return
    if direction == "to_lock":
        px, py = lerp(x0, x1, packet_t), y
    else:
        px, py = lerp(x1, x0, packet_t), y + 40
    tw = draw.textbbox((0, 0), payload, font=font(16))[2] + 24
    px = min(max(px, x0 + tw / 2), x1 - tw / 2)
    draw.rounded_rectangle([px - tw / 2, py - 15, px + tw / 2, py + 15], 15, fill=ORANGE if direction == "to_lock" else GREEN)
    text(draw, (px, py), payload, 16, "white")


def caption(draw, step, title, subtitle):
    draw.rectangle([0, H - 78, W, H], fill=(20, 24, 32))
    draw.rounded_rectangle([24, H - 62, 64, H - 22], 10, fill=ORANGE)
    text(draw, (44, H - 42), step, 24, "white")
    draw.text((82, H - 70), title, font=font(26), fill="white")
    draw.text((82, H - 36), subtitle, font=font(18), fill=(200, 206, 216))


def frames():
    fps = 15
    timeline = [
        # (duration s, step, title, subtitle)
        (1.6, "1", "Tap your iPhone or Apple Watch", "Home Key in Wallet, Express mode: no unlocking or Face ID needed"),
        (1.2, "2", "The reader authenticates the Home Key", "HomeKey-ESP32 is the native Apple Home lock accessory"),
        (1.6, "3", "Reader to lock: \"unlocking\"", "MQTT topic smartlock-reader/homekit/state = 4"),
        (2.4, "4", "The lock closes its clutch and turns the thumb-turn", "Calibrated run time, then the clutch opens again"),
        (1.6, "5", "Lock to reader: \"unlocked\"", "set_state = 0, only now Apple Home shows Unlocked"),
        (1.4, "5", "Lock to reader: \"unlocked\"", "set_state = 0, only now Apple Home shows Unlocked"),
        (2.4, "6", "Someone locks it with the key by hand", "The reed sensor counts the turn, the clutch lets the key turn freely"),
        (1.6, "7", "Lock to reader: \"locked\"", "Apple Home stays in sync with manual changes"),
        (1.2, "7", "Lock to reader: \"locked\"", "Apple Home stays in sync with manual changes"),
    ]
    out = []
    for index, (duration, step, title, subtitle) in enumerate(timeline):
        n = int(duration * fps)
        for i in range(n):
            t = (i + 1) / n
            img = Image.new("RGB", (W, H), BG)
            draw = ImageDraw.Draw(img, "RGBA")
            text(draw, (W / 2, 34), "How Home Key works with the smart lock", 26, INK)

            phone_x = PHONE_HOME[0]
            glow = 0
            reader_state = "idle"
            packet = None
            angle = 0
            lock_state, app_state = "locked", "Locked"
            led = False

            if index == 0:
                phone_x = lerp(PHONE_HOME[0], READER[0] - 135, ease(t))
                glow = ease((t - 0.6) / 0.4)
            elif index == 1:
                phone_x, glow, reader_state = READER[0] - 135, 1, "ok" if t > 0.35 else "idle"
            elif index == 2:
                phone_x, reader_state = READER[0] - 135, "ok"
                packet = (ease(t), "to_lock", "state = 4  unlocking")
                app_state = "Unlocking..."
            elif index == 3:
                phone_x = lerp(READER[0] - 135, PHONE_HOME[0], ease(t))
                angle = -90 * ease(t)
                lock_state, app_state = "clutch closed · servo turning", "Unlocking..."
            elif index in (4, 5):
                angle, lock_state, led = -90, "unlocked · clutch open", True
                if index == 4:
                    packet = (ease(t), "to_reader", "set_state = 0  unlocked")
                    app_state = "Unlocking..."
                else:
                    app_state = "Unlocked"
            elif index == 6:
                angle = -90 + 90 * ease(t)
                led = t < 0.95
                lock_state, app_state = "key turned by hand · servo idle", "Unlocked"
            elif index in (7, 8):
                lock_state = "locked"
                if index == 7:
                    packet = (ease(t), "to_reader", "set_state = 1  locked")
                    app_state = "Unlocked"
                else:
                    app_state = "Locked"

            wire(draw, *(packet if packet else (None, None, None)))
            reader(draw, reader_state)
            lock(draw, angle, led, lock_state)
            home_app(draw, app_state)
            phone(draw, (phone_x, PHONE_HOME[1]), glow)
            if index == 6:
                kx, ky = LOCK[0] - 150, LOCK[1] - 110
                text(draw, (kx, ky), "key turned from outside", 18, INK)
            caption(draw, step, title, subtitle)
            out.append(img)
    return out, fps


def main(images_dir):
    imgs, fps = frames()
    quantized = [f.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in imgs]
    path = images_dir / "homekey_flow.gif"
    quantized[0].save(path, save_all=True, append_images=quantized[1:], duration=int(1000 / fps), loop=0, optimize=True)
    print(f"  {path.name}: {len(imgs)} frames, {path.stat().st_size / 1e6:.1f} MB")
