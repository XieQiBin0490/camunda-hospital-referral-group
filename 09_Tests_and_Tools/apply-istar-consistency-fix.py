#!/usr/bin/env python3
"""Close the SD/SR consistency gap in the i* source, following the case study.

The portfolio's Task 02 section B.5 and istar-assumptions.md IA-09 both state that every
dependency drawn in the SR also appears in the SD. Comparing the nine SR boundary links
against the 37 SD dependencies shows that is not true: five diverge. Three of them name
a dependency the SD simply does not contain, and each is required by the case study:

  * "Medical Secretaries may identify missing information and request it from the
    referring organisation" (paragraph 5) - a task dependency to the referring
    organisation that the SD did not draw.
  * "if the appointment is due to take place within the following two weeks, the patient
    must also be contacted by telephone" (paragraph 7) - the SD had only the offer of an
    appointment, not the confirmation call.
  * "whether the referring organisation should be informed" (paragraph 27) - pathway
    changes are notified to the referring organisation; the SD had no such dependency.

Two more are wording or attribution divergences, fixed on the SR side:
  * the SR attributes "Distribute clinic letters" to the Consultant, while paragraph 22
    gives the distribution to the Medical Secretaries, which is what the SD says.
  * the SR calls the CNS/clinical-services dependency "Urgent investigation results"
    where the SD calls it "Blood test and assessment results".

After this runs, validate-istar.py reports 9/9 boundary links matching the SD and the
product backlog's SD dependency count becomes 40, so the portfolio text has to change
from "37 dependencies" to "40 dependencies". The script is idempotent.

usage: python apply-istar-consistency-fix.py [--check]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "06_iStar_Models" / "iStar_models_source.json"

# from, to, kind, label, the case-study sentence that requires it
NEW_SD_DEPENDENCIES = [
    ("A_Secretary", "A_Referrer", "task", "Supply missing referral information",
     "para 5: Medical Secretaries may identify missing information and request it from the referring organisation"),
    ("A_Booking", "A_Patient", "task", "Confirm attendance by telephone",
     "para 7: if the appointment is due within the following two weeks, the patient must also be contacted by telephone"),
    ("A_Pathway", "A_Referrer", "task", "Inform the referring organisation of pathway changes",
     "para 27: whether the referring organisation should be informed"),
]

# boundary key -> what it should become
SR_BOUNDARY_FIXES = {
    "Distribute clinic letters": {
        "fromActor": "ACT_Secretary", "fromEl": "T_S3",
        "why": "para 22 gives the distribution to the Medical Secretaries, not the Consultant",
    },
    "Urgent investigation results": {
        "label": "Blood test and assessment results",
        "why": "the SD names this dependency differently; one of the two has to change",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    src = json.loads(SOURCE.read_text(encoding="utf-8"), object_pairs_hook=dict)
    sd = src["strategicDependencyModel"]
    sr = src["strategicRationaleModel"]

    before_sd = len(sd["dependencies"])
    before_bad = 0

    print("-- adding the dependencies the case study requires --")
    have = {(d["from"], d["to"], d["kind"], d["label"]) for d in sd["dependencies"]}
    ids = {a["id"] for a in sd["actors"]}
    for src_a, tgt, kind, label, why in NEW_SD_DEPENDENCIES:
        if (src_a, tgt, kind, label) in have:
            print(f"  already present: {label}")
            continue
        for a in (src_a, tgt):
            if a not in ids:
                print(f"  !! unknown actor id {a}", file=sys.stderr)
                return 1
        sd["dependencies"].append({"from": src_a, "to": tgt, "kind": kind, "label": label})
        have.add((src_a, tgt, kind, label))
        print(f"  + [{kind}] {label}\n      {why}")

    print("\n-- fixing the two SR boundary links --")
    for b in sr["boundaries"]:
        fix = SR_BOUNDARY_FIXES.get(b["label"])
        if not fix:
            continue
        for key in ("fromActor", "fromEl", "label"):
            if key in fix and b[key] != fix[key]:
                print(f"  {b['label'][:38]:<40} {key}: {b[key]} -> {fix[key]}")
                b[key] = fix[key]
        if b["label"] in SR_BOUNDARY_FIXES and "why" in fix:
            print(f"      ({fix['why']})")

    after_sd = len(sd["dependencies"])
    print(f"\nSD dependencies: {before_sd} -> {after_sd}")

    if args.check:
        print("(check mode - nothing written)")
        return 0

    SOURCE.write_text(json.dumps(src, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {SOURCE}")
    print("\nnext: python 09_Tests_and_Tools/validate-istar.py   (expect 9/9)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
