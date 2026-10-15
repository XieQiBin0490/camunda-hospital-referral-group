#!/usr/bin/env python3
"""Export the delivered i* models as piStar projects, and print the redraw runbook.

Why
---
The diagrams in 06_iStar_Models/ are rendered by tools/build-istar.mjs, which is not in
this repository, so the team cannot redraw or re-export them with the tool that made
them. piStar (https://github.com/jhcp/piStar, docs/JSON.md) is the reference i* 2.0 tool
and reads a documented JSON format, so the delivered models can be re-expressed as
piStar projects that open, edit and export to PDF/SVG without the missing generator.

What is and is not carried across
---------------------------------
* The SD model is complete: 16 actors and 37 typed dependencies all come from the
  source, so the exported project is the whole model.
* The SR model carries the 7 opened actors, their 61 intentional elements with the
  correct i* type and grid position, and the 9 boundary dependencies. The *internal*
  links (task decomposition, means-end, contribution) are not recorded in
  iStar_models_source.json - they exist only as lines in the SVG - so they have to be
  drawn in piStar. The runbook says which links are needed in which layer.

usage:
  python export-pistar-projects.py [--out DIR]
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "06_iStar_Models" / "iStar_models_source.json"

# i* 2.0 element type used by piStar, per the kind names in the source
PISTAR_TYPE = {
    "goal": "istar.Goal",
    "softgoal": "istar.Quality",
    "task": "istar.Task",
    "resource": "istar.Resource",
}

GRID_X0, GRID_DX = 24, 216
GRID_Y0, GRID_DY = 46, 78


def new_id():
    return str(uuid.uuid4())


def layout_actors(actors, externals, internal_cols=2, gap_x=300, gap_y=260):
    """A deterministic grid: internal actors in columns, external actors down the right."""
    placed = []
    for i, a in enumerate(actors):
        col, row = divmod(i, 4)
        placed.append({"key": a["id"], "text": a["name"],
                       "x": 60 + col * gap_x * 1.6, "y": 60 + row * gap_y})
    for i, e in enumerate(externals):
        placed.append({"key": e["id"], "text": e["name"], "external": True,
                       "x": 60 + internal_cols * gap_x * 1.6 + 260, "y": 60 + i * gap_y})
    return placed


def build_sd(src):
    sd = src["strategicDependencyModel"]
    actors = []
    pos = {}
    for i, a in enumerate(sd["actors"]):
        col, row = divmod(i, 4)
        x, y = 80 + col * 520, 60 + row * 300
        pos[a["id"]] = (x, y)
        actors.append({"id": a["id"], "text": a["name"], "type": "istar.Actor",
                       "x": x, "y": y, "nodes": []})

    nodes = {a["id"]: a for a in actors}
    dependencies, links = [], []
    for i, dep in enumerate(sd["dependencies"]):
        did = new_id()
        sx, sy = pos[dep["from"]]
        tx, ty = pos[dep["to"]]
        dependencies.append({
            "id": did, "text": dep["label"], "type": PISTAR_TYPE[dep["kind"]],
            "x": (sx + tx) // 2, "y": (sy + ty) // 2 + i % 5 * 18,
            "source": dep["from"], "target": dep["to"]})
        links.append({"id": new_id(), "type": "istar.DependencyLink",
                      "source": dep["from"], "target": did})
        links.append({"id": new_id(), "type": "istar.DependencyLink",
                      "source": did, "target": dep["to"]})
    return {"actors": actors, "orphans": [], "dependencies": dependencies, "links": links,
            "display": {}, "diagram": {"width": 2200, "height": 1700}}, nodes


def build_sr(src):
    sr = src["strategicRationaleModel"]
    sd = src["strategicDependencyModel"]
    sd_by_id = {a["id"]: a["name"] for a in sd["actors"]}

    actors = []
    for a in sr["actors"]:
        nodes = []
        for e in a["elements"]:
            nodes.append({
                "id": e["id"], "text": e["name"], "type": PISTAR_TYPE[e["kind"]],
                "x": a["x"] + GRID_X0 + e["col"] * GRID_DX,
                "y": a["y"] + GRID_Y0 + e["row"] * GRID_DY})
        actors.append({"id": a["id"], "text": a["name"], "type": "istar.Actor",
                       "x": a["x"], "y": a["y"], "nodes": nodes,
                       "w": a["w"], "cols": a["cols"], "rows": a["rows"]})

    externals = []
    for i, e in enumerate(sr.get("externals", [])):
        externals.append({"id": e["id"], "text": e["name"], "type": "istar.Actor",
                          "x": e["x"], "y": e["y"], "nodes": []})
    known = {a["id"] for a in actors} | {e["id"] for e in externals}
    for b in sr["boundaries"]:
        if b["to"] not in known:
            externals.append({"id": b["to"], "text": sd_by_id.get(b["to"], b["to"]),
                              "type": "istar.Actor", "x": 1900, "y": 100 + len(externals) * 240,
                              "nodes": []})
            known.add(b["to"])

    dependencies, links = [], []
    for b in sr["boundaries"]:
        did = new_id()
        dependencies.append({"id": did, "text": b["label"], "type": PISTAR_TYPE[b["kind"]],
                             "x": 1650, "y": 120 + len(dependencies) * 90,
                             "source": b["fromEl"], "target": b["to"]})
        links.append({"id": new_id(), "type": "istar.DependencyLink",
                      "source": b["fromEl"], "target": did})
        links.append({"id": new_id(), "type": "istar.DependencyLink",
                      "source": did, "target": b["to"]})

    display = {a["id"]: {"collapsed": True} for a in externals}
    project = {"actors": actors + externals, "orphans": [], "dependencies": dependencies,
               "links": links, "display": display,
               "diagram": {"width": sr["width"] + 600, "height": sr["height"]}}
    return project, sr


def stamp(project):
    project["tool"] = "pistar.2.0.0"
    project["istar"] = "2.0"
    project["saveDate"] = "Thu, 01 Jan 2026 00:00:00 GMT"
    return project


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "06_iStar_Models" / "pistar"))
    args = ap.parse_args()
    out = Path(args.out)

    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    sd_project, _ = build_sd(src)
    sd_project = stamp(sd_project)
    (out / "iStar_SD_pistar.json").write_text(
        json.dumps(sd_project, indent=1, ensure_ascii=False), encoding="utf-8")

    sr_project, sr = build_sr(src)
    sr_project = stamp(sr_project)
    (out / "iStar_SR_pistar.json").write_text(
        json.dumps(sr_project, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"SD: actors {len(sd_project['actors'])}  dependencies "
          f"{len(sd_project['dependencies'])}  links {len(sd_project['links'])}")
    print(f"SR: actors {len(sr_project['actors'])} "
          f"(opened {len(sr['actors'])}, external {len(sr_project['actors']) - len(sr['actors'])})  "
          f"nodes {sum(len(a['nodes']) for a in sr_project['actors'])}  "
          f"dependencies {len(sr_project['dependencies'])}  "
          f"links {len(sr_project['links'])}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
