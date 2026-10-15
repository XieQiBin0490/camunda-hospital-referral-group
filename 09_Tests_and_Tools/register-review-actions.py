#!/usr/bin/env python3
"""Register the five review actions in the backlog workbook.

The review list (database persistence, RBAC, BPMN model defects, form input
validation, form field types) was being worked on but appeared nowhere in the
product or sprint backlog, so the task board could not evidence it - which is what
a marked standup is assessed on, and what the brief's "every activity must have a
first owner and a second owner, an estimate, acceptance conditions, dependencies
and a status" requires.

Rows are appended to the existing sheets with the style of the row above, so the
workbook keeps its look. Existing rows and every other sheet are untouched.

usage: python register-review-actions.py [--check]
"""

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "01_Agile_Planning" / ("Hospital_Patient_System_Project_Backlog_"
                                    "按评价逐项修正最终版.xlsx")

DONE = "Done\n完成"
WIP = "In progress\n进行中"
TODO = "Not started\n未开始"

# ID, story, workstream, priority, points, sprint, letter, 1st, 2nd, depends,
# acceptance, which mark, status, hours
PRODUCT_ROWS = [
    ["PB-45",
     "As a hospital service, I want referral, appointment, funding, payment and refund "
     "records to survive a restart, so that a finished episode can still be audited",
     "Building the System\n系统实现", "Must\n必须", "8", "S4\n冲刺4", "B", "finn", "max",
     "PB-25..PB-28",
     "A restart of the application loses no referral, appointment, funding, payment or "
     "refund record. The store is a database with a schema and a migration, not the "
     "in-process HospitalStore.",
     "Portfolio Task 04 evidence; review action 1", TODO, "20"],
    ["PB-46",
     "As a member of a hospital team, I want Tasklist to offer me only the tasks my role "
     "is authorised to claim, so that clinical, administrative and financial authority "
     "stay separated",
     "Building the System\n系统实现", "Must\n必须", "8", "S4\n冲刺4", "D", "peter", "finn",
     "PB-27, FB-11",
     "A user outside a task's candidateGroups cannot see, claim or complete it. The nine "
     "candidate groups used by the models resolve to real Identity users and groups, and "
     "an access check runs as a regression test.",
     "Portfolio Task 03 RBAC gap; review action 2; FB-11", TODO, "20"],
    ["PB-47",
     "As a reviewer, I want every decision to leave a task through a gateway with a "
     "condition, so that the model routes on the decision it records",
     "Operational BPMN\n操作级BPMN", "Must\n必须", "5", "S3\n冲刺3", "A", "max", "peter",
     "PB-31",
     "No user task has more than one unconditional outgoing flow; no gateway branches on "
     "a variable that no form and no worker supplies; a fresh lint and structural pass "
     "reports zero findings.",
     "Portfolio Task 01; review action 3", WIP, "8"],
    ["PB-48",
     "As an operator, I want a form to refuse an empty or malformed answer, so that a "
     "gateway never branches on a value nobody supplied",
     "Camunda Forms\n表单", "Must\n必须", "5", "S3\n冲刺3", "D", "peter", "finn",
     "PB-27",
     "Every variable a gateway branches on is required in the form that collects it; "
     "patientId is required with a format rule; submitting a blank form is rejected. "
     "validate-form-controls.py reports zero form problems.",
     "Portfolio Task 04; review action 4", DONE, "8"],
    ["PB-49",
     "As an operator, I want each business data item collected with the control that "
     "fits it, so that the value a form submits is the value the model expects",
     "Camunda Forms\n表单", "Must\n必须", "5", "S3\n冲刺3", "D", "peter", "henry",
     "PB-27",
     "No numeric or date quantity is collected in a text box; every controlled decision "
     "value is a select whose option values match the FEEL literals exactly; "
     "validate-forms.py and validate-contract.py are clean.",
     "Portfolio Task 04; review action 5", DONE, "10"],
]

# Task ID, PB ref, story, daily plan, 1st, letter, 2nd, hours, priority, status,
# acceptance, depends
SPRINT3_ROWS = [
    ["S3-21", "PB-49",
     "Correct the control type of every form field that holds date, number or "
     "controlled-decision data; replace the four checkboxes bound to numeric gateway "
     "variables with number controls and the six free-text decision fields with selects",
     "D1-D2", "peter", "D", "henry", "10", "Must\n必须", DONE,
     "10 control types corrected; 41 controls added for data the workers already read; "
     "controls go 2 types to 6; validate-forms.py clean",
     "S3-14"],
    ["S3-22", "PB-48",
     "Add input validation to the forms: make every variable a gateway branches on "
     "required, and give patientId a required format rule",
     "D1-D2", "peter", "D", "finn", "8", "Must\n必须", DONE,
     "115 fields carry a rule; 24 of 25 gateway variables collected and required; all 91 "
     "patientId values in the delivered evidence pass the new pattern; "
     "validate-form-controls.py clean",
     "S3-14, S3-21"],
    ["S3-23", "PB-47",
     "Fix the BPMN defects the review named and the four further defects the form work "
     "exposed: two tasks that split without a gateway, the S1 variable no form supplies, "
     "the misplaced follow-up field",
     "D2-D4", "max", "A", "peter", "8", "Must\n必须", WIP,
     "Structural pass clean for every delivered model; the four newly found defects are "
     "either fixed or recorded in the defect log with an owner",
     "S3-02..S3-07"],
    ["S3-24", "PB-45",
     "Specify the persistence design for the second release: schema for the episode, "
     "referral, appointment, funding, payment and refund records, and the migration from "
     "the in-process store",
     "D4-D5", "finn", "B", "max", "6", "Must\n必须", TODO,
     "A written schema and migration plan exists, and the second-release backlog carries "
     "the implementation as PB-45",
     "S3-18"],
    ["S3-25", "PB-46",
     "Specify the role-based access design: map the nine candidate groups the models "
     "already declare to Identity users and groups, and say which Tasklist permission "
     "each needs",
     "D4-D5", "peter", "D", "finn", "6", "Must\n必须", TODO,
     "A group-to-permission table exists; the second-release backlog carries the "
     "implementation as PB-46; FB-11 records why it was not implemented in the initial "
     "release",
     "S3-18"],
]


def append(ws, rows, first_data_row):
    """Append rows below the existing data, borrowing the style of the row above."""
    template = ws[ws.max_row]
    start = ws.max_row + 1
    for i, values in enumerate(rows):
        r = start + i
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            src = template[c - 1]
            if src.has_style:
                # _style carries font, fill, border, number format and alignment
                cell._style = src._style
    return start, start + len(rows) - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    wb = load_workbook(BOOK)
    before = {ws.title: (ws.max_row, ws.max_column) for ws in wb.worksheets}

    # refuse to double-register
    for sheet, ids in (("Project Backlog", [r[0] for r in PRODUCT_ROWS]),
                       ("Sprint 3 Backlog", [r[0] for r in SPRINT3_ROWS])):
        existing = {str(ws.cell(row=r, column=1).value)
                    for ws in [wb[sheet]] for r in range(1, ws.max_row + 1)}
        clash = [i for i in ids if i in existing]
        if clash:
            print(f"{sheet}: already registered: {clash}")
            return 0

    for sheet, rows in (("Project Backlog", PRODUCT_ROWS),
                        ("Sprint 3 Backlog", SPRINT3_ROWS)):
        ws = wb[sheet]
        a, b = append(ws, rows, 1)
        print(f"{sheet}: added {len(rows)} rows ({a}-{b})")

    if args.check:
        print("(check mode - nothing written)")
        return 0

    wb.save(BOOK)
    print(f"saved {BOOK.name}")

    wb2 = load_workbook(BOOK)
    for ws in wb2.worksheets:
        if ws.title in before:
            print(f"  {ws.title:<22} {before[ws.title]} -> {(ws.max_row, ws.max_column)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
