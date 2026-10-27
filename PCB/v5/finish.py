"""Ground pours, KiCad DRC, fabrication outputs (runs inside the KiCad container)."""

import csv
import json
import subprocess
from pathlib import Path

import pcbnew

import layout
import netlist

HERE = Path(__file__).parent
FAB = HERE / "fab"


def mm(v):
    return pcbnew.FromMM(v)


def pours(board):
    for z in list(board.Zones()):
        board.Remove(z)
    gnd = board.FindNet("GND")
    outline = layout.outline()
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        zone = pcbnew.ZONE(board)
        zone.SetLayer(layer)
        zone.SetNet(gnd)
        poly = zone.Outline()
        poly.NewOutline()
        for x, y in outline:
            poly.Append(mm(100 + x), mm(100 - y))
        zone.SetLocalClearance(mm(0.2))
        zone.SetMinThickness(mm(0.2))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)     # reflow assembled: solid is fine, and no starved thermals
        board.Add(zone)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def drc(pcb):
    out = HERE / "drc.json"
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-error", "--schematic-parity", "-o", str(out), str(pcb)],
                   capture_output=True)
    if not out.exists():
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-error", "-o", str(out), str(pcb)], capture_output=True)
    report = json.loads(out.read_text())
    violations = [v for v in report.get("violations", []) if v.get("severity") == "error"]
    # The USB-C receptacle's own footprint: its locating holes sit 0.19 mm from its own pads, and its shell
    # reaches the board edge on purpose (the plug comes in through the case wall). Listed, not hidden.
    accepted = [v for v in violations if v["type"] in ("hole_clearance", "copper_edge_clearance")
                and all("of J1" in i.get("description", "") or "Edge.Cuts" in i.get("description", "")
                        for i in v.get("items", []))
                and any("of J1" in i.get("description", "") for i in v.get("items", []))]
    for v in accepted:
        print("   accepted (USB-C footprint):", v["type"], [i.get("description") for i in v.get("items", [])])
    violations = [v for v in violations if v not in accepted]
    unconnected = report.get("unconnected_items", [])
    kinds = {}
    for v in violations:
        kinds[v["type"]] = kinds.get(v["type"], 0) + 1
    return violations, unconnected, kinds


def fab(pcb):
    FAB.mkdir(exist_ok=True)
    run = lambda *a: subprocess.run(["kicad-cli", "pcb", "export", *a], capture_output=True, check=True)  # noqa: E731
    run("gerbers", "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts", "-o", str(FAB) + "/", str(pcb))
    run("drill", "-o", str(FAB) + "/", str(pcb))
    run("pos", "--format", "csv", "--units", "mm", "--side", "both", "-o", str(FAB / "pick_and_place.csv"), str(pcb))
    (FAB / "bom.csv").unlink(missing_ok=True)
    for version, dnp in netlist.DNP.items():               # one board, two BOMs (the assembler only places BOM parts)
        with open(FAB / f"bom_{version}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Designator", "Value", "Footprint", "Manufacturer part"])
            groups = {}
            for ref, (fp, value, mpn, _, _) in netlist.PARTS.items():
                if ref not in dnp:
                    groups.setdefault((value, fp, mpn), []).append(ref)
            for (value, fp, mpn), refs in sorted(groups.items(), key=lambda g: g[1][0]):
                w.writerow([",".join(refs), value, fp.split(":")[1], mpn])
    for side in ("top", "bottom"):
        subprocess.run(["kicad-cli", "pcb", "render", "--side", side, "--width", "1600", "--height", "900", "--quality", "basic",
                        "-o", str(HERE / f"render_{side}.png"), str(pcb)], capture_output=True)


def stats(board):
    tracks = [t for t in board.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    length = sum(pcbnew.ToMM(t.GetLength()) for t in tracks)
    return len(tracks), len(vias), length


def run(pcb):
    board = pcbnew.LoadBoard(str(pcb))
    pours(board)
    pcbnew.SaveBoard(str(pcb), board)
    violations, unconnected, kinds = drc(pcb)
    n_tracks, n_vias, length = stats(board)
    print(f"tracks {n_tracks}, vias {n_vias}, {length:.0f} mm of copper track")
    print(f"DRC errors: {len(violations)} {kinds}")
    for v in violations[:15]:
        print("  ", v["type"], "-", v["description"], [i.get("description") for i in v.get("items", [])][:2])
    print(f"unconnected items: {len(unconnected)}")
    for u in unconnected[:10]:
        print("  ", [i.get("description") for i in u.get("items", [])])
    fab(pcb)
    print("fab outputs in", FAB)
    return not violations and not unconnected
