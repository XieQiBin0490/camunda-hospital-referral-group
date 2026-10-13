#!/usr/bin/env python3
"""Show what the form field-type correction changes at run time, without a cluster.

Why this exists
---------------
A form change only affects a run when a person works the task in Tasklist. The
project's automated evidence (run-worker-demo.mjs, run-acceptance.mjs) sets process
variables through the Zeebe API, which never renders a form and never runs form
validation - so re-running it shows no difference at all. That makes the correction
hard to demonstrate, and a reviewer is entitled to ask "so what actually changes?".

This script answers that question from the models themselves. For every gateway whose
condition reads one of the corrected variables, it evaluates the conditions twice:

  * once with the value the superseded control produced (a checkbox emits true/false;
    a free text box emits whatever the user typed, for example "Accept")
  * once with the value the corrected control produces (a number control emits a
    number; a select can only emit one of the modelled literals)

and reports which outgoing sequence flow is selected each time. Where the two differ,
the corrected form changes which path the instance takes - which is exactly what a
Tasklist demonstration would show.

The FEEL subset evaluated here is deliberately small and covers every condition form
these models use: `var = "literal"`, `var = true|false`, and `var <= >= < > number`.
A comparison whose operand type does not match evaluates to null, and Zeebe treats a
null condition as not satisfied, so the gateway falls through to its default flow.

usage: python demo-form-control-impact.py [--markdown OUT.md]
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "02_BPMN_Models"

# variable, value the OLD control produced, value the NEW control produces, description
CASES = [
    ("letterDelayDays", True, 3,
     "checkbox ticked -> number 3"),
    ("letterAgeMonths", True, 2,
     "checkbox ticked -> number 2"),
    ("letterAgeMonths", True, 4,
     "checkbox ticked -> number 4"),
    ("referralDecision", "Accept", "accepted",
     'free text copied from the label ("Accept") -> select value "accepted"'),
    ("enquiryType", "Administrative", "administrative",
     'capitalised free text -> select value "administrative"'),
    ("referralUrgency", "Urgent", "urgent",
     'capitalised free text -> select value "urgent"'),
    ("paymentStatus", "Confirmed", "confirmed",
     'capitalised free text -> select value "confirmed"'),
]

COND = re.compile(r"^(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*"
                  r"(?P<op><=|>=|!=|=|<|>)\s*(?P<rhs>.+)$")
NUM = re.compile(r"^-?\d+(\.\d+)?$")

WHY = {"condition": "a condition was satisfied",
       "default": "no condition satisfied, so it fell through to the default flow",
       "none": "no flow could be selected"}


def unescape(text):
    return (text.replace("&quot;", '"').replace("&apos;", "'")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))


def parse(model_path):
    """Return (gateways, flows, names) for one model file."""
    xml = unescape(model_path.read_text(encoding="utf-8"))

    names = {}
    for m in re.finditer(r'<bpmn:(?:userTask|serviceTask|sendTask|startEvent|endEvent|'
                         r'intermediateCatchEvent|boundaryEvent|exclusiveGateway|task)'
                         r'\s+id="([^"]+)"[^>]*?(?:\sname="([^"]*)")?', xml):
        names[m.group(1)] = m.group(2) or m.group(1)

    gateways = {}
    for m in re.finditer(r'<bpmn:exclusiveGateway\s+id="([^"]+)"(.*?)>', xml, re.S):
        gid, attrs = m.group(1), m.group(2)
        dm = re.search(r'default="([^"]+)"', attrs)
        nm = re.search(r'name="([^"]*)"', attrs)
        gateways[gid] = {"default": dm.group(1) if dm else None,
                         "name": nm.group(1) if nm else gid}

    flows = {}
    for m in re.finditer(r'<bpmn:sequenceFlow\s+id="([^"]+)"(.*?)(?:/>|>(.*?)</bpmn:sequenceFlow>)',
                         xml, re.S):
        fid, attrs, body = m.group(1), m.group(2), m.group(3) or ""
        src = re.search(r'sourceRef="([^"]+)"', attrs)
        tgt = re.search(r'targetRef="([^"]+)"', attrs)
        nm = re.search(r'name="([^"]*)"', attrs)
        cond = re.search(r"<bpmn:conditionExpression[^>]*>(.*?)</bpmn:conditionExpression>",
                         body, re.S)
        flows[fid] = {"id": fid,
                      "source": src.group(1) if src else None,
                      "target": tgt.group(1) if tgt else None,
                      "name": nm.group(1) if nm else "",
                      "condition": cond.group(1).strip() if cond else None}
    return gateways, flows, names


def evaluate(condition, value):
    """True / False / None(null). None means the comparison could not be made."""
    expr = condition.lstrip("=").strip()
    m = COND.match(expr)
    if not m:
        return None
    op, rhs = m.group("op"), m.group("rhs").strip()

    if rhs in ("true", "false"):
        literal = rhs == "true"
    elif rhs.startswith('"') and rhs.endswith('"'):
        literal = rhs[1:-1]
    elif NUM.match(rhs):
        literal = float(rhs)
    else:
        return None

    if op == "=":
        return value == literal
    if op == "!=":
        return value != literal

    # ordering comparisons need two numbers; anything else is a type error -> null
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isinstance(literal, float):
        return None
    return {"<": value < literal, "<=": value <= literal,
            ">": value > literal, ">=": value >= literal}[op]


def select_flow(gid, gateways, flows, variables):
    """The flow an exclusive gateway takes: first satisfied condition, else default."""
    outgoing = [f for f in flows.values() if f["source"] == gid]
    for flow in outgoing:
        if flow["condition"] is None:
            continue
        verdict = None
        for var, value in variables.items():
            if re.match(r"^\s*=?\s*" + re.escape(var) + r"\b", flow["condition"]):
                verdict = evaluate(flow["condition"], value)
                break
        if verdict is True:
            return flow, "condition"
    default = gateways[gid]["default"]
    if default and default in flows:
        return flows[default], "default"
    return None, "none"


def label(flow, names):
    if flow is None:
        return "NO FLOW SELECTABLE"
    target = names.get(flow["target"], flow["target"])
    branch = flow["name"] or "(unnamed)"
    return f"{branch} -> {target}"


def verdict_of(before, after, reason_before, reason_after):
    if before is None or after is None:
        return "NO FLOW SELECTABLE", True
    if before["target"] != after["target"]:
        return "DIFFERENT PATH", True
    if reason_before != reason_after:
        return "same target, reached for a different reason", False
    return "identical", False


def collect(parsed):
    rows = []
    for variable, old_value, new_value, description in CASES:
        for name, (gateways, flows, names) in parsed.items():
            for gid, gw in gateways.items():
                outgoing = [f for f in flows.values() if f["source"] == gid]
                if not any(f["condition"] and
                           re.match(r"^\s*=?\s*" + re.escape(variable) + r"\b", f["condition"])
                           for f in outgoing):
                    continue
                before, why_before = select_flow(gid, gateways, flows, {variable: old_value})
                after, why_after = select_flow(gid, gateways, flows, {variable: new_value})
                verdict, changes = verdict_of(before, after, why_before, why_after)
                rows.append({
                    "model": name, "gateway": gid, "gatewayName": gw["name"],
                    "variable": variable, "description": description,
                    "old": old_value, "new": new_value,
                    "before": label(before, names), "after": label(after, names),
                    "verdict": verdict, "changes": changes,
                    "whyBefore": WHY[why_before], "whyAfter": WHY[why_after],
                })
    return rows


def emit_console(rows):
    print("=" * 100)
    print("WHAT THE FIELD-TYPE CORRECTION CHANGES AT RUN TIME")
    print("computed from the gateway conditions and default flows in 02_BPMN_Models/")
    print("=" * 100)
    for row in rows:
        print()
        print(f"{row['model']}  {row['gateway']}  \"{row['gatewayName']}\"")
        print(f"  variable  : {row['variable']}   ({row['description']})")
        print(f"  before fix: value {row['old']!r:>14}  ->  {row['before']}")
        print(f"              ({row['whyBefore']})")
        print(f"  after fix : value {row['new']!r:>14}  ->  {row['after']}")
        print(f"              ({row['whyAfter']})")
        print(f"  verdict   : {row['verdict']}")
    changed = sum(1 for r in rows if r["changes"])
    print()
    print(f"gateway decisions compared: {len(rows)}")
    print(f"decisions that change path: {changed}")
    return changed


def emit_markdown(rows, path):
    lines = [
        "## Computed gateway decisions",
        "",
        "For each gateway that branches on a corrected field: which flow is selected when the",
        "value comes from the superseded control, and which when it comes from the corrected one.",
        "Computed by `09_Tests_and_Tools/demo-form-control-impact.py` from the condition",
        "expressions and `default` attributes in the models themselves.",
        "",
        "| Model | Gateway | Variable | Before the fix | After the fix | Verdict |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(f"| `{row['model'].replace('.bpmn', '')}` | `{row['gateway']}` | `{row['variable']}` "
                     f"| `{row['old']!r}` → {row['before']}<br>*{row['whyBefore']}* "
                     f"| `{row['new']!r}` → {row['after']}<br>*{row['whyAfter']}* "
                     f"| {row['verdict']} |")
    changed = sum(1 for r in rows if r["changes"])
    lines += ["", f"**{changed} of {len(rows)} gateway decisions change path.**", ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nmarkdown written to {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", help="also write the table as markdown to this path")
    args = ap.parse_args()

    parsed = {p.name: parse(p) for p in sorted(MODELS.glob("*.bpmn"))}
    rows = collect(parsed)
    emit_console(rows)
    if args.markdown:
        emit_markdown(rows, args.markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
