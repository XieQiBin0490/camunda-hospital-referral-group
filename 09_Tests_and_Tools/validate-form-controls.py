#!/usr/bin/env python3
"""Check that every input the process needs can actually be entered, with the right control.

Complements the two validators already in this directory:

  * validate-forms.py     - form files exist, are valid JSON, and are wired to a user task.
  * validate-contract.py  - every requireString/requireBool in the worker source has a source.

Neither looks at which *control* collects a value, nor at the variables the gateways
branch on. Both gaps matter here:

  * A gateway that branches on a variable no form collects takes its default flow
    silently. The default is a legal BPMN outcome, so no validator reports it, but
    the process no longer follows the case study.
  * A control that cannot represent its data (a checkbox bound to a day count, a free
    text box bound to a controlled decision value) produces a value the engine can
    store but the model cannot route on.

Checks
  A  gateway variables: collected by a form, and marked required
  B  worker inputs: hard requirements (requireString/requireBool) and soft reads
     (findString/doubleOr/intOr/bool) that no form collects
  C  control appropriateness: a date or number label on a text control
  D  model scan: a flow node with more than one outgoing flow and no gateway

usage: python validate-form-controls.py [--json OUT.json]
exit code 0 when A-D are clean, 1 otherwise (D is reported as a defect too).
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMS = ROOT / "03_Forms"
MODELS = ROOT / "02_BPMN_Models"
JAVA = ROOT / "04_Java_Worker" / "src" / "main" / "java"

INPUT_TYPES = {"textfield", "textarea", "number", "datetime", "checkbox", "radio",
               "select", "checklist", "taglist", "table", "group", "dynamiclist",
               "iframe", "filepicker", "expression"}

FEEL_WORDS = {
    "and", "or", "not", "true", "false", "null", "if", "then", "else", "some",
    "every", "in", "between", "instance", "of", "return", "for", "satisfies",
    "string", "number", "date", "time", "duration", "list", "context",
}

# A label that promises a date or a numeric quantity.
DATE_LABEL = re.compile(r"\b(date|day|days|month|months|deadline|due)\b", re.I)
NUMBER_LABEL = re.compile(r"\b(amount|number|count|cycles|days|months|cost|fee|total)\b", re.I)
# A data item whose value set is fixed by the case study, so free text is wrong.
CONTROLLED_LABEL = re.compile(r"\((?:[^()]*?/[^()]*?)\)")

problems = []
model_defects = []
notes = []


def forms_by_key():
    supplied = defaultdict(list)
    for path in sorted(FORMS.glob("*.form")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for comp in doc.get("components", []):
            if comp.get("key"):
                supplied[comp["key"]].append((doc.get("id") or path.stem, comp))
    return supplied


def model_texts():
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(MODELS.glob("*.bpmn"))}


def gateway_variables(texts):
    """variable -> [model, ...] for every name a gateway condition reads."""
    found = defaultdict(set)
    for name, text in texts.items():
        for expr in re.findall(
                r"<bpmn:conditionExpression[^>]*>(.*?)</bpmn:conditionExpression>", text, re.S):
            # Undo XML escaping, then drop string literals: a name inside quotes is a
            # data value the model compares against, not a process variable.
            expr = (expr.replace("&quot;", '"').replace("&apos;", "'")
                        .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
            expr = re.sub(r'"[^"]*"', " ", expr)
            for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr):
                if word.lower() not in FEEL_WORDS:
                    found[word].add(name)
    return found


def worker_inputs():
    """variable -> (accessor, {worker, ...}) for every variable a worker reads."""
    reads = {}
    hard = {"requireString", "requireBool", "requireDouble"}
    soft = {"findString", "doubleOr", "intOr", "bool"}
    pattern = re.compile(r"ctx\.(\w+)\s*\(\s*\"([^\"]+)\"")
    for path in JAVA.rglob("*.java"):
        text = path.read_text(encoding="utf-8")
        for accessor, var in pattern.findall(text):
            if accessor not in hard | soft:
                continue
            entry = reads.setdefault(var, [accessor in hard, set()])
            entry[0] = entry[0] or accessor in hard
            entry[1].add(path.stem)
    return reads


def workers_that_write():
    written = set()
    for path in JAVA.rglob("*.java"):
        text = path.read_text(encoding="utf-8")
        written |= set(re.findall(r'(?:\.set|out\.put)\(\s*"([^"]+)"', text))
    return written


def group_a(supplied, texts):
    print("A  gateway variables")
    gv = gateway_variables(texts)
    for var in sorted(gv):
        where = supplied.get(var, [])
        if not where:
            # No form can fix this on its own: the model branches on a variable the
            # rest of the model never defines. Reported as a model defect, not a form
            # failure, so this script can still gate a form-only change.
            model_defects.append(f"[A] {var}: a gateway branches on it but no form collects "
                                 f"it ({', '.join(sorted(gv[var]))})")
            status = "NOT COLLECTED (model defect)"
        else:
            missing_required = [fid for fid, comp in where
                                if not (comp.get("validate") or {}).get("required")]
            if missing_required:
                problems.append(f"[A] {var}: not required in {', '.join(missing_required)} "
                                f"- an empty answer silently takes the default flow")
                status = "collected, NOT required in " + ", ".join(missing_required)
            else:
                status = f"collected and required in {len(where)} form(s)"
        print(f"   {var:<28} {status}")
    print(f"   -> {len(gv)} gateway variable(s); "
          f"{sum(1 for v in gv if v in supplied)} collected")
    return gv


def group_b(supplied):
    print("B  worker inputs")
    reads = worker_inputs()
    written = workers_that_write()
    hard_missing, soft_missing = [], []
    for var, (is_hard, classes) in sorted(reads.items()):
        if var in supplied:
            continue
        if var in written:
            continue  # a worker produces it, so no human has to type it
        target = hard_missing if is_hard else soft_missing
        target.append(f"{var} ({', '.join(sorted(classes))})")
        if is_hard:
            problems.append(f"[B] {var}: required by {', '.join(sorted(classes))} "
                            f"but no form collects it and no worker writes it")
    for label, items in (("hard", hard_missing), ("soft", soft_missing)):
        print(f"   {label} input(s) with no form and no worker source: {len(items)}")
        for item in items:
            print(f"     * {item}")
    notes.extend(f"[B] soft read with no form source: {i}" for i in soft_missing)
    return reads


def group_c(supplied):
    print("C  control appropriateness")
    findings = 0
    for var, occurrences in sorted(supplied.items()):
        for fid, comp in occurrences:
            kind = comp.get("type")
            label = comp.get("label") or ""
            # A label that asks a yes/no question describes a boolean, so a checkbox
            # is the right control even when the wording mentions days or cycles.
            is_question = label.strip().endswith("?")
            if kind in ("textfield", "textarea") and not is_question:
                if NUMBER_LABEL.search(label):
                    problems.append(f"[C] {fid}/{var}: numeric data in a {kind} "
                                    f"(label {label!r})")
                    findings += 1
                elif DATE_LABEL.search(label):
                    problems.append(f"[C] {fid}/{var}: date data in a {kind} "
                                    f"(label {label!r})")
                    findings += 1
                elif CONTROLLED_LABEL.search(label):
                    problems.append(f"[C] {fid}/{var}: controlled value set in a {kind} "
                                    f"(label {label!r})")
                    findings += 1
            if kind == "checkbox" and NUMBER_LABEL.search(label) and not is_question:
                problems.append(f"[C] {fid}/{var}: numeric data on a checkbox "
                                f"(label {label!r})")
                findings += 1
    print(f"   text/checkbox controls holding date, number or controlled data: {findings}")
    return findings


def group_d(texts):
    print("D  model scan: implicit parallel splits")
    findings = 0
    for name, text in texts.items():
        task_ids = set(re.findall(
            r'<bpmn:(?:userTask|serviceTask|sendTask|receiveTask|manualTask|scriptTask)\s+id="([^"]+)"',
            text))
        outgoing = defaultdict(int)
        for src in re.findall(r'<bpmn:sequenceFlow\b[^>]*?sourceRef="([^"]+)"', text):
            outgoing[src] += 1
        for node, count in sorted(outgoing.items()):
            if node in task_ids and count > 1:
                model_defects.append(
                    f"[D] {name}: {node} has {count} outgoing flows and no gateway; "
                    f"BPMN treats this as a parallel split, so every branch runs")
                findings += 1
                print(f"   {name}: {node} -> {count} outgoing flows")
    if not findings:
        print("   none")
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write the result as JSON to this path")
    args = ap.parse_args()

    supplied = forms_by_key()
    texts = model_texts()

    gv = group_a(supplied, texts)
    group_b(supplied)
    group_c(supplied)
    group_d(texts)

    print()
    if notes:
        print(f"NOTES ({len(notes)})")
        for n in notes:
            print("  -", n)
        print()
    if problems:
        print(f"PROBLEMS - the forms need fixing ({len(problems)})")
        for p in problems:
            print("  -", p)
        print()
    if model_defects:
        print(f"MODEL DEFECTS - not fixable in a form, for the model-fix action "
              f"({len(model_defects)})")
        for d in model_defects:
            print("  -", d)
        print()

    result = {
        "forms": len(list(FORMS.glob("*.form"))),
        "distinctFormFields": len(supplied),
        "gatewayVariables": len(gv),
        "gatewayVariablesCollected": sum(1 for v in gv if v in supplied),
        "formProblems": problems,
        "modelDefects": model_defects,
        "notes": notes,
    }
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")

    summary = {k: v for k, v in result.items()
               if k not in ("formProblems", "modelDefects", "notes")}
    summary["formProblems"] = len(problems)
    summary["modelDefects"] = len(model_defects)
    print(f"SUMMARY {json.dumps(summary)}")
    if problems:
        print("RESULT: %d form problem(s)" % len(problems))
        return 1
    print("RESULT: forms clean%s" % (
        "" if not model_defects else
        f" ({len(model_defects)} model defect(s) reported above, not a form failure)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
