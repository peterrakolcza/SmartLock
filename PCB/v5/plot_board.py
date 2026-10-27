"""Plot the board (pads, tracks, vias, keep-out) to a PNG for checking the routing."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pcbnew
import layout

b = pcbnew.LoadBoard(sys.argv[1])
fig, ax = plt.subplots(figsize=(16, 7))
pts = [(x, y) for x, y in layout.outline()]
ax.plot([p[0] for p in pts + pts[:1]], [p[1] for p in pts + pts[:1]], "k-", lw=0.8)
k = layout.ANTENNA_KEEPOUT
ax.add_patch(plt.Rectangle((k[0], k[1]), k[2] - k[0], k[3] - k[1], fill=False, ls="--", ec="gray"))
W = lambda p: (pcbnew.ToMM(p.x) - 100, 100 - pcbnew.ToMM(p.y))  # noqa: E731
for fp in b.GetFootprints():
    for pad in fp.Pads():
        bb = pad.GetBoundingBox()
        x0, y1 = W(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()))
        x1, y0 = W(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
        col = "#c33" if pad.IsOnLayer(pcbnew.F_Cu) and not pad.IsOnLayer(pcbnew.B_Cu) else ("#36c" if not pad.IsOnLayer(pcbnew.F_Cu) else "#a6a")
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, color=col, alpha=0.7))
    x, y = W(fp.GetPosition())
    ax.text(x, y, fp.GetReference(), fontsize=6, ha="center")
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        x, y = W(t.GetPosition())
        ax.add_patch(plt.Circle((x, y), 0.25, color="k"))
    else:
        (x0, y0), (x1, y1) = W(t.GetStart()), W(t.GetEnd())
        ax.plot([x0, x1], [y0, y1], color="#e55" if t.GetLayer() == pcbnew.F_Cu else "#58f", lw=pcbnew.ToMM(t.GetWidth()) * 7, solid_capstyle="round", alpha=0.8)
ax.set_aspect("equal")
ax.set_xlim(-38, 38)
ax.set_ylim(-38, -9)
plt.tight_layout()
plt.savefig(sys.argv[2], dpi=110)
