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


# piStar writes these on every actor and node it saves, and names the diagram. They are
# not required by docs/JSON.md, but matching a file piStar produced byte-shape for
# byte-shape is cheap insurance against a loader that is stricter than its own docs.
DESCRIPTION = {"Description": ""}


def actor(aid, text, x, y, nodes=None):
    return {"id": aid, "text": text, "type": "istar.Actor", "x": x, "y": y,
            "customProperties": dict(DESCRIPTION), "nodes": nodes or []}


def node(nid, text, kind, x, y):
    return {"id": nid, "text": text, "type": PISTAR_TYPE[kind], "x": x, "y": y,
            "customProperties": dict(DESCRIPTION)}


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
        actors.append(actor(a["id"], a["name"], x, y))

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
    project = {"actors": actors, "orphans": [], "dependencies": dependencies,
               "links": links, "display": {},
               "diagram": {"width": 2400, "height": 1500,
                           "name": "i* SD - HPAS initial release",
                           "customProperties": dict(DESCRIPTION)}}
    return project


def build_sr(src):
    sr = src["strategicRationaleModel"]
    sd = src["strategicDependencyModel"]
    sd_by_id = {a["id"]: a["name"] for a in sd["actors"]}

    actors = []
    for a in sr["actors"]:
        nodes = [node(e["id"], e["name"], e["kind"],
                      a["x"] + GRID_X0 + e["col"] * GRID_DX,
                      a["y"] + GRID_Y0 + e["row"] * GRID_DY)
                 for e in a["elements"]]
        actors.append(actor(a["id"], a["name"], a["x"], a["y"], nodes))

    externals = []
    for e in sr.get("externals", []):
        externals.append(actor(e["id"], e["name"], e["x"], e["y"]))
    known = {a["id"] for a in actors} | {e["id"] for e in externals}
    for b in sr["boundaries"]:
        if b["to"] not in known:
            externals.append(actor(b["to"], sd_by_id.get(b["to"], b["to"]),
                                   2150, 100 + len(externals) * 240))
            known.add(b["to"])

    dependencies, links = [], []
    for b in sr["boundaries"]:
        did = new_id()
        dependencies.append({"id": did, "text": b["label"], "type": PISTAR_TYPE[b["kind"]],
                             "x": 1800, "y": 120 + len(dependencies) * 90,
                             "source": b["fromEl"], "target": b["to"]})
        links.append({"id": new_id(), "type": "istar.DependencyLink",
                      "source": b["fromEl"], "target": did})
        links.append({"id": new_id(), "type": "istar.DependencyLink",
                      "source": did, "target": b["to"]})

    display = {a["id"]: {"collapsed": True} for a in externals}
    project = {"actors": actors + externals, "orphans": [], "dependencies": dependencies,
               "links": links, "display": display,
               "diagram": {"width": sr["width"] + 700, "height": sr["height"],
                           "name": "i* SR - HPAS initial release",
                           "customProperties": dict(DESCRIPTION)}}
    return project


# The version piStar writes into the file it saves, and reads back to decide how to load
# it. The live tool at istar.rwth-aachen.de reports "v2.1.0, released on November, 2021",
# so the file has to claim the version of the tool that will open it - a file stamped
# with a version string the loader does not recognise is rejected as "not valid".
PISTAR_TOOL = "pistar.2.1.0"


def stamp(project):
    project["tool"] = PISTAR_TOOL
    project["istar"] = "2.0"
    project["saveDate"] = "Thu, 01 Jan 2026 00:00:00 GMT"
    return project


# The key sets the documented schema uses. A file that carries these, with unique ids
# and no dangling reference, is what piStar reads.
ROOT_KEYS = {"actors", "orphans", "dependencies", "links", "display", "tool", "istar",
             "saveDate", "diagram"}
ACTOR_KEYS = {"id", "text", "type", "x", "y", "nodes"}
NODE_KEYS = {"id", "text", "type", "x", "y"}
DEP_KEYS = {"id", "text", "type", "x", "y", "source", "target"}
LINK_KEYS = {"id", "type", "source", "target"}


def conforms(project, label):
    """Check the projection against the documented schema, so a rejected load can be
    attributed to the file rather than guessed at."""
    bad = []
    if not ROOT_KEYS <= set(project):
        bad.append(f"root is missing {ROOT_KEYS - set(project)}")
    ids = set()
    for a in project["actors"]:
        if not ACTOR_KEYS <= set(a):
            bad.append(f"actor {a.get('id')} is missing {ACTOR_KEYS - set(a)}")
        if a["id"] in ids:
            bad.append(f"duplicate id {a['id']}")
        ids.add(a["id"])
        if a["type"] not in ("istar.Actor", "istar.Agent", "istar.Role"):
            bad.append(f"actor {a['id']} has type {a['type']}")
        for n in a["nodes"]:
            if not NODE_KEYS <= set(n):
                bad.append(f"node {n.get('id')} is missing {NODE_KEYS - set(n)}")
            if n["id"] in ids:
                bad.append(f"duplicate id {n['id']}")
            ids.add(n["id"])
    for d in project["dependencies"]:
        if not DEP_KEYS <= set(d):
            bad.append(f"dependency {d.get('id')} is missing {DEP_KEYS - set(d)}")
        ids.add(d["id"])
    for l in project["links"]:
        if not LINK_KEYS <= set(l):
            bad.append(f"link {l.get('id')} is missing {LINK_KEYS - set(l)}")
        if l["source"] not in ids or l["target"] not in ids:
            bad.append(f"link {l['id']} points outside the model")
    print(f"  {label}: {'conforms to the piStar schema' if not bad else 'SCHEMA PROBLEMS'}")
    for b in bad[:6]:
        print(f"      {b}")
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "06_iStar_Models" / "pistar"))
    args = ap.parse_args()
    out = Path(args.out)

    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    sd_project = stamp(build_sd(src))
    (out / "iStar_SD_pistar.json").write_text(
        json.dumps(sd_project, indent=1, ensure_ascii=False), encoding="utf-8")

    sr_project = stamp(build_sr(src))
    (out / "iStar_SR_pistar.json").write_text(
        json.dumps(sr_project, indent=1, ensure_ascii=False), encoding="utf-8")

    sr = src["strategicRationaleModel"]
    print(f"SD: actors {len(sd_project['actors'])}  dependencies "
          f"{len(sd_project['dependencies'])}  links {len(sd_project['links'])}")
    print(f"SR: actors {len(sr_project['actors'])} "
          f"(opened {len(sr['actors'])}, external "
          f"{len(sr_project['actors']) - len(sr['actors'])})  nodes "
          f"{sum(len(a['nodes']) for a in sr_project['actors'])}  dependencies "
          f"{len(sr_project['dependencies'])}  links {len(sr_project['links'])}")
    ok = conforms(sd_project, "iStar_SD_pistar.json")
    ok = conforms(sr_project, "iStar_SR_pistar.json") and ok
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
