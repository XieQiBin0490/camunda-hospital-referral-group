#!/usr/bin/env python3
"""Render the i* Strategic Dependency model to SVG, straight from the source.

Why this exists
---------------
The delivered SD figure was produced by tools/build-istar.mjs, which is not in this
repository, and piStar - the obvious replacement - will not open a file the team can
load. Adding three dependencies by hand to the existing SVG is not viable either: that
figure is already at capacity, with 37 dependums filling every gap between the sixteen
actor circles, and several already overlapping. So the figure is drawn here instead.

Layout
------
The sixteen actor positions are taken from the delivered figure, so the picture keeps the
arrangement the team's readers already know: patients and the referring organisation down
the left, hospital teams in two middle columns, external services down the right. Each
dependency is placed on the line between its depender and its dependee, and dependums that
share an actor pair are fanned out perpendicular to that line so they do not stack.

The annotation band along the bottom is copied verbatim from the delivered figure, so the
justification text the portfolio refers to is preserved.

usage: python render-istar-sd.py [--out PATH.svg]
"""

import argparse
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "06_iStar_Models" / "iStar_models_source.json"
TEMPLATE = ROOT / "06_iStar_Models" / "iStar_SD_Initial_Release.svg"

# Actor centres and radii read from the delivered figure, in the model's actor order.
POSITIONS = [(180, 330, 80), (180, 760, 78), (650, 210, 78), (650, 580, 88),
             (650, 980, 80), (650, 1290, 80), (1190, 180, 82), (1190, 500, 90),
             (1190, 830, 76), (1190, 1120, 78), (1760, 130, 82), (1760, 400, 84),
             (1760, 690, 88), (1760, 980, 86), (1760, 1250, 82), (1190, 1400, 78)]

W, H = 2200, 1560          # drawing area; the annotation band sits below it
FONT = "Segoe UI, Arial, sans-serif"

KIND_STYLE = {
    "goal":     {"fill": "#dbeafe", "stroke": "#1d4ed8"},
    "softgoal": {"fill": "#fef3c7", "stroke": "#b45309"},
    "task":     {"fill": "#dcfce7", "stroke": "#15803d"},
    "resource": {"fill": "#f3e8ff", "stroke": "#7e22ce"},
}


def wrap(text, width=22, max_lines=3):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:width - 1] + "\u2026"
    return lines or [""]


def shape(kind, x, y, w, h):
    """The dependum shape, centred on (x, y)."""
    s = KIND_STYLE[kind]
    left, top = x - w / 2, y - h / 2
    if kind == "goal":
        return (f'<rect x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="{h/2:.1f}" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.4"/>')
    if kind == "resource":
        return (f'<rect x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" '
                f'rx="4" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.4"/>')
    if kind == "task":
        n = h / 2
        pts = [(left + n, top), (left + w - n, top), (left + w, y),
               (left + w - n, top + h), (left + n, top + h), (left, y)]
        return (f'<polygon points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" '
                f'fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.4"/>')
    # soft goal: a cloud, approximated by overlapping arcs
    a = h / 2
    return (f'<path d="M {left+a:.1f} {y+a:.1f} '
            f'A {a*1.1:.1f} {a*1.1:.1f} 0 0 1 {left+w*0.35:.1f} {y-a*0.55:.1f} '
            f'A {a*1.2:.1f} {a*1.2:.1f} 0 0 1 {left+w*0.7:.1f} {y-a*0.5:.1f} '
            f'A {a*1.0:.1f} {a*1.0:.1f} 0 0 1 {left+w-a:.1f} {y+a:.1f} Z" '
            f'fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="1.4"/>')


def arrowhead(x, y, angle, size=11):
    a1, a2 = angle + math.radians(155), angle - math.radians(155)
    p = [(x, y), (x + size * math.cos(a1), y + size * math.sin(a1)),
         (x + size * math.cos(a2), y + size * math.sin(a2))]
    return f'<polygon points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in p)}" fill="#0f172a"/>'


def band_text():
    """Lift the annotation band from the delivered figure, unchanged."""
    if not TEMPLATE.exists():
        return ""
    old = TEMPLATE.read_text(encoding="utf-8")
    i = old.rfind('<rect x="10" y="1536"')
    if i < 0:
        i = old.find('<rect x="10" y="153')
    if i < 0:
        return ""
    return old[i:old.rindex("</svg>")]


def build(src):
    sd = src["strategicDependencyModel"]
    actors = sd["actors"]
    if len(actors) != len(POSITIONS):
        raise SystemExit(f"the figure expects {len(POSITIONS)} actors, the model has {len(actors)}")
    pos = {a["id"]: POSITIONS[i] for i, a in enumerate(actors)}

    # group dependencies by actor pair so cords that share a pair can be fanned out
    by_pair = {}
    for d in sd["dependencies"]:
        by_pair.setdefault(frozenset((d["from"], d["to"])), []).append(d)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H + 420}" '
           f'viewBox="0 0 {W} {H + 420}">',
           f'<rect x="0" y="0" width="{W}" height="{H + 420}" fill="#ffffff"/>']

    # ---- legend
    out.append(f'<text x="20" y="30" font-family="{FONT}" font-size="13" font-weight="700" '
               f'fill="#1f3864">Dependum types and the dependency arrow (depender to dependee)</text>')
    lx = 24
    for kind, label in (("goal", "goal dependency"), ("softgoal", "softgoal dependency"),
                        ("task", "task dependency"), ("resource", "resource dependency")):
        out.append(shape(kind, lx + 38, 62, 76, 30))
        out.append(f'<text x="{lx + 84}" y="66" font-family="{FONT}" font-size="10.5" '
                   f'fill="#374151">{label}</text>')
        lx += 250

    # ---- dependency arrows and dependums
    for pair, deps in by_pair.items():
        ids = list(pair)
        if len(ids) != 2:
            continue
        a, b = ids
        ax, ay, ar = pos[a]
        bx, by, br = pos[b]
        ux, uy = bx - ax, by - ay
        length = math.hypot(ux, uy) or 1
        ux, uy = ux / length, uy / length
        px, py = -uy, ux                      # perpendicular
        for k, d in enumerate(deps):
            spread = (k - (len(deps) - 1) / 2) * 74
            t = 0.5
            cx = ax + (bx - ax) * t + px * spread
            cy = ay + (by - ay) * t + py * spread
            # keep the dependum clear of the two circles
            for (ox, oy, orr) in ((ax, ay, ar), (bx, by, br)):
                while math.hypot(cx - ox, cy - oy) < orr + 62:
                    cx += px * 6 + ux * 2
                    cy += py * 6 + uy * 2
            # arrow: depender edge -> dependee edge, through the dependum
            sxp, syp = ax + ux * ar, ay + uy * ar
            exp, eyp = bx - ux * (br + 16), by - uy * (br + 16)
            out.append(f'<line x1="{sxp:.1f}" y1="{syp:.1f}" x2="{exp:.1f}" y2="{eyp:.1f}" '
                       f'stroke="#334155" stroke-width="1.3"/>')
            out.append(arrowhead(exp, eyp, math.atan2(uy, ux)))
            lines = wrap(d["label"])
            w = max(120, min(210, 11 + max(len(x) for x in lines) * 6.6))
            h = 26 + 17 * len(lines)
            # white plate, then the typed shape, then the label, then the kind tag
            out.append(f'<rect x="{cx-w/2-5:.1f}" y="{cy-h/2-4:.1f}" width="{w+10:.1f}" '
                       f'height="{h+8:.1f}" rx="6" fill="#ffffff"/>')
            out.append(shape(d["kind"], cx, cy, w, h))
            for j, line in enumerate(lines):
                ty = cy - h / 2 + 20 + j * 17
                out.append(f'<text x="{cx:.1f}" y="{ty:.1f}" font-family="{FONT}" font-size="11" '
                           f'fill="#111827" text-anchor="middle">{escape(line)}</text>')
            tag = d["kind"]
            tw = 9 + len(tag) * 5.6
            out.append(f'<rect x="{cx-tw/2:.1f}" y="{cy-h/2-18:.1f}" width="{tw:.1f}" height="15" '
                       f'rx="3" fill="#ffffff" fill-opacity="0.92"/>')
            out.append(f'<text x="{cx:.1f}" y="{cy-h/2-7:.1f}" font-family="{FONT}" font-size="9.5" '
                       f'fill="#6b7280" text-anchor="middle" font-style="italic">{tag}</text>')

    # ---- actors on top, so a dependum can never hide a name
    for a in actors:
        x, y, r = pos[a["id"]]
        label = wrap(a["name"], width=20, max_lines=3)
        out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#ffffff" stroke="#334155" '
                   f'stroke-width="1.6"/>')
        for j, line in enumerate(label):
            ty = y - (len(label) - 1) * 8 + j * 16 + 4
            out.append(f'<text x="{x}" y="{ty}" font-family="{FONT}" font-size="11.5" '
                       f'fill="#111827" text-anchor="middle">{escape(line)}</text>')

    out.append(f'<g transform="translate(0,{H})">{band_text()}</g>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "06_iStar_Models" / "iStar_SD_Initial_Release.svg"))
    args = ap.parse_args()
    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    svg = build(src)
    Path(args.out).write_text(svg, encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"  actors {len(src['strategicDependencyModel']['actors'])}  "
          f"dependencies {len(src['strategicDependencyModel']['dependencies'])}  "
          f"({len(svg)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
