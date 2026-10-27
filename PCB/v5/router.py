"""Small 2-layer grid router for the v5 board (runs inside the KiCad container: pcbnew + numpy + matplotlib).

* 0.05 mm grid, both copper layers, 8 directions (45 deg tracks), vias between the layers
* every obstacle is grown by clearance + half the track (or via) width, so the centreline of a free cell is legal
* nets are connected pad by pad into a tree
* negotiated congestion (PathFinder): pads are walls, other nets' tracks only a cost that rises every iteration,
  plus a history cost on cells that were fought over; nets that still overlap are rerouted until none do
* KiCad's own DRC checks the result afterwards (make_board.py finish)
"""

import heapq
import math

import numpy as np
import pcbnew
from matplotlib.path import Path as MplPath

import layout
import netlist

G = 0.05                 # grid, mm
CLEAR = 0.17             # copper clearance (board rule 0.15; the 0.05 mm grid loses up to ~0.01)
EDGE = 0.38              # copper to board edge (rule 0.3)
HOLE_CLEAR = 0.27        # hole to copper (rule 0.25)
VIA_D, VIA_DRILL = 0.5, 0.3
VIA_COST = 30            # in grid steps (1.5 mm)
BOTTOM_PENALTY = 1.6     # keep the bottom layer mostly for the ground plane
ITERATIONS = 80
PRES_START, PRES_GROWTH = 1.0, 1.5     # cost of a cell another net uses, per grid step
HIST_STEP = 1.0                        # added to a cell's cost every iteration it is overused
DEFAULT_W = 0.2


def mm(v):
    return pcbnew.FromMM(v)


class Grid:
    def __init__(self, board):
        self.board = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = pcbnew.ToMM(bb.GetLeft()) - 1.0, pcbnew.ToMM(bb.GetTop()) - 1.0
        self.nx = int((pcbnew.ToMM(bb.GetWidth()) + 2.0) / G) + 1
        self.ny = int((pcbnew.ToMM(bb.GetHeight()) + 2.0) / G) + 1
        xs = self.x0 + np.arange(self.nx) * G
        ys = self.y0 + np.arange(self.ny) * G
        self.X, self.Y = np.meshgrid(xs, ys, indexing="xy")      # shape (ny, nx)
        self.pts = np.column_stack([self.X.ravel(), self.Y.ravel()])
        self.net_ids = {"": 0}
        self.copper = np.zeros((2, self.ny, self.nx), dtype=np.int16)   # net id of the copper in each cell
        self.outside = self._outline_mask()
        self.keepout = self._keepout_mask()
        self.pad_cells = {}

    def nid(self, name):
        return self.net_ids.setdefault(name, len(self.net_ids))

    def cell(self, x, y):
        return int(round((y - self.y0) / G)), int(round((x - self.x0) / G))

    def xy(self, r, c):
        return self.x0 + c * G, self.y0 + r * G

    def _outline_mask(self):
        # KiCad doesn't keep the Edge.Cuts segments in order: use the outline from layout.py
        pts = [(100.0 + x, 100.0 - y) for x, y in layout.outline()]
        path = MplPath(pts + [pts[0]])
        return ~path.contains_points(self.pts).reshape(self.ny, self.nx)

    def _keepout_mask(self):
        mask = np.zeros((self.ny, self.nx), dtype=bool)
        for fp in self.board.GetFootprints():
            for z in fp.Zones():
                if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                    poly = z.Outline().Outline(0)
                    pts = [(pcbnew.ToMM(poly.CPoint(i).x), pcbnew.ToMM(poly.CPoint(i).y)) for i in range(poly.PointCount())]
                    mask |= MplPath(pts + [pts[0]]).contains_points(self.pts).reshape(self.ny, self.nx)
        return mask

    def add_pads(self):
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                net = pad.GetNetname()
                poly = pad.GetEffectivePolygon(pcbnew.ERROR_INSIDE)
                bb = pad.GetBoundingBox()
                r0, c0 = self.cell(pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()))
                r1, c1 = self.cell(pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
                cells = []
                for r in range(max(r0 - 1, 0), min(r1 + 2, self.ny)):
                    for c in range(max(c0 - 1, 0), min(c1 + 2, self.nx)):
                        x, y = self.xy(r, c)
                        if poly.Contains(pcbnew.VECTOR2I(mm(x), mm(y))):
                            cells.append((r, c))
                if not cells:
                    cells = [self.cell(pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y))]
                layers = [i for i, l in enumerate((pcbnew.F_Cu, pcbnew.B_Cu)) if pad.IsOnLayer(l)]
                n = self.nid(net) if net else -1        # pads without a net are obstacles for everyone
                for layer in layers:
                    for r, c in cells:
                        self.copper[layer, r, c] = n
                if net:
                    self.pad_cells.setdefault(net, []).append((layers, cells, pad))
            # holes (NPTH and THT) block both layers
            for pad in fp.Pads():
                if pad.GetDrillSize().x > 0 and not pad.GetNetname():
                    x, y = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
                    # stamped bigger by the difference, so the copper clearance around it becomes the hole clearance
                    self.stamp_disk(-1, x, y, pcbnew.ToMM(pad.GetDrillSize().x) / 2 + HOLE_CLEAR - CLEAR, (0, 1))

    def stamp_disk(self, n, x, y, radius, layers):
        r0, c0 = self.cell(x, y)
        k = int(math.ceil(radius / G))
        for dr in range(-k, k + 1):
            for dc in range(-k, k + 1):
                if (dr * G) ** 2 + (dc * G) ** 2 <= radius ** 2 + 1e-9:
                    r, c = r0 + dr, c0 + dc
                    if 0 <= r < self.ny and 0 <= c < self.nx:
                        for layer in layers:
                            if self.copper[layer, r, c] == 0:
                                self.copper[layer, r, c] = n


def dilate(mask, radius):
    k = int(math.ceil(radius / G))
    ny, nx = mask.shape
    out = mask.copy()
    for dr in range(-k, k + 1):
        for dc in range(-k, k + 1):
            if (dr * G) ** 2 + (dc * G) ** 2 > radius ** 2 + 1e-9:
                continue
            shifted = np.zeros_like(mask)
            rs = slice(max(0, dr), ny + min(0, dr))
            rd = slice(max(0, -dr), ny + min(0, -dr))
            cs = slice(max(0, dc), nx + min(0, dc))
            cd = slice(max(0, -dc), nx + min(0, -dc))
            shifted[rs, cs] = mask[rd, cd]
            out |= shifted
    return out


DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]


def astar(blocked, via_blocked, starts, goal_mask, goal_xy, ny, nx, penalty=None, via_penalty=None):
    """starts: [(layer, r, c)], goal_mask: bool (2, ny, nx), penalty: extra cost per cell (2, ny, nx) or None,
    via_penalty: extra cost of a via per cell (ny, nx) or None. Returns the path as [(layer, r, c)]."""
    gr, gc = goal_xy
    INF = 1e18
    cost = np.full((2, ny, nx), INF, dtype=np.float64)
    prev = {}
    heap = []
    for s in starts:
        cost[s] = 0.0
        heapq.heappush(heap, (math.hypot(s[1] - gr, s[2] - gc), 0.0, s))
    while heap:
        f, g, (l, r, c) = heapq.heappop(heap)
        if g > cost[l, r, c]:
            continue
        if goal_mask[l, r, c]:
            path = [(l, r, c)]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            return path[::-1]
        for dr, dc, w in DIRS:
            if l == 1:
                w *= BOTTOM_PENALTY
            rr, cc = r + dr, c + dc
            if not (0 <= rr < ny and 0 <= cc < nx) or blocked[l, rr, cc]:
                continue
            if dr and dc and (blocked[l, r, cc] or blocked[l, rr, c]):   # no squeezing through diagonal gaps
                continue
            ng = g + w
            if penalty is not None:
                ng += penalty[l, rr, cc]
            if ng < cost[l, rr, cc]:
                cost[l, rr, cc] = ng
                prev[(l, rr, cc)] = (l, r, c)
                heapq.heappush(heap, (ng + math.hypot(rr - gr, cc - gc), ng, (l, rr, cc)))
        ol = 1 - l
        if not via_blocked[r, c] and not blocked[ol, r, c]:
            ng = g + VIA_COST
            if via_penalty is not None:
                ng += via_penalty[r, c]
            if ng < cost[ol, r, c]:
                cost[ol, r, c] = ng
                prev[(ol, r, c)] = (l, r, c)
                heapq.heappush(heap, (ng + math.hypot(r - gr, c - gc), ng, (ol, r, c)))
    return None


def simplify(path):
    out = [path[0]]
    for i in range(1, len(path) - 1):
        a, b, c = out[-1], path[i], path[i + 1]
        if a[0] != b[0] or b[0] != c[0]:
            out.append(b)
            continue
        d1 = (b[1] - a[1], b[2] - a[2])
        d2 = (c[1] - b[1], c[2] - b[2])
        if d1[0] * d2[1] - d1[1] * d2[0] != 0:
            out.append(b)
    out.append(path[-1])
    return out


def walls(grid, net, width):
    """Hard obstacles for this net: other nets' pads, the board edge, keep-outs (cached, they never change)."""
    key = (net, width)
    if key not in grid.walls:
        n = grid.nid(net)
        hw = width / 2
        # pads are rasterised at the grid points inside them, so their real edge can be up to one cell further out
        other = [dilate((grid.pads[l] != 0) & (grid.pads[l] != n), G) for l in (0, 1)]
        edge = dilate(grid.outside, EDGE + hw)
        keepout = dilate(grid.keepout, hw + G)
        blocked = np.stack([dilate(other[l], CLEAR + hw) | edge | keepout for l in (0, 1)])
        via_blocked = (dilate(other[0] | other[1], CLEAR + VIA_D / 2) | dilate(grid.outside, EDGE + VIA_D / 2)
                       | dilate(grid.keepout, VIA_D / 2 + G))
        grid.walls[key] = (blocked, via_blocked)
    return grid.walls[key]


def route_net(grid, net, width, items, used, hist, pres, unreached=None):
    """used: (2, ny, nx) cells other nets' tracks claim; hist: history cost per cell.
    unreached: if a list, pads that can't be reached are collected there instead of failing the net."""
    hw = width / 2
    blocked, via_blocked = walls(grid, net, width)
    blocked = blocked.copy()
    near = np.stack([dilate(used[l], hw + CLEAR / 2) for l in (0, 1)])
    penalty = hist + near * (pres * (1.0 + hist))
    via_near = dilate(used[0] | used[1], VIA_D / 2 + CLEAR / 2)
    via_penalty = hist[0] + hist[1] + via_near * (pres * VIA_D / G)
    pads = grid.pad_cells[net]
    tree = np.zeros((2, grid.ny, grid.nx), dtype=bool)
    layers0, cells0, _ = pads[0]
    for l in layers0:
        for r, c in cells0:
            tree[l, r, c] = True
    remaining = list(pads[1:])
    while remaining:
        # connect the pad closest to the tree
        tr = np.argwhere(tree)
        def dist(p):
            r, c = p[1][len(p[1]) // 2]
            return np.min(np.hypot(tr[:, 1] - r, tr[:, 2] - c))
        remaining.sort(key=dist)
        layers, cells, pad = remaining.pop(0)
        if any(tree[l, r, c] for l in layers for r, c in cells):
            continue
        r, c = cells[len(cells) // 2]
        starts = [(l, r, c) for l in layers]
        for s in starts:                       # own pad cells are always enterable
            blocked[s] = False
        ti = np.argmin(np.hypot(tr[:, 1] - r, tr[:, 2] - c))
        path = astar(blocked, via_blocked, starts, tree, (tr[ti, 1], tr[ti, 2]), grid.ny, grid.nx, penalty, via_penalty)
        if path is None:
            if unreached is None:
                return False
            unreached.append(f"{pad.GetParentFootprint().GetReference()}.{pad.GetNumber()}")
            continue
        for l, rr, cc in path:
            tree[l, rr, cc] = True
        for l in layers:
            for pr, pc in cells:
                tree[l, pr, pc] = True
        items.append(path)
    return True


def claim(grid, paths, width):
    """Cells this net's copper claims: track + half the clearance (two claims may not overlap)."""
    centre = np.zeros((2, grid.ny, grid.nx), dtype=bool)
    vias = np.zeros((grid.ny, grid.nx), dtype=bool)
    for path in paths:
        for i, (l, r, c) in enumerate(path):
            centre[l, r, c] = True
            if i > 0 and path[i - 1][0] != l:
                vias[r, c] = True
    out = np.stack([dilate(centre[l], width / 2 + CLEAR / 2) for l in (0, 1)])
    if vias.any():
        v = dilate(vias, VIA_D / 2 + CLEAR / 2)
        out[0] |= v
        out[1] |= v
    return out


def commit(board, grid, net, width, paths):
    ni = board.FindNet(net)
    for path in paths:
        pts = simplify(path)
        for a, b in zip(pts, pts[1:]):
            ax, ay = grid.xy(a[1], a[2])
            bx, by = grid.xy(b[1], b[2])
            if a[0] != b[0]:
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(pcbnew.VECTOR2I(mm(bx), mm(by)))
                via.SetWidth(mm(VIA_D))
                via.SetDrill(mm(VIA_DRILL))
                via.SetNet(ni)
                board.Add(via)
                continue
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(mm(ax), mm(ay)))
            t.SetEnd(pcbnew.VECTOR2I(mm(bx), mm(by)))
            t.SetWidth(mm(width))
            t.SetLayer(pcbnew.F_Cu if a[0] == 0 else pcbnew.B_Cu)
            t.SetNet(ni)
            board.Add(t)


def ground_fanout(grid, board):
    """A short track + via from every top-side ground pad down to the bottom ground plane."""
    n = grid.nid("GND")
    hw = 0.15
    other = [dilate((grid.copper[l] != 0) & (grid.copper[l] != n), G) for l in (0, 1)]   # pad edges, as in walls()
    edge = dilate(grid.outside, EDGE + hw)
    blocked = np.stack([dilate(other[l], CLEAR + hw) | edge | dilate(grid.keepout, hw + G) for l in (0, 1)])
    via_ok = ~(dilate(other[0] | other[1], CLEAR + VIA_D / 2) | dilate(grid.outside, EDGE + VIA_D / 2)
               | dilate(grid.keepout, VIA_D / 2 + G))
    # only places where the bottom layer is free (it becomes the plane) and nothing else is near
    goal = np.zeros((2, grid.ny, grid.nx), dtype=bool)
    goal[0] = via_ok & ~dilate(grid.copper[1] != 0, CLEAR + VIA_D / 2)
    ni = board.FindNet("GND")
    added = 0
    for layers, cells, pad in grid.pad_cells.get("GND", []):
        if layers != [0]:
            continue                                   # bottom and through-hole pads touch the plane already
        r, c = cells[len(cells) // 2]
        blocked[0, r, c] = False
        path = astar(blocked, np.ones((grid.ny, grid.nx), dtype=bool), [(0, r, c)], goal, (r, c), grid.ny, grid.nx)
        if path is None or len(path) > 120:
            continue
        end = path[-1]
        commit(board, grid, "GND", 0.3, [path])
        x, y = grid.xy(end[1], end[2])
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        via.SetWidth(mm(VIA_D))
        via.SetDrill(mm(VIA_DRILL))
        via.SetNet(ni)
        board.Add(via)
        grid.stamp_disk(n, x, y, VIA_D / 2, (0, 1))
        rr, cc = end[1], end[2]
        k = int((VIA_D + CLEAR) / G) + 1
        goal[0, max(0, rr - k):rr + k + 1, max(0, cc - k):cc + k + 1] = False
        added += 1
    # stitching vias on a 2.5 mm lattice wherever both layers are free: they tie the top and bottom pours together
    free = via_ok & ~dilate((grid.copper[0] != 0) | (grid.copper[1] != 0), CLEAR + VIA_D / 2)
    step = int(2.5 / G)
    for r in range(0, grid.ny, step):
        for c in range(0, grid.nx, step):
            if free[r, c]:
                x, y = grid.xy(r, c)
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
                via.SetWidth(mm(VIA_D))
                via.SetDrill(mm(VIA_DRILL))
                via.SetNet(ni)
                board.Add(via)
                grid.stamp_disk(n, x, y, VIA_D / 2, (0, 1))
                added += 1
    return added


def route(pcb_path):
    board = pcbnew.LoadBoard(str(pcb_path))
    # removing tracks and zones from a loaded board crashes KiCad 9's Python bindings: start from a fresh placement
    if len(board.GetTracks()) or len(board.Zones()):
        raise SystemExit("the board is already routed: run `make_board.py place` first")
    nets = netlist.nets()
    grid = Grid(board)
    grid.add_pads()
    grid.pads = grid.copper.copy()
    grid.walls = {}
    # ground goes last and is routed like any other net, so it doesn't depend on the pours being in one piece
    order = [n for n in sorted(nets, key=lambda n: (n == "GND", len(nets[n])))
             if len(grid.pad_cells.get(n, [])) >= 2]
    count = np.zeros((2, grid.ny, grid.nx), dtype=np.int16)
    hist = np.zeros((2, grid.ny, grid.nx), dtype=np.float32)
    routes, failed = {}, []
    queue, pres = list(order), PRES_START
    for it in range(ITERATIONS):
        for net in queue:
            if net in routes:
                count -= routes.pop(net)[2]
            used = count > 0
            for width in dict.fromkeys((netlist.WIDE.get(net, DEFAULT_W), DEFAULT_W)):
                paths = []
                # ground may leave a pad for the pours and the fanout vias; everything else must be complete
                unreached = [] if net == "GND" and width == DEFAULT_W else None
                if route_net(grid, net, width, paths, used, hist, pres, unreached):
                    if unreached:
                        print(f"  GND pads left to the pours: {unreached}")
                    c = claim(grid, paths, width)
                    count += c
                    routes[net] = (width, paths, c)
                    break
            else:
                failed.append(net)            # walled in by pads: no cost makes this one routable
        over = count >= 2
        queue = [n for n in order if n in routes and (routes[n][2] & over).any()]
        print(f"iteration {it + 1}: {int(over.sum())} overused cells, {len(queue)} nets in conflict", flush=True)
        if not queue:
            break
        hist[over] += HIST_STEP
        pres *= PRES_GROWTH
    failed = sorted(set(failed) | set(queue))
    print(f"routed {len(routes) - len(queue)} of {len(order)} nets, failed {failed}")
    for net in failed:
        routes.pop(net, None)
    for net, (width, paths, c) in routes.items():
        commit(board, grid, net, width, paths)
        grid.copper[c & (grid.copper == 0)] = grid.nid(net)
    vias = ground_fanout(grid, board)
    print(f"ground: {vias} vias to the bottom plane")
    pcbnew.SaveBoard(str(pcb_path), board)
    return failed
