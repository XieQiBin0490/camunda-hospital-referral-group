#!/usr/bin/env python3
"""Record the model-defect fixes in the documents, the defect log and the backlog.

Item 3 of the review list was "fix the BPMN models". Four defects were open; all four are
now fixed and deployed, and the form count necessarily rose from 68 to 69 because S1 could
not share the registration form with S2 (para 5 of the case study forbids the Medical
Secretaries from deciding acceptance, and S2's registration task is theirs).

usage: python record-model-fixes.py [--check]
"""

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]

DOCX = [
    ROOT / "07_Portfolio_Documents" / "UFCEP4-0-3_01_Task01_02_Strategic_BPMN_and_iStar.docx",
    ROOT / "07_Portfolio_Documents" / "UFCEP4-0-3_02_Task03_Alignment_Evaluation.docx",
    ROOT / "07_Portfolio_Documents" / "UFCEP4-0-3_03_Task04_Acceptance_Evaluation.docx",
    ROOT / "07_Portfolio_Documents" / "UFCEP4-0-3_04_Agile_Delivery_Record.docx",
    ROOT / "07_Portfolio_Documents" / "UFCEP4-0-3_06_Appendices.docx",
    ROOT / "07_Portfolio_Documents" / "UFCEP4-0-3_Portfolio.docx",
    ROOT / "08_Repository_Documents" / "UFCEP4-0-3_Manual_Run_Guide.docx",
    ROOT / "01_Agile_Planning" / "UFCEP4-0-3_Work_Division.docx",
]

REPLACEMENTS = [
    ("68 Camunda Forms", "69 Camunda Forms"),
    ("68 forms", "69 forms"),
    ("68/68 deployed", "69/69 deployed"),
    ("All 68 ", "All 69 "),
]

DEFECT_ENTRIES = """
## D. Defects found by the second-release review (item 3 of the review list)

Found by auditing the delivered models against the case study, after the initial release
was accepted. All four are fixed, deployed and re-validated.

| ID | Defect | Case-study basis | Status | Resolution | Evidence |
| --- | --- | --- | --- | --- | --- |
| DEF-17 | `T_RefundDecision` (S3) had two unconditional outgoing flows and no gateway, so BPMN read it as a parallel split and every refund case both refunded and retained the payment | Para 15 makes this a choice: an authorised member of the Finance Team determines whether a refund is appropriate | Fixed | Inserted the exclusive gateway `G_RefundDecision` with `= refundDecision = "refunded"` on the refund branch and the retain/transfer branch declared as the default flow | `validate-models.py` clean; deployed as PR_TreatmentToAftercare v5 |
| DEF-18 | `T_AuthoriseUrgentTreatment` (O1 and S3) had two unconditional outgoing flows, so the AND-split was implicit | Para 14 requires both: the treatment proceeds on clinical grounds **and** the reason is referred to the Finance Team | Fixed | Inserted the explicit `G_UrgentTreatmentAuthorised` parallel gateway, making the intent visible instead of implied | Deployed as PR_Operational_Merged v12 and PR_TreatmentToAftercare v5 |
| DEF-19 | `G_Accepted` in S1 branched on an `accepted` boolean that no form collected and no other model used, so the gateway could never leave its default flow | Para 6: the Consultant accepts, rejects, requests information or redirects | Fixed | S1 now branches on the controlled `referralDecision`, and `T_Register` binds to the new `form-register-referral-landscape`; the shared `form-register-referral` is left alone because S2's registration task belongs to the Medical Secretaries, who para 5 forbids from deciding acceptance | Deployed as PR_Landscape v5; the form count rose from 68 to 69 |
| DEF-20 | `form-prepare-accessible-format` collected `followUpSlotWithinPeriod`, a follow-up booking flag belonging to the follow-up forms | Task attribution | Fixed | Field removed from that form | `validate-form-controls.py` reports 0 inappropriate controls |
| DEF-21 | Three worker inputs had no form anywhere, so their value could only ever be the worker's own default: `documentationCheckResult`, `letterRecipients`, `refundAuthorised` | Para 5, 22 and 15 require a person to record the check outcome, the letter recipients and the financial authorisation | Fixed | Added to `form-check-referral-documents`, `form-clinic-letter-admin-check` and `form-refund-decision` respectively | `validate-form-controls.py` reports 0 worker inputs with no form source |
"""


def patch_docx(path, tally):
    doc = Document(str(path))

    def walk(container):
        for p in container.paragraphs:
            for run in p.runs:
                for old, new in REPLACEMENTS:
                    if old in run.text:
                        run.text = run.text.replace(old, new)
                        tally[old] = tally.get(old, 0) + 1

    walk(doc)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                walk(cell)
    return doc


def update_backlog(check):
    book = ROOT / "01_Agile_Planning" / ("Hospital_Patient_System_Project_Backlog_"
                                       "按评价逐项修正最终版.xlsx")
    wb = load_workbook(book)
    done = "Done\n完成"
    edits = []
    ws = wb["Project Backlog"]
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value) == "PB-47":
            ws.cell(row=r, column=13, value=done)
            edits.append("PB-47 -> Done")
    ws = wb["Sprint 3 Backlog"]
    for r in range(4, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value) == "S3-23":
            ws.cell(row=r, column=10, value=done)
            ws.cell(row=r, column=11, value=(
                "All four defects fixed and deployed: G_RefundDecision inserted (S3), an "
                "explicit parallel gateway for urgent treatment (O1, S3), S1 branches on "
                "referralDecision from its own form, and the three worker inputs now have "
                "a form. validate-models.py and validate-form-controls.py report 0 problems."))
            edits.append("S3-23 -> Done")
    if check:
        return edits
    wb.save(book)
    return edits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    total = 0
    for path in DOCX:
        if not path.exists():
            print(f"  missing: {path.name}")
            continue
        doc = patch_docx(path, {})
        tally = {}
        doc = patch_docx(path, tally)
        n = sum(tally.values())
        total += n
        print(f"  {path.name:<58} {tally if tally else 'no change'}")
        if n and not args.check:
            doc.save(str(path))

    log = ROOT / "08_Repository_Documents" / "defect-log.md"
    text = log.read_text(encoding="utf-8")
    if "DEF-17" not in text:
        log.write_text(text.rstrip() + "\n" + DEFECT_ENTRIES, encoding="utf-8")
        print(f"  {log.name:<58} appended section D (DEF-17 to DEF-21)")

    edits = update_backlog(args.check)
    for e in edits:
        print(f"  backlog: {e}")

    print(f"\n{total} replacement(s), {len(edits)} backlog edit(s)"
          + ("  (check mode)" if args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
