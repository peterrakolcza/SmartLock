"""Builds the v5 PCB in KiCad from layout.py + netlist.py (runs inside a KiCad 9 container: pcbnew + kicad-cli).

    python3 make_board.py place    # outline, parts (passives placed automatically), nets -> smartlock_v5.kicad_pcb
    python3 make_board.py route    # router.py: 2-layer grid router (A*, vias, rip-up and retry)
    python3 make_board.py finish   # ground pours, DRC, Gerbers, drill, BOM, pick and place, renders

World coordinates (mm, +y up, origin on the lock axis) map to KiCad as x + 100, 100 - y.
"""

import json
import math
import sys
from pathlib import Path

import pcbnew

import layout
import netlist

HERE = Path(__file__).parent
PCB = HERE / "smartlock_v5.kicad_pcb"
LIB = Path("/usr/share/kicad/footprints")
OX, OY = 100.0, 100.0


def mm(v):
    return pcbnew.FromMM(v)


def to_k(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY - y))


def from_k(p):
    return pcbnew.ToMM(p.x) - OX, OY - pcbnew.ToMM(p.y)


def polygon_contains(poly, x, y):
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def courtyard(fp):
    layer = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
    c = fp.GetCourtyard(layer)
    b = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
    x0, y1 = from_k(pcbnew.VECTOR2I(b.GetLeft(), b.GetTop()))
    x1, y0 = from_k(pcbnew.VECTOR2I(b.GetRight(), b.GetBottom()))
    return x0, y0, x1, y1


def overlaps(a, b, gap=0.15):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def place():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(layout.THICKNESS))
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_MinClearance = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_HoleClearance = mm(0.25)
    ds.m_CopperEdgeClearance = mm(0.3)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(0.15))
    nc.SetTrackWidth(mm(0.2))
    nc.SetViaDiameter(mm(0.5))
    nc.SetViaDrill(mm(0.3))

    # Outline
    outline = layout.outline()
    for (x1, y1), (x2, y2) in zip(outline, outline[1:] + outline[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(to_k(x1, y1))
        seg.SetEnd(to_k(x2, y2))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    # Nets and net classes
    nets = {}
    for name in sorted(netlist.nets()):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    # Footprints
    fps = {}
    for ref, (footprint, value, mpn, pads, anchor) in netlist.PARTS.items():
        lib, name = footprint.split(":")
        fp = pcbnew.FootprintLoad(str(LIB / f"{lib}.pretty"), name)
        assert fp is not None, footprint
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetField("MPN", mpn) if hasattr(fp, "SetField") else None
        board.Add(fp)
        for pad in fp.Pads():
            net = pads.get(pad.GetNumber())
            if net:
                pad.SetNet(nets[net])
        fps[ref] = fp

    placed = {}       # ref -> courtyard box (world) per side
    keepout = layout.ANTENNA_KEEPOUT

    def put(ref, x, y, rot, side):
        fp = fps[ref]
        if side == "bottom" and not fp.IsFlipped():
            fp.Flip(to_k(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(to_k(x, y))
        fp.SetOrientationDegrees(rot)
        placed[ref] = (courtyard(fp), side)

    for ref, (x, y, rot, side, body, offset, _, _) in layout.FIXED.items():
        put(ref, x, y, rot, side)

    def free(ref, box, side):
        if not all(polygon_contains(outline, px, py) for px in (box[0] - 0.3, box[2] + 0.3) for py in (box[1] - 0.3, box[3] + 0.3)):
            return False
        if ref != "U1" and overlaps(box, keepout, 0.2) and side == "top":
            return False
        if ref != "U1" and overlaps(box, keepout, 0.2) and side == "bottom":
            return False
        for cx, cy in layout.CLAMPS:
            if overlaps(box, (cx - layout.CLAMP_R, cy - layout.CLAMP_R, cx + layout.CLAMP_R, cy + layout.CLAMP_R), 0.2):
                return False
        if overlaps(box, (layout.FIXED["D1"][0] - 2.0, layout.FIXED["D1"][1] - 2.0, layout.FIXED["D1"][0] + 2.0, layout.FIXED["D1"][1] + 2.0), 0.0) and ref != "D1" and side == "top":
            pass
        for other, (obox, oside) in placed.items():
            if oside == side and overlaps(box, obox, 0.25):
                return False
        return True

    def auto(ref, tx, ty, side, rots=(0, 90)):
        fp = fps[ref]
        best = None
        for r in range(0, 160):
            ring_r = r * 0.25
            steps = max(1, int(2 * math.pi * ring_r / 0.25))
            for i in range(steps):
                a = 2 * math.pi * i / steps
                x, y = tx + ring_r * math.cos(a), ty + ring_r * math.sin(a)
                for rot in rots:
                    if side == "bottom" and not fp.IsFlipped():
                        fp.Flip(to_k(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
                    fp.SetPosition(to_k(x, y))
                    fp.SetOrientationDegrees(rot)
                    box = courtyard(fp)
                    if free(ref, box, side):
                        best = (x, y, rot)
                        break
                if best:
                    break
            if best:
                break
        assert best, f"no room for {ref}"
        put(ref, best[0], best[1], best[2], side)

    # Mid-size parts near where their connections go
    targets = {"U2": (-8.0, -16.0), "U3": (-22.0, -21.0), "U4": (-3.0, -25.0), "J2": (-28.0, -16.5), "J3": (-12.0, -14.5)}
    for ref, (tx, ty) in targets.items():
        auto(ref, tx, ty, "top", rots=(0, 90, 180, 270))
    # Passives next to their anchor part (hall decoupling on the bottom, next to the sensor)
    for ref, (_, _, _, pads, anchor) in netlist.PARTS.items():
        if ref in placed:
            continue
        ax, ay = from_k(fps[anchor].GetPosition())
        side = "bottom" if anchor in ("U5", "U6") else "top"
        auto(ref, ax, ay, side)

    # Silkscreen: no part text (the board is hidden in the lock)
    for fp in fps.values():
        for field in fp.GetFields():          # reference, value, MPN, ...
            field.SetVisible(False)
    pcbnew.SaveBoard(str(PCB), board)

    out = {}
    for ref, fp in fps.items():
        x, y = from_k(fp.GetPosition())
        fixed = layout.FIXED.get(ref)
        if fixed:
            body, offset = fixed[4], fixed[5]
        else:
            b = placed[ref][0]
            body, offset = (round(b[2] - b[0], 2), round(b[3] - b[1], 2), 1.2 if not ref.startswith(("J",)) else 2.9), (0, 0)
            body = (body[0], body[1], 2.9 if ref.startswith("J") else (1.2 if ref.startswith("U") else 0.9))
            offset = ((b[0] + b[2]) / 2 - x, (b[1] + b[3]) / 2 - y)
            if fp.GetOrientationDegrees() % 180:
                pass
        out[ref] = dict(x=round(x, 3), y=round(y, 3), rot=fp.GetOrientationDegrees(), side=placed[ref][1],
                        body=[body[0], body[1], body[2]] if fixed else [round(placed[ref][0][2] - placed[ref][0][0], 2), round(placed[ref][0][3] - placed[ref][0][1], 2), body[2]],
                        offset=[0.0, 0.0] if not fixed else list(offset))
        if not fixed:
            b = placed[ref][0]
            out[ref]["x"], out[ref]["y"], out[ref]["rot"] = round((b[0] + b[2]) / 2, 3), round((b[1] + b[3]) / 2, 3), 0.0
    (HERE / "placement.json").write_text(json.dumps(out, indent=1))
    print(f"placed {len(fps)} parts -> {PCB.name}, placement.json")


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "place"
    if stage == "place":
        place()
    elif stage == "route":
        import router
        router.route(PCB)
    elif stage == "finish":
        import finish
        finish.run(PCB)
