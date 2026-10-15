#!/usr/bin/env python3
"""Rebuild 06_iStar_Models/iStar_models_source.json from the delivered i* SVG.

Why this exists
---------------
The delivered SR figure opens seven actors, but the "editable source" shipped beside
it only defines four. A marker who opens the JSON (which SUBMISSION_MAP.md lists as
part of the i* deliverable, and whose own description claims it generates the
diagrams) sees a model that cannot produce the figure. This script removes that
discrepancy by reading the element inventory back out of the SVG that IS the figure.

Method
------
The SVG is generated with a fixed visual vocabulary, so the inventory is recoverable:

  task      polygon  fill #dcfce7  stroke #15803d   (green hexagon)
  goal      rect     fill #dbeafe  stroke #1d4ed8   (blue pill)
  softgoal  path     fill #fef3c7  stroke #b45309   (amber cloud)
  resource  rect     fill #f3e8ff                   (purple rectangle)
  actor box rect     fill #fbfdff

Elements are assigned to the actor box that contains them, and an element's name is
the text drawn inside it. Boundary dependencies are the dashed links from an element
to an actor node drawn outside the opened boxes.

Validation
----------
The four actors already present in the shipped JSON act as ground truth: the script
compares its extraction against them and refuses to write anything if they differ.
That proves the reader before it is trusted for the three actors that were missing.

usage: python rebuild-istar-source.py [--check-only]
"""

import argparse
import json
import math
import re
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISTAR = ROOT / "06_iStar_Models"
SR_SVG = ISTAR / "iStar_SR_Initial_Release.svg"
SD_SVG = ISTAR / "iStar_SD_Initial_Release.svg"
SOURCE = ISTAR / "iStar_models_source.json"

KIND_BY_FILL = {
    "#dcfce7": "task",
    "#dbeafe": "goal",
    "#fef3c7": "softgoal",
    "#f3e8ff": "resource",
}
ACTOR_FILL = "#fbfdff"
# The generator lays elements out on a grid: 200 wide in a 3-column actor, 632 wide for
# the top-level decomposing task, 184 for a cloud. A boundary dependum is drawn free,
# at 150-165 wide. Width therefore separates an element from a dependum cleanly, which
# fill colour alone cannot do because both are drawn in the same palette.
ELEMENT_MIN_WIDTH = 180
# How far a soft goal cloud rises above, and dips below, the baseline its path traces.
CLOUD_RISE = 26
CLOUD_DROP = 6

SHAPE_RE = re.compile(r'<(rect|polygon|path|circle)\b([^>]*?)/?>')
TEXT_RE = re.compile(r'<text\b([^>]*)>(.*?)</text>', re.S)
ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
NUM_RE = re.compile(r'-?\d+(?:\.\d+)?')
# The actor title is the only text drawn in this colour inside an actor box.
TITLE_FILL = "#1f3864"
# Contribution labels are drawn on the link, not inside a shape, but they sit close
# enough to be picked up by a bounding box test.
CONTRIBUTIONS = {"make", "help", "hurt", "break", "some+", "some-", "unknown"}


def unescape(text):
    return (text.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"'))


def attrs(blob):
    return dict(ATTR_RE.findall(blob))


def path_points(d):
    """Absolute endpoints of an SVG path. Arc radii and flags are not coordinates:
    reading them as x/y pairs is what broke the first version of this reader."""
    tokens = re.findall(r'[A-Za-z]|-?\d*\.?\d+', d)
    pts, i, cmd = [], 0, None
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            continue
        if cmd in ("M", "L"):
            pts.append((float(tokens[i]), float(tokens[i + 1])))
            i += 2
        elif cmd == "A":
            pts.append((float(tokens[i + 5]), float(tokens[i + 6])))
            i += 7
        elif cmd in ("H", "V"):
            i += 1
        else:
            i += 1
    return pts


def bbox_of(tag, a):
    if tag == "circle":
        cx, cy, r = float(a.get("cx", 0)), float(a.get("cy", 0)), float(a.get("r", 0))
        return cx - r, cy - r, cx + r, cy + r
    if tag == "rect":
        x, y = float(a.get("x", 0)), float(a.get("y", 0))
        return x, y, x + float(a.get("width", 0)), y + float(a.get("height", 0))
    if tag == "polygon":
        nums = [float(n) for n in NUM_RE.findall(a.get("points", ""))]
        xs, ys = nums[0::2], nums[1::2]
        return min(xs), min(ys), max(xs), max(ys)
    pts = path_points(a.get("d", ""))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # A cloud's path endpoints all lie on its baseline, because the arcs bulge upward
    # and land back on it. The body and its label sit above that line, so the extent
    # has to be estimated or the shape measures zero high and owns no text.
    return min(xs), min(ys) - CLOUD_RISE, max(xs), max(ys) + CLOUD_DROP


def read_svg(path):
    text = path.read_text(encoding="utf-8", errors="ignore")

    shapes = []
    for m in SHAPE_RE.finditer(text):
        tag, a = m.group(1), attrs(m.group(2))
        if "fill" not in a:
            continue
        x0, y0, x1, y1 = bbox_of(tag, a)
        shapes.append({"tag": tag, "attrs": a, "bbox": (x0, y0, x1, y1),
                       "fill": a["fill"].lower()})

    texts = []
    for m in TEXT_RE.finditer(text):
        a = attrs(m.group(1))
        body = unescape(re.sub(r"<[^>]+>", "", m.group(2)).strip())
        if not body:
            continue
        texts.append({"x": float(a.get("x", 0)), "y": float(a.get("y", 0)),
                      "text": body, "fill": (a.get("fill") or "").lower(),
                      "weight": a.get("font-weight", "")})
    return shapes, texts


def inside(bbox, outer, pad=2.0):
    x0, y0, x1, y1 = bbox
    X0, Y0, X1, Y1 = outer
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return X0 - pad <= cx <= X1 + pad and Y0 - pad <= cy <= Y1 + pad


def name_of(shape, texts):
    """The name is the text owned by this shape. Ownership is decided by the smallest
    containing shape, because a boundary dependum is drawn on top of an element and
    otherwise donates its label to that element."""
    lines = [t for t in texts if t.get("owner") is shape and t["text"] not in CONTRIBUTIONS]
    lines.sort(key=lambda t: (round(t["y"], 1), t["x"]))
    return " ".join(t["text"] for t in lines).strip()


def extract(path):
    shapes, texts = read_svg(path)

    kind_shapes = [s for s in shapes if s["fill"] in KIND_BY_FILL]
    for t in texts:
        point = (t["x"], t["y"] - 6, t["x"], t["y"])
        owners = [s for s in kind_shapes if inside(point, s["bbox"])]
        # A label is drawn horizontally centred in its shape, and a boundary dependum is
        # drawn on top of an element with almost the same centre. Nearest centre to the
        # text therefore separates them; smallest area alone does not, because it hands
        # the element's own label to the dependum.
        t["owner"] = min(owners, key=lambda s: (
            abs((s["bbox"][0] + s["bbox"][2]) / 2 - t["x"]),
            (s["bbox"][2] - s["bbox"][0]) * (s["bbox"][3] - s["bbox"][1]))) if owners else None

    actors = [s for s in shapes if s["fill"] == ACTOR_FILL and s["tag"] == "rect"]
    actors.sort(key=lambda s: (round(s["bbox"][1]), round(s["bbox"][0])))

    out = []
    for actor in actors:
        box = actor["bbox"]
        members = [s for s in shapes
                   if s["fill"] in KIND_BY_FILL
                   and s is not actor
                   and (s["bbox"][2] - s["bbox"][0]) >= ELEMENT_MIN_WIDTH
                   and inside(s["bbox"], box)]
        title_lines = [t for t in texts
                       if inside((t["x"], t["y"] - 6, t["x"], t["y"]), box)
                       and t["fill"] == TITLE_FILL]
        title_lines.sort(key=lambda t: (round(t["y"], 1), t["x"]))
        elements = []
        for m in members:
            elements.append({"kind": KIND_BY_FILL[m["fill"]],
                             "name": name_of(m, texts),
                             "bbox": m["bbox"]})
        elements.sort(key=lambda e: (round(e["bbox"][1]), round(e["bbox"][0])))
        out.append({"name": " ".join(t["text"] for t in title_lines).strip(),
                    "bbox": box, "elements": elements})
    return out, shapes, texts


def grid_position(bbox, actor_bbox):
    """Map a drawn position onto the generator's grid: 3 columns of 216 px starting
    24 px inside the box, rows of 78 px starting 46 px down."""
    x0, y0, x1, y1 = bbox
    ax, ay = actor_bbox[0], actor_bbox[1]
    col = max(0, round((x0 - ax - 24) / 216))
    row = max(0, round((y0 - ay - 46) / 78))
    span = max(1, round((x1 - x0) / 216))
    return col, row, span


# Actor id and element letter, for all seven opened actors. The first four are the ones
# the shipped source already defined, so their ids and letters must not change.
ACTOR_CODES = {
    "Consultant / Clinical Team": ("ACT_Consultant", "C"),
    "Medical Secretaries": ("ACT_Secretary", "S"),
    "Treatment & Chemotherapy Bookings Team": ("ACT_Treatment", "T"),
    "Finance Team": ("ACT_Finance", "F"),
    "Outpatient Bookings Team": ("ACT_Bookings", "B"),
    "Patient Pathway Coordinators": ("ACT_Pathway", "P"),
    "Clinical Nurse Specialist Team": ("ACT_CNS", "N"),
}


def build_sr(extracted, shapes, texts, sd_actors):
    """The seven-actor SR section, in the shipped source's own shape."""
    actors = []
    element_ids = {}
    for actor in extracted:
        name = actor["name"]
        aid, letter = ACTOR_CODES[name]
        box = actor["bbox"]
        rows = []
        for e in actor["elements"]:
            col, row, span = grid_position(e["bbox"], box)
            rows.append({"kind": e["kind"], "name": e["name"],
                         "col": col, "row": row, "span": span,
                         "y": e["bbox"][1], "x": e["bbox"][0]})
        # Numbering, reproduced from the shipped file: the decomposing task is 0,
        # then goals, tasks and soft goals each number separately in row-major order.
        top = [r for r in rows if r["span"] >= 3]
        rest = [r for r in rows if r["span"] < 3]
        ordered = []
        for r in top:
            ordered.append((f"T_{letter}0", r))
        n = 1
        for r in sorted([r for r in rest if r["kind"] == "goal"],
                        key=lambda r: (r["row"], r["col"])):
            ordered.append((f"G_{letter}{n}", r))
            n += 1
        n = 1
        for r in sorted([r for r in rest if r["kind"] == "task"],
                        key=lambda r: (r["row"], r["col"])):
            ordered.append((f"T_{letter}{n}", r))
            n += 1
        n = 1
        for r in sorted([r for r in rest if r["kind"] == "softgoal"],
                        key=lambda r: (r["row"], r["col"])):
            ordered.append((f"S_{letter}{n}", r))
            n += 1

        elements = []
        for eid, r in ordered:
            elements.append(OrderedDict([("id", eid), ("kind", r["kind"]),
                                         ("name", r["name"]), ("col", r["col"]),
                                         ("row", r["row"]), ("span", r["span"])]))
            element_ids[(name, r["name"])] = (eid, r)

        actors.append(OrderedDict([
            ("id", aid), ("name", name),
            ("x", int(box[0])), ("y", int(box[1])),
            ("w", int(box[2] - box[0])), ("cols", 3), ("rows", 4),
            ("elements", elements)]))
    return actors


def dist_point_segment(pt, p, q):
    px, py = pt
    x1, y1 = p
    x2, y2 = q
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.dist(pt, p)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.dist(pt, (x1 + t * dx, y1 + t * dy))


def resolve_sd(name, sd_actors):
    """The SR draws the referring organisation as "GP or another hospital" while the SD
    says "GP or other hospital"; match on a distinctive prefix rather than exactly."""
    for a in sd_actors:
        if a["name"] == name:
            return a["id"]
    key = name.split("(")[0].strip().lower()
    for a in sd_actors:
        if a["name"].split("(")[0].strip().lower() == key:
            return a["id"]
    return name


def build_boundaries(path, shapes, texts, extracted, built_actors, sd_actors):
    """The nine dashed links, resolved to (fromActor, fromEl, to, kind, label).

    Each dependum shape is bound to exactly one line: the pairings are made globally by
    nearest distance, because several lines pass close to several shapes and a per-line
    nearest lookup assigns the same shape to more than one link.
    """
    svg = path.read_text(encoding="utf-8", errors="ignore")
    circles = [s for s in shapes if s["tag"] == "circle" and s["fill"] == "#ffffff"]
    name_to_act = {a["name"]: a["id"] for a in built_actors}
    DIAGRAM_BOTTOM = 1900          # below this sits the notation and assumptions band

    def centre(s):
        return ((s["bbox"][0] + s["bbox"][2]) / 2, (s["bbox"][1] + s["bbox"][3]) / 2)

    def circle_name(c):
        x0, y0, x1, y1 = c["bbox"]
        ls = [t for t in texts if x0 <= t["x"] <= x1 and y0 <= t["y"] <= y1]
        ls.sort(key=lambda t: round(t["y"], 1))
        return " ".join(t["text"] for t in ls).strip()

    lines = []
    for m in re.finditer(r'<line\b([^>]*stroke-dasharray="([^"]*)"[^>]*)/?>', svg):
        a = attrs(m.group(1))
        if a["stroke-dasharray"] == "0":
            continue
        p = (float(a["x1"]), float(a["y1"]))
        q = (float(a["x2"]), float(a["y2"]))
        if abs(q[0] - p[0]) < 60:            # the short rule in the legend band
            continue
        lines.append((p, q))

    dependums = [s for s in shapes if s["fill"] in KIND_BY_FILL
                 and (s["bbox"][2] - s["bbox"][0]) < ELEMENT_MIN_WIDTH
                 and centre(s)[1] < DIAGRAM_BOTTOM]

    pairs = sorted(
        ((dist_point_segment(centre(d), p, q), id(d), i)
         for d in dependums for i, (p, q) in enumerate(lines)),
        key=lambda t: t[0])
    shape_line, line_shape = {}, {}
    for _, sid, i in pairs:
        if sid in shape_line or i in line_shape:
            continue
        shape_line[sid] = i
        line_shape[i] = sid

    out = []
    for shape in dependums:
        i = shape_line.get(id(shape))
        if i is None:
            continue
        p, q = lines[i]
        actor = next((x for x in extracted
                      if x["bbox"][0] - 8 <= p[0] <= x["bbox"][2] + 8
                      and x["bbox"][1] - 8 <= p[1] <= x["bbox"][3] + 8), None)
        src = next((e for a in extracted if a is actor for e in a["elements"]
                    if e["bbox"][0] - 4 <= p[0] <= e["bbox"][2] + 4
                    and e["bbox"][1] - 4 <= p[1] <= e["bbox"][3] + 4), None)
        label = " ".join(t["text"] for t in texts if t.get("owner") is shape
                         and t["text"] not in CONTRIBUTIONS)
        circ = min(circles, key=lambda c: math.dist(q, centre(c)))
        out.append({"fromActor": name_to_act.get(actor["name"] if actor else "", "?"),
                    "fromEl": (src or {}).get("id", "?"),
                    "to": resolve_sd(circle_name(circ), sd_actors),
                    "kind": KIND_BY_FILL[shape["fill"]], "label": label,
                    "p": p})
    out.sort(key=lambda b: (b["p"][1], b["p"][0]))
    for b in out:
        b.pop("p")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    shipped = json.loads(SOURCE.read_text(encoding="utf-8"),
                         object_pairs_hook=OrderedDict)
    known = {a["name"]: a for a in shipped["strategicRationaleModel"]["actors"]}

    extracted, shapes, texts = extract(SR_SVG)
    print(f"SVG actor boxes found: {len(extracted)}")
    for a in extracted:
        kinds = defaultdict(int)
        for e in a["elements"]:
            kinds[e["kind"]] += 1
        print(f"  {a['name'][:44]:<46} {len(a['elements']):>3} elements  {dict(kinds)}")

    print("\n-- ground-truth check against the four actors already in the JSON --")
    ok = True
    for name, actor in known.items():
        match = next((a for a in extracted if a["name"] == name), None)
        if match is None:
            print(f"  MISSING in extraction: {name}")
            ok = False
            continue
        want = {e["name"] for e in actor["elements"]}
        got = {e["name"] for e in match["elements"]}
        same = want == got
        print(f"  {'OK   ' if same else 'DIFF '} {name[:40]:<42} "
              f"JSON={len(want)} SVG={len(got)}")
        if not same:
            ok = False
            for n in sorted(want - got):
                print(f"        only in JSON: {n}")
            for n in sorted(got - want):
                print(f"        only in SVG : {n}")
    print(f"\nGROUND TRUTH: {'reader validated' if ok else 'READER NOT VALIDATED'}")
    if not ok:
        return 1

    sr = shipped["strategicRationaleModel"]
    actors = build_sr(extracted, shapes, texts, shipped["strategicDependencyModel"]["actors"])

    # the boundary list references element ids, so hand the generated ids back
    by_key = {(a["name"], e["name"]): e["id"] for a in actors for e in a["elements"]}
    for a in extracted:
        for e in a["elements"]:
            e["id"] = by_key.get((a["name"], e["name"]))

    # the regenerated four actors must be identical to the shipped ones, field by field
    print("\n-- regeneration check against the shipped four actors --")
    shipped_by_name = {a["name"]: a for a in sr["actors"]}
    for a in actors:
        want = shipped_by_name.get(a["name"])
        if want is None:
            continue
        same = (a["id"] == want["id"] and a["x"] == want["x"] and a["y"] == want["y"]
                and a["w"] == want["w"] and a["cols"] == want["cols"]
                and a["rows"] == want["rows"]
                and [dict(e) for e in a["elements"]] == [dict(e) for e in want["elements"]])
        print(f"  {'IDENTICAL' if same else 'DIFFERS  '} {a['name'][:44]}")
        if not same:
            for got, exp in zip(a["elements"], want["elements"]):
                if dict(got) != dict(exp):
                    print(f"      got {dict(got)}")
                    print(f"      exp {dict(exp)}")
            ok = False
    if not ok:
        print("\nrefusing to write: the regenerated actors do not match the shipped file")
        return 1

    boundaries = build_boundaries(SR_SVG, shapes, texts, extracted, actors,
                                 shipped["strategicDependencyModel"]["actors"])
    print(f"\nSR actors : {len(actors)}   elements: {sum(len(a['elements']) for a in actors)}")
    print(f"boundaries: {len(boundaries)}")
    for b in boundaries:
        print(f"   {b['fromActor']:<16} {str(b['fromEl']):<8} -> {b['to']:<20} "
              f"[{b['kind']:<8}] {b['label']}")

    if not args.write:
        print("\n(dry run - pass --write to update the source file)")
        return 0

    sr["actors"] = actors
    sr["boundaries"] = boundaries
    text = json.dumps(shipped, indent=2, ensure_ascii=False) + "\n"
    SOURCE.write_text(text, encoding="utf-8")
    print(f"\nwrote {SOURCE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
