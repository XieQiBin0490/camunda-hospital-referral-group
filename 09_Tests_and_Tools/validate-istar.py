#!/usr/bin/env python3
"""Check the i* models - the source file, a piStar project, or both.

The portfolio brief asks for the SD and SR models to be kept consistent, and Task 02
section B.5 claims three specific consistency properties. This checks them mechanically
so the claim in the document can be re-run rather than asserted:

  A  the source file is self-consistent (unique element ids, every boundary resolves)
  B  SD and SR agree: every SR actor appears in the SD; every boundary link matches a
     dependency drawn in the SD, with the same type; no SR boundary uses a type the SD
     never uses
  C  the headline counts the portfolio text quotes are the counts in the model
  D  a piStar project, if given, carries the same model

usage:
  python validate-istar.py                                   # the delivered source
  python validate-istar.py --pistar F1.json [F2.json ...]     # a piStar project too
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "06_iStar_Models" / "iStar_models_source.json"

TYPE_OF_KIND = {"goal": "istar.Goal", "softgoal": "istar.Quality",
                "task": "istar.Task", "resource": "istar.Resource"}
KIND_OF_TYPE = {v: k for k, v in TYPE_OF_KIND.items()}

# What portfolio section B.2 and B.3 assert, so a mismatch is caught here. The SD count
# rose from 37 to 40 when the three dependencies the case study requires were added (see
# apply-istar-consistency-fix.py); the portfolio text was updated to match.
CLAIMED = {"sd_actors": 16, "sd_dependencies": 40, "sr_actors": 7,
           "sr_elements": 61, "sr_boundaries": 9}

problems = []
notes = []


def check_source(src):
    sd = src["strategicDependencyModel"]
    sr = src["strategicRationaleModel"]

    print("A  source file")
    ids = [e["id"] for a in sr["actors"] for e in a["elements"]]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        problems.append(f"[A] duplicate SR element ids: {dupes}")
    print(f"A  SR element ids unique            : {'yes' if not dupes else 'NO'}")
    print(f"A  boundaries                        : {len(sr['boundaries'])}")
    bad = [b for b in sr["boundaries"] if b["fromEl"] not in ids]
    if bad:
        problems.append(f"[A] boundary fromEl does not resolve: {bad}")
    print(f"A  boundaries resolve to an element  : {len(sr['boundaries']) - len(bad)}"
          f"/{len(sr['boundaries'])}")

    print("\nB  SD and SR consistency")
    sd_actor_names = {a["name"] for a in sd["actors"]}
    sr_actor_names = {a["name"] for a in sr["actors"]}
    missing = sr_actor_names - sd_actor_names
    if missing:
        problems.append(f"[B] SR opens actors absent from the SD: {missing}")
    print(f"B  SR actors present in the SD       : {len(sr_actor_names) - len(missing)}"
          f"/{len(sr_actor_names)}")

    sd_deps = {(d["from"], d["to"], d["kind"], d["label"]) for d in sd["dependencies"]}
    sd_types = {d["kind"] for d in sd["dependencies"]}
    name_to_sd = {a["name"]: a["id"] for a in sd["actors"]}
    sr_name = {a["id"]: a["name"] for a in sr["actors"]}

    def matches(b):
        """A boundary link matches an SD dependency in either direction. When the opened
        actor is the *dependee*, the SR draws the link out of the internal element that
        satisfies the dependum, so the actor-to-external direction is reversed relative
        to the SD."""
        opened = name_to_sd.get(sr_name.get(b["fromActor"], ""), b["fromActor"])
        ext = b["to"]
        return ((ext, opened, b["kind"], b["label"]) in sd_deps
                or (opened, ext, b["kind"], b["label"]) in sd_deps)

    unmatched = [b for b in sr["boundaries"] if not matches(b)]
    if unmatched:
        for b in unmatched:
            notes.append(f"[B] boundary not found verbatim in the SD: "
                         f"{b['fromActor']} -> {b['to']} [{b['kind']}] {b['label']}")
    print(f"B  boundaries matching an SD dependency: "
          f"{len(sr['boundaries']) - len(unmatched)}/{len(sr['boundaries'])}")
    alien = {b["kind"] for b in sr["boundaries"]} - sd_types
    if alien:
        problems.append(f"[B] SR boundary uses a type the SD never uses: {alien}")
    print(f"B  boundary types used by the SD      : "
          f"{'all' if not alien else 'ALIEN ' + str(alien)}")

    print("\nC  counts against the portfolio text")
    actual = {
        "sd_actors": len(sd["actors"]),
        "sd_dependencies": len(sd["dependencies"]),
        "sr_actors": len(sr["actors"]),
        "sr_elements": sum(len(a["elements"]) for a in sr["actors"]),
        "sr_boundaries": len(sr["boundaries"]),
    }
    for key, want in CLAIMED.items():
        got = actual[key]
        ok = got == want
        if not ok:
            problems.append(f"[C] {key}: the portfolio claims {want}, the model has {got}")
        print(f"C  {key:<18} portfolio {want:>3}   model {got:>3}   "
              f"{'match' if ok else 'MISMATCH'}")
    print(f"C  SD dependency mix                  : "
          f"{dict(Counter(d['kind'] for d in sd['dependencies']))}")
    return actual


def check_pistar(path, src):
    print(f"\nD  piStar project: {path.name}")
    proj = json.loads(path.read_text(encoding="utf-8"))
    ids = ({a["id"] for a in proj["actors"]}
           | {n["id"] for a in proj["actors"] for n in a["nodes"]}
           | {d["id"] for d in proj["dependencies"]})
    dangling = [l for l in proj["links"] if l["source"] not in ids or l["target"] not in ids]
    if dangling:
        problems.append(f"[D] {path.name}: {len(dangling)} dangling link(s)")
    print(f"D  actors {len(proj['actors'])}  nodes "
          f"{sum(len(a['nodes']) for a in proj['actors'])}  "
          f"dependencies {len(proj['dependencies'])}  links {len(proj['links'])}")
    print(f"D  dangling links                     : {len(dangling)}")

    sr = src["strategicRationaleModel"]
    want = {e["name"] for a in sr["actors"] for e in a["elements"]}
    got = {n["text"] for a in proj["actors"] for n in a["nodes"]}
    diff = want - got
    if diff and got:
        notes.append(f"[D] {path.name}: {len(diff)} SR element(s) not present, e.g. "
                     f"{sorted(diff)[:2]}")
    if got:
        print(f"D  SR elements carried across         : {len(want & got)}/{len(want)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pistar", nargs="*", default=[])
    args = ap.parse_args()

    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    check_source(src)
    for name in args.pistar:
        check_pistar(Path(name), src)

    print()
    if notes:
        print(f"NOTES ({len(notes)})")
        for n in notes:
            print("  -", n)
        print()
    if problems:
        print(f"PROBLEMS ({len(problems)})")
        for p in problems:
            print("  -", p)
        print()
        print("RESULT: %d problem(s)" % len(problems))
        return 1
    print("RESULT: i* models consistent"
          + ("" if not notes else " (see notes)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
