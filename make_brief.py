"""Writes boards/iris_ring/board.json: Iris Ring's outline and every part lock, computed from angles.

    python3 boards/iris_ring/make_brief.py          # any Python 3.9+, standard library only

Edit this file, not board.json: the twelve LEDs, their capacitors and the wire pads are placed by
formula, so the ring stays exactly symmetric, and the checks below run on every edit.

Frame: the brief's 18 x 18 mm frame, origin top-left, y down (KiCad's), ring centre (9, 9). An angle
phi is measured from +x toward +y, so it grows clockwise on the F face (the face a person in front of
the robot sees, LEDs toward the iris). The key flat is the chord y = 17.4 (8.4 mm below the centre).

What the checks prove before the pipeline runs (they raise on a failure):
  * no two courtyards on one face overlap (every part is turned by a quarter turn, so a courtyard is an
    axis-aligned box; KiCad DRC's courtyards_overlap is an error);
  * no B-face courtyard enters the 8.7 x 8.7 mm camera-holder square (spec section 4.4);
  * every pad keeps the 0.3 mm edge clearance from the outline, the flat and the centre hole.
The pipeline measures all of it again (DRC); these checks only stop a bad brief early.

Spec: Iris design spec v0.1 (not published) section 4.4 (outline, parts, heights, keepout), section 5 (RING pads).
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
W = H = 18.0
CX, CY = 9.0, 9.0
R_OUT, FLAT, R_HOLE = 9.0, 8.4, 3.8          # spec 4.4: Ø18.0, flat 8.4 mm from the centre, Ø7.6 hole
EDGE = 0.3                                    # copper-to-edge clearance (board.rules.edge_clearance)
R_LED = 6.6                                   # spec 4.4: LED centres on r = 6.6 at 15 deg + 30 deg k
PHI0 = 195.0                                  # D1: the first LED clockwise after the wire pads (180 deg)
SQUARE = (4.65, 4.65, 13.35, 13.35)           # B-face camera-holder contact square, 8.7 x 8.7 (spec 4.4)

# footprint facts (KiCad 10.0.6 libraries, read from the .kicad_mod files)
LED_PADS = {"1": (-0.915, -0.55), "2": (-0.915, 0.55), "3": (0.915, 0.55), "4": (0.915, -0.55)}
LED_PAD, LED_CRT = (0.7, 0.7), (1.52, 1.25)   # LED_WS2812B-2020_PLCC4_2.0x2.0mm: pad size, courtyard half-sizes
C_PADS, C_PAD, C_CRT = {"1": (-0.48, 0.0), "2": (0.48, 0.0)}, (0.56, 0.62), (0.91, 0.46)   # C_0402_1005Metric
R_PADS, R_PAD, R_CRT = {"1": (-0.51, 0.0), "2": (0.51, 0.0)}, (0.54, 0.64), (0.93, 0.47)   # R_0402_1005Metric
TP_D, TP_CRT_R = 1.0, 1.0                     # TestPoint_Pad_D1.0mm: Ø1.0 pad, Ø2.0 courtyard circle

R_PAD_ARC, TP_PITCH = 7.6, 2.1               # wire pads: r = 7.6, 2.1 mm apart (Ø2.0 courtyards must not touch)
R_CAP_IN, R_CAP_DIAG = 5.0, 7.4                # capacitor centres: inner ones 5.0 mm out on their axis
TITLE_WINDOW = (5.4, 14.6, 12.6, 16.7)       # back-face title spot between C9/C10 and the flat, kept via-free


def rot_pt(x, y, rot):
    """KiCad's RotatePoint in a y-down frame (place.py _rot_pt): positive turns counter-clockwise on screen."""
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[rot % 360]


def polar(r, phi):
    return (CX + r * math.cos(math.radians(phi)), CY + r * math.sin(math.radians(phi)))


def led_phi(k):
    return (PHI0 + 30.0 * (k - 1)) % 360.0


def led_rot(k):
    """Quarter turn for LED k. The SDK takes only 0/90/180/270 (place.py _rot_pt), so each LED is turned to the
    axis nearest its radius, with pads 1-2 (DOUT, GND) outward and pads 3-4 (DIN, VDD) inward, and DOUT on the
    clockwise side: data then hops from the outer DOUT of one LED to the inner DIN of the next, VDD faces the
    hole and GND the rim. A diagonal LED (45 deg off both axes) takes its clockwise neighbour's turn: DOUT to DIN
    is then 2.56 and 1.86 mm pad centre to pad centre, against 4.00 and 3.33 mm with its other neighbour's turn."""
    phi = led_phi(k)
    axis = (round(phi / 90.0) * 90.0) % 360.0
    if abs(((phi - 45.0) % 90.0)) < 1e-9:
        axis = (phi + 45.0) % 360.0
    return int((180.0 - axis) % 360.0)


def flipped(pads):
    """Pad offsets of a bottom-face footprint at orientation 0. place.py flips it with FLIP_DIRECTION_LEFT_RIGHT and
    then sets orientation 0; KiCad's flip mirrors y and turns the part 180 deg, so undoing the turn leaves the pads
    mirrored in y (measured on this board's first build: a back 0402 at rot 0 keeps pad 1 on -x)."""
    return {n: (x, -y) for n, (x, y) in pads.items()}


def pad1_rot(direction):
    """Quarter turn that points pad 1 of a two-pad 0402 (pad 1 at -x) along `direction` (deg, y down), either face."""
    return int((180.0 - direction) % 360.0)


class Part(object):
    def __init__(self, key, ref, xy, rot, side, pads, pad_size, crt, why, round_crt=None):
        self.key, self.ref, self.xy, self.rot, self.side, self.why = key, ref, xy, rot, side, why
        local = flipped(pads) if side == "bottom" else pads
        self.pads = {}
        for n, (px, py) in local.items():
            dx, dy = rot_pt(px, py, rot)
            sw, sh = pad_size if rot % 180 == 0 else (pad_size[1], pad_size[0])
            self.pads[n] = (xy[0] + dx, xy[1] + dy, sw / 2.0, sh / 2.0)
        if round_crt:
            self.box = (xy[0] - round_crt, xy[1] - round_crt, xy[0] + round_crt, xy[1] + round_crt)
        else:
            hx, hy = crt if rot % 180 == 0 else (crt[1], crt[0])
            self.box = (xy[0] - hx, xy[1] - hy, xy[0] + hx, xy[1] + hy)
        self.round_crt = round_crt


def plan():
    parts = []
    for k in range(1, 13):
        phi, rot = led_phi(k), led_rot(k)
        xy = polar(R_LED, phi)
        parts.append(Part("px%d:D?" % k, "D%d" % k, xy, rot, "top", LED_PADS, LED_PAD, LED_CRT,
                          "LED %d of 12 at phi %.0f deg on r = 6.6 mm (spec 4.4: 15 deg + 30 deg k); quarter turn %d "
                          "puts DOUT and GND outward, DIN and VDD inward, DOUT clockwise" % (k, phi, rot)))
    for k in range(1, 13):
        phi = led_phi(k)
        if abs(((phi - 45.0) % 90.0)) < 1e-9:
            xy = polar(R_CAP_DIAG, phi)
            rot = pad1_rot(0.0 if xy[0] < CX else 180.0)   # tangential to the square's corner, pad 1 inward
            why = ("D%d's 100 nF on the back behind its LED, r = 7.4 mm: the camera-holder square's corner reaches "
                   "r = 6.15 on the diagonal, so this one cannot sit inside the LED circle" % k)
        else:
            # straight under the LED's inner pads, turned along the ring: the axis the LED faces is u, the ring
            # direction there is v, and the capacitor sits R_CAP_IN out along u at the LED's own v offset
            axis = (round(phi / 90.0) * 90.0) % 360.0
            u = (math.cos(math.radians(axis)), math.sin(math.radians(axis)))
            v = (-u[1], u[0])                          # clockwise ring direction (y down)
            led = (R_LED * math.cos(math.radians(phi)), R_LED * math.sin(math.radians(phi)))
            t = led[0] * v[0] + led[1] * v[1]
            xy = (CX + R_CAP_IN * u[0] + t * v[0], CY + R_CAP_IN * u[1] + t * v[1])
            rot = pad1_rot((axis + 90.0) % 360.0)      # pad 1 (5V_LED) clockwise, under the LED's VDD pad
            why = ("D%d's 100 nF on the back under the LED's inner pads, along the ring: pad 1 (5V_LED) beside its "
                   "VDD pad, pad 2 (GND) beside its DIN pad; %.1f mm out on the LED's axis, clear of the "
                   "camera-holder square and leaving the band above the key flat free" % (k, R_CAP_IN))
        parts.append(Part("px%d:C?" % k, "C%d" % k, xy, rot, "bottom", C_PADS, C_PAD, C_CRT, why))
    # wire pads P1-P4 on an arc at the temporal (-x) side, in harness order from the top
    step = 2.0 * math.degrees(math.asin(TP_PITCH / 2.0 / R_PAD_ARC))
    names = {1: "5V_LED", 2: "LED_DIN", 3: "GND", 4: "GND"}
    for i in range(4):
        phi = 180.0 + 1.5 * step - i * step
        parts.append(Part("in:P%d?" % (i + 1), "P%d" % (i + 1), polar(R_PAD_ARC, phi), 0, "bottom",
                          {"1": (0.0, 0.0)}, (TP_D, TP_D), None,
                          "RING wire pad P%d (%s, spec section 5) on the back at r = 7.6 mm, phi %.1f deg: pads in "
                          "harness order on the temporal side, %.1f mm apart so the stock pads' 2.0 mm courtyards "
                          "do not touch" % (i + 1, names[i + 1], phi, TP_PITCH), round_crt=TP_CRT_R))
    parts.append(Part("in:R?", "R1", (CX - 5.98, CY - 0.05), pad1_rot(270.0), "bottom", R_PADS, R_PAD, R_CRT,
                      "33 ohm DIN series resistor between the wire pads and C1/C12, pad 1 (LED_DIN) up toward P2, "
                      "pad 2 (DIN1) down into the gap between D12 and D1"))
    parts.append(Part("in:C?", "C13", (CX - 5.0, CY - 3.6), pad1_rot(90.0), "bottom", C_PADS, C_PAD, C_CRT,
                      "4.7 uF bulk beside P1 (5V_LED), in line with C1, its pad 1 (5V_LED) facing C1's pad 1"))
    return parts


def _boxes_overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _circle_box(c, r, b):
    nx, ny = min(max(c[0], b[0]), b[2]), min(max(c[1], b[1]), b[3])
    return math.hypot(nx - c[0], ny - c[1]) < r


def check(parts):
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            if a.side != b.side:
                continue
            if a.round_crt and b.round_crt:
                bad = math.hypot(a.xy[0] - b.xy[0], a.xy[1] - b.xy[1]) < a.round_crt + b.round_crt
            elif a.round_crt or b.round_crt:
                c, o = (a, b) if a.round_crt else (b, a)
                bad = _circle_box(c.xy, c.round_crt, o.box)
            else:
                bad = _boxes_overlap(a.box, b.box)
            if bad:
                raise SystemExit("courtyards overlap: %s and %s" % (a.ref, b.ref))
        if a.side == "bottom":
            if (a.round_crt and _circle_box(a.xy, a.round_crt, SQUARE)) or (not a.round_crt and _boxes_overlap(a.box, SQUARE)):
                raise SystemExit("%s enters the camera-holder square" % a.ref)
        for n, (x, y, hx, hy) in a.pads.items():
            for px, py in ((x - hx, y - hy), (x + hx, y - hy), (x + hx, y + hy), (x - hx, y + hy)):
                r = math.hypot(px - CX, py - CY)
                if r > R_OUT - EDGE or py > CY + FLAT - EDGE or r < R_HOLE + EDGE:
                    raise SystemExit("%s pad %s is inside the edge clearance (r %.2f)" % (a.ref, n, r))


def outline():
    """The circle with its key flat, as a polygon whose fillets ARE the circle: each vertex is where two tangents
    of the Ø18 circle meet, so a fillet of r = 9 mm there is an exact arc of the circle (Edge.Cuts gets real
    arcs, no facets), and the flat's ends are sharp corners where it meets the circle."""
    half = math.sqrt(R_OUT ** 2 - FLAT ** 2)
    fr, fl = (CX + half, CY + FLAT), (CX - half, CY + FLAT)
    # tangents at (18, 9) and at fr meet on x = 18 at y = CY + (R^2 - half*R) / FLAT
    yt = CY + (R_OUT ** 2 - half * R_OUT) / FLAT
    pts = [(0.0, 0.0), (W, 0.0), (W, yt), fr, fl, (0.0, yt)]
    return {"type": "polygon", "points": [[round(x, 6), round(y, 6)] for x, y in pts],
            "fillets": [R_OUT, R_OUT, R_OUT, 0.0, 0.0, R_OUT]}


def brief(parts):
    blocks = []
    for k in range(1, 13):
        b = {"block": "irisring_pixel", "as": "px%d" % k, "title": "Pixel %d (phi %.0f deg)" % (k, led_phi(k)),
             "nets": {"VDD": "5V_LED"}, "pinNets": {"D?.3": "DIN%d" % k}}
        if k < 12:
            b["pinNets"]["D?.1"] = "DIN%d" % (k + 1)
        else:
            b["no_connect"] = ["D?.1"]
        blocks.append(b)
    blocks.append({"block": "irisring_wire_in", "as": "in", "title": "RING wire pads, DIN series R, bulk C",
                   "nets": {"VDD": "5V_LED", "LED_DIN": "LED_DIN", "TO_PIXEL": "DIN1"}})
    placement = {}
    for p in parts:
        e = {"lock": [round(p.xy[0], 4), round(p.xy[1], 4)], "from_center": False, "rot": p.rot}
        if p.side == "bottom":
            e["side"] = "bottom"
        e["why"] = p.why
        placement[p.key] = e
    return {
        "name": "iris_ring",
        "title": "Iris Ring - annular WS2812C-2020 LED board behind each iris of Iris (B3, fitted twice)",
        "revision": "A",
        "brief": ("Iris board B3, fitted twice: an 18 mm annulus with a key flat 8.4 mm from the centre and a 7.6 mm "
                  "hole for the camera lens, 0.8 mm thick, 2 layers, that glows behind the translucent iris of each "
                  "eye. Twelve Worldsemi WS2812C-2020-V1 RGB LEDs on r = 6.6 mm at 15 deg + 30 deg k face the iris on "
                  "the front, chained clockwise from the first LED beside the wire pads; each has its own 100 nF on "
                  "the back. The RING harness lands on four 1.0 mm back-side pads at the temporal edge (P1 5V_LED, "
                  "P2 LED_DIN, P3 GND, P4 GND), with a 33 ohm series resistor into the first DIN and 4.7 uF of bulk. "
                  "The back's centre 8.7 mm square rests on the camera holder and carries no parts."),
        "blocks": blocks,
        "pwrFlags": ["5V_LED", "GND"],
        "netClasses": [
            {"name": "LED_PWR", "nets": ["5V_LED"], "track": 0.3, "clearance": 0.15, "via": [0.5, 0.3],
             "currentA": 0.19,
             "why": "the ring's supply: 12 LEDs x 3 channels x 5 mA plus 12 x 0.5 mA quiescent = 186 mA at full "
                    "white (WS2812C-2020-V1 datasheet p.1 and p.3). 0.3 mm still enters the LEDs' 0.7 mm pads; "
                    "the current budget keeps the route ladder from narrowing it"}
        ],
        "board": {
            "width": W, "height": H, "origin": [100.0, 100.0], "layers": 2,
            "shape": outline(),
            "cutouts": [{"type": "circle", "at": [CX, CY], "d": 2 * R_HOLE}],
            "rules": {"clearance": 0.15, "track": 0.2, "via": [0.5, 0.3], "edge_clearance": EDGE,
                      "hole_to_hole": 0.5, "min_through_hole": 0.3, "min_track": 0.15,
                      "why": "0.15 mm clearance and 0.2 mm tracks inside JLC's 2-layer line (0.10 / 0.10 mm, "
                             "jlcpcb_2layer); 0.5 / 0.3 mm vias fit between the LEDs' inner pads (r >= 5.08) and the "
                             "hole's clearance ring (r <= 4.1); every class is 0.2 mm or wider, so 0.15 leaves room "
                             "for Freerouting's rounding",
                      "why_edge": "0.3 mm copper to edge, not the 0.5 mm of the other boards: D9 and D10 reach "
                                  "0.76 mm from the key flat, so at 0.5 mm no ground track passed below them and "
                                  "the router ran GND between the LEDs, leaving DIN11 open (measured on this "
                                  "brief); at 0.3 mm it routes 64 -> 0. Confirm 0.3 mm against the fab's "
                                  "routed-edge rule before ordering"},
            "keepouts": [
                {"name": "camera_holder_contact", "rect": list(SQUARE), "layers": ["B.Cu"], "no": ["footprints"],
                 "why": "spec 4.4: the back's centre 8.7 x 8.7 mm square rests on the 8.5 x 8.5 mm camera holder "
                        "(left eye: the dummy carrier); 0.1 mm margin. Tracks and vias may pass under it"},
                {"name": "name_window", "rect": list(TITLE_WINDOW), "layers": "all", "no": ["vias"],
                 "why": "keeps the back's only free band (between C9/C10 and the key flat) clear of vias for the "
                        "board name; tracks may cross it"}
            ],
            "notes": ("Outline from spec 4.4 (binding): circle 18.0 mm, key flat 8.4 mm from the centre (the chord "
                      "y = 17.4 of the frame), centre hole 7.6 mm. The polygon's corners are tangent points of the "
                      "circle and their 9 mm fillets are exact arcs of it. Board thickness 0.8 mm is an order option "
                      "at the fab: the pipeline has no thickness setting, and its gerber job and STEP carry KiCad's "
                      "default 1.6 mm stackup."),
        },
        "placement": placement,
        "route": {"passes": 30, "solve_s": 300,
                  "why": "every part is locked; the route stage measures Freerouting with fanout on and off and keeps "
                         "the better solve; the outline is stated and shaped, so it is never grown"},
        "stitch_pitch": 3.0,
        "silk": {
            "words": {"px9:C?": "Iris", "px10:C?": "Ring"},
            "title": [],
            "why": "the board's name on the back, as two words under C9 and C10 in the via-free band above the key "
                   "flat (read from the back: Iris on the left, Ring on the right). As a silk.title line it never "
                   "landed: the designator pass runs first and seats C9's and C10's designators in that band, the "
                   "only free space on the back, while words are placed before designators. No other silk words: "
                   "the wire pads' labels found no free spot at 2.1 mm pitch, so the pad order is in the README"
        },
        "captions": {
            "place_3d": "Iris Ring placed: twelve WS2812C-2020 on r = 6.6 mm every 30 deg, the 7.6 mm lens hole, "
                        "the key flat at the bottom; capacitors and wire pads are on the back.",
            "done_3d": "Iris Ring (B3): 12 x WS2812C-2020-V1 chained clockwise, 12 x 100 nF behind them, 33 ohm "
                       "DIN resistor, 4.7 uF bulk, four wire pads on the temporal edge."
        },
    }


def main():
    parts = plan()
    check(parts)
    data = brief(parts)
    path = os.path.join(HERE, "board.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)
    for p in parts:
        print("%-4s %-6s (%7.3f, %7.3f) rot %3d" % (p.ref, p.side, p.xy[0], p.xy[1], p.rot))
    print("wrote", path)


if __name__ == "__main__":
    main()
