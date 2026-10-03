"""Draws Iris Ring's assembly map, img/iris_ring_map.svg, from the routed board.

    ./run.sh --board boards/iris_ring --no-media          # writes build/iris_ring/iris_ring.kicad_pcb
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
        boards/iris_ring/draw_map.py                      # KiCad's Python: it reads the board with pcbnew

Two panels: the front (LED face, as a person in front of the robot sees the right eye) with each LED's
place in the data chain, and the back (camera side, drawn mirrored as you hold it) with the four wire
pads labelled by net. Everything drawn is read from the board file: the outline, pads, tracks, vias and
references. The silkscreen has no room for the wire-pad names, so this map is where they live.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PCB = os.path.join(ROOT, "build", "iris_ring", "iris_ring.kicad_pcb")
OUT = os.path.join(HERE, "img", "iris_ring_map.svg")
S = 26.0                       # px per mm
PANEL = 25.0                   # mm per panel, board centred
COL = {"5V_LED": "#c62828", "GND": "#7a7a7a", "LED_DIN": "#1565c0"}
NAMES = {"P1": "P1  5V_LED", "P2": "P2  LED_DIN", "P3": "P3  GND", "P4": "P4  GND"}


def mm(v):
    return pcbnew.ToMM(v)


def colour(net):
    if net in COL:
        return COL[net]
    if net.startswith("DIN"):
        return "#1565c0"
    return "#b0b0b0"


def main():
    b = pcbnew.LoadBoard(PCB)
    bb = b.GetBoardEdgesBoundingBox()
    cx, cy = mm(bb.GetX()) + 9.0, mm(bb.GetY()) + 9.0     # the ring centre: the outline's circle is 18 mm

    def edge_paths(mirror):
        paths = []
        for d in b.GetDrawings():
            if d.GetLayer() != pcbnew.Edge_Cuts:
                continue
            st = d.GetShape()
            if st == pcbnew.SHAPE_T_CIRCLE:
                c, r = d.GetCenter(), mm(d.GetRadius())
                pts = [(mm(c.x) + r * math.cos(2 * math.pi * k / 96), mm(c.y) + r * math.sin(2 * math.pi * k / 96))
                       for k in range(97)]
            elif st == pcbnew.SHAPE_T_ARC:
                c, r = d.GetCenter(), mm(d.GetRadius())
                a0 = math.atan2(mm(d.GetStart().y) - mm(c.y), mm(d.GetStart().x) - mm(c.x))
                am = math.atan2(mm(d.GetArcMid().y) - mm(c.y), mm(d.GetArcMid().x) - mm(c.x))
                a1 = math.atan2(mm(d.GetEnd().y) - mm(c.y), mm(d.GetEnd().x) - mm(c.x))
                span = (a1 - a0) % (2 * math.pi)
                if not ((am - a0) % (2 * math.pi) < span):
                    span -= 2 * math.pi
                pts = [(mm(c.x) + r * math.cos(a0 + span * k / 48), mm(c.y) + r * math.sin(a0 + span * k / 48))
                       for k in range(49)]
            else:
                pts = [(mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))]
            paths.append([P(x, y, mirror) for x, y in pts])
        return paths

    def P(x, y, mirror):
        dx = -(x - cx) if mirror else (x - cx)
        return (dx, y - cy)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
           'font-family="Helvetica, Arial, sans-serif">' % ((2 * PANEL + 1.5) * S, (PANEL + 1.5) * S,
                                                             (2 * PANEL + 1.5) * S, (PANEL + 1.5) * S),
           '<rect width="100%" height="100%" fill="white"/>']
    for panel, (side, mirror, title) in enumerate(((pcbnew.F_Cu, False, "FRONT: LED face, toward the iris"),
                                                   (pcbnew.B_Cu, True, "BACK: camera side, as you hold it"))):
        ox, oy = panel * PANEL * S + PANEL * S / 2.0, (PANEL / 2.0 + 0.9) * S

        def X(p):
            return "%.1f,%.1f" % (ox + p[0] * S, oy + p[1] * S)

        out.append('<text x="%.1f" y="%.1f" font-size="22" font-weight="bold" text-anchor="middle">%s</text>'
                   % (ox, 1.2 * S, title))
        paths = edge_paths(mirror)
        # board body: the outer outline filled, the hole on top in white
        outer = [p for p in paths if max(math.hypot(*q) for q in p) > 5.0]
        hole = [p for p in paths if max(math.hypot(*q) for q in p) <= 5.0]
        ring = []
        for p in outer:
            ring += p
        ring.sort(key=lambda q: math.atan2(q[1], q[0]))
        out.append('<polygon points="%s" fill="#f1ede0" stroke="#555" stroke-width="2"/>' % " ".join(X(q) for q in ring))
        for p in hole:
            out.append('<polygon points="%s" fill="white" stroke="#555" stroke-width="2"/>' % " ".join(X(q) for q in p))
        if side == pcbnew.B_Cu:
            sq = [(-4.35, -4.35), (4.35, -4.35), (4.35, 4.35), (-4.35, 4.35)]
            out.append('<polygon points="%s" fill="none" stroke="#9c27b0" stroke-width="1.5" stroke-dasharray="6,4"/>'
                       % " ".join(X(q) for q in sq))
            out.append('<text x="%.1f" y="%.1f" font-size="13" fill="#9c27b0" text-anchor="middle">camera-holder</text>'
                       % (ox, oy - 0.2 * S))
            out.append('<text x="%.1f" y="%.1f" font-size="13" fill="#9c27b0" text-anchor="middle">square: no parts</text>'
                       % (ox, oy + 0.55 * S))
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA" or t.GetLayer() != side or t.GetNetname() == "GND":
                continue
            a = P(mm(t.GetStart().x), mm(t.GetStart().y), mirror)
            e = P(mm(t.GetEnd().x), mm(t.GetEnd().y), mirror)
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" '
                       'stroke-linecap="round" opacity="0.75"/>' % (ox + a[0] * S, oy + a[1] * S, ox + e[0] * S,
                                                                    oy + e[1] * S, colour(t.GetNetname()),
                                                                    mm(t.GetWidth()) * S))
        for fp in b.GetFootprints():
            if (fp.IsFlipped()) != (side == pcbnew.B_Cu):
                continue
            for pad in fp.Pads():
                bx = pad.GetBoundingBox()
                x0, y0 = P(mm(bx.GetX()), mm(bx.GetY()), mirror)
                x1, y1 = P(mm(bx.GetRight()), mm(bx.GetBottom()), mirror)
                x0, x1 = min(x0, x1), max(x0, x1)
                rx = (x1 - x0) * S / 2.0 if pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE else 1.5
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="%s" stroke="#222" '
                           'stroke-width="0.8"/>' % (ox + x0 * S, oy + y0 * S, (x1 - x0) * S, (y1 - y0) * S, rx,
                                                     colour(pad.GetNetname())))
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                q = P(mm(t.GetPosition().x), mm(t.GetPosition().y), mirror)
                out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="white" stroke="%s" stroke-width="2.5"/>'
                           % (ox + q[0] * S, oy + q[1] * S, mm(t.GetWidth(pcbnew.F_Cu)) / 2 * S, colour(t.GetNetname())))
        for fp in b.GetFootprints():
            ref = fp.GetReference()
            if (fp.IsFlipped()) != (side == pcbnew.B_Cu):
                continue
            q = P(mm(fp.GetPosition().x), mm(fp.GetPosition().y), mirror)
            if ref.startswith("D"):
                out.append('<text x="%.1f" y="%.1f" font-size="17" font-weight="bold" text-anchor="middle" '
                           'fill="#111">%s</text>' % (ox + q[0] * S, oy + q[1] * S + 6, ref[1:]))
            elif ref in NAMES:
                r = math.hypot(*q)
                lx, ly = q[0] / r * 9.6, q[1] / r * 9.6
                anchor = "end" if lx < 0 else "start"
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#333" stroke-width="1"/>'
                           % (ox + q[0] * S, oy + q[1] * S, ox + lx * S, oy + ly * S))
                out.append('<text x="%.1f" y="%.1f" font-size="15" font-weight="bold" text-anchor="%s">%s</text>'
                           % (ox + (lx + (-0.2 if lx < 0 else 0.2)) * S, oy + ly * S + 5, anchor, NAMES[ref]))
            else:
                r = math.hypot(*q)
                lx, ly = q[0] * (1 - 1.05 / r), q[1] * (1 - 1.05 / r)   # 1.05 mm toward the centre, off the pads
                out.append('<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle" fill="#333">%s</text>'
                           % (ox + lx * S, oy + ly * S + 4, ref))
        if side == pcbnew.F_Cu:
            # the data direction: arrows just outside the rim from each LED to the next
            leds = {}
            for fp in b.GetFootprints():
                if fp.GetReference().startswith("D"):
                    q = P(mm(fp.GetPosition().x), mm(fp.GetPosition().y), mirror)
                    leds[int(fp.GetReference()[1:])] = math.atan2(q[1], q[0])
            for k in range(1, 12):
                a0, a1 = leds[k] + 0.12, leds[k + 1] - 0.12
                if a1 < a0:
                    a1 += 2 * math.pi
                r = 9.9
                pts = [(r * math.cos(a0 + (a1 - a0) * i / 12), r * math.sin(a0 + (a1 - a0) * i / 12)) for i in range(13)]
                out.append('<polyline points="%s" fill="none" stroke="#1565c0" stroke-width="2.2"/>'
                           % " ".join(X(p) for p in pts))
                tip, back = pts[-1], pts[-3]
                ang = math.atan2(tip[1] - back[1], tip[0] - back[0])
                h = [tip, (tip[0] - 0.45 * math.cos(ang - 0.45), tip[1] - 0.45 * math.sin(ang - 0.45)),
                     (tip[0] - 0.45 * math.cos(ang + 0.45), tip[1] - 0.45 * math.sin(ang + 0.45))]
                out.append('<polygon points="%s" fill="#1565c0"/>' % " ".join(X(p) for p in h))
            out.append('<text x="%.1f" y="%.1f" font-size="14" text-anchor="middle" fill="#1565c0">data in at 1 '
                       '(from P2 through R1), clockwise to 12</text>' % (ox, oy + 11.2 * S))
            out.append('<text x="%.1f" y="%.1f" font-size="13" text-anchor="middle" fill="#444">temporal</text>'
                       % (ox - 11.0 * S, oy - 0.2 * S))
            out.append('<text x="%.1f" y="%.1f" font-size="13" text-anchor="middle" fill="#444">(right eye)</text>'
                       % (ox - 11.0 * S, oy + 0.55 * S))
        else:
            out.append('<text x="%.1f" y="%.1f" font-size="13" text-anchor="end" fill="#444">temporal side '
                       '(right eye)</text>' % (ox + 12.2 * S, oy - 8.6 * S))
        out.append('<text x="%.1f" y="%.1f" font-size="13" text-anchor="middle" fill="#444">key flat</text>'
                   % (ox, oy + 9.3 * S))
    out.append('<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle" fill="#666">pads and tracks read from '
               'build/iris_ring/iris_ring.kicad_pcb; red 5V_LED, grey GND (tracks hidden, poured), blue data</text>'
               % (PANEL * S, (PANEL + 1.1) * S))
    out.append("</svg>")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT + ".tmp", "w") as f:
        f.write("\n".join(out) + "\n")
    os.replace(OUT + ".tmp", OUT)
    sys.stdout.write("wrote %s\n" % OUT)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
