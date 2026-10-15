#!/usr/bin/env python3
"""Fix the four BPMN and form defects left open by the defect log.

Each fix is grounded in the case study, and each is written so that running the script
twice changes nothing.

  DEF-M1  S3 T_RefundDecision has two unconditional outgoing flows. The case study (para
          15) makes this a genuine choice - the Finance Team decides whether a refund is
          appropriate - so the split needs an exclusive gateway and a condition. The form
          already collects refundDecision, so nothing else has to change.
  DEF-M2  O1 and S3 T_AuthoriseUrgentTreatment also have two unconditional outgoing flows,
          but here BOTH branches are meant to run: para 14 requires the treatment to
          proceed AND the reason to be referred to the Finance Team. BPMN already treats
          it as a parallel split, so the model behaves correctly; what is missing is an
          explicit parallel gateway making that intent visible instead of implicit.
  DEF-M3  S1 branches on an `accepted` boolean that no form collects, so G_Accepted can
          never leave its default flow. The rest of the suite uses the controlled
          `referralDecision`; S1 is brought into line, and because form-register-referral
          is shared with S2 - where para 5 forbids the Medical Secretaries from deciding
          acceptance - S1 gets its own landscape form rather than a field added to the
          shared one.
  DEF-F1  form-prepare-accessible-format collects followUpSlotWithinPeriod, a follow-up
          booking flag that belongs to the follow-up forms.
  DEF-F2  Three worker inputs have no form anywhere, so their value can only ever be the
          worker's own default: documentationCheckResult, letterRecipients and
          refundAuthorised. Each is added to the user task that precedes the worker.

usage: python fix-model-defects.py [--check]
"""

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "02_BPMN_Models"
FORMS = ROOT / "03_Forms"

changes = []


def note(msg):
    changes.append(msg)
    print("  " + msg)


# --------------------------------------------------------------------------- #
# BPMN
# --------------------------------------------------------------------------- #

def edit(path, pairs, label):
    """Apply literal replacements, asserting each anchor is present exactly once."""
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in pairs:
        n = text.count(old)
        if n != 1:
            print(f"  !! {path.name}: anchor found {n} times, skipping {label}: {old[:60]!r}")
            return False
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        note(f"{path.name}: {label}")
    else:
        print(f"  = {path.name}: {label} already applied")
    return True


def fix_refund_gateway(check):
    """DEF-M1: insert an exclusive gateway after T_RefundDecision in S3."""
    p = MODELS / "S3_Strategic_Treatment_To_Aftercare.bpmn"
    if check:
        print("  (check) would insert G_RefundDecision in S3")
        return
    q = "&quot;"
    # 1. the task now leaves only to the new gateway
    edit(p, [(
        '<bpmn:outgoing>F_G12</bpmn:outgoing>\n      <bpmn:outgoing>F_G16</bpmn:outgoing>\n    </bpmn:userTask>',
        '<bpmn:outgoing>F_G12</bpmn:outgoing>\n    </bpmn:userTask>\n'
        '    <bpmn:exclusiveGateway id="G_RefundDecision" name="Payment refunded, retained or transferred?" default="F_G16">\n'
        '      <bpmn:incoming>F_G12</bpmn:incoming>\n'
        '      <bpmn:outgoing>F_G122</bpmn:outgoing>\n'
        '      <bpmn:outgoing>F_G16</bpmn:outgoing>\n'
        '    </bpmn:exclusiveGateway>')], "insert G_RefundDecision")
    # 2. F_G12 becomes task -> gateway; F_G122 carries the refund branch; F_G16 becomes the default
    edit(p, [(
        '<bpmn:sequenceFlow id="F_G12" name="Refund approved" sourceRef="T_RefundDecision" targetRef="T_RequestRefund">\n    </bpmn:sequenceFlow>',
        '<bpmn:sequenceFlow id="F_G12" name="Decision recorded" sourceRef="T_RefundDecision" targetRef="G_RefundDecision">\n    </bpmn:sequenceFlow>\n'
        '    <bpmn:sequenceFlow id="F_G122" name="Refund approved" sourceRef="G_RefundDecision" targetRef="T_RequestRefund">\n'
        f'      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">= refundDecision = {q}refunded{q}</bpmn:conditionExpression>\n'
        '    </bpmn:sequenceFlow>')], "rewire F_G12 and add F_G122")
    edit(p, [(
        '<bpmn:sequenceFlow id="F_G16" name="Payment retained or transferred" sourceRef="T_RefundDecision" targetRef="T_OfferAnotherAppointment">\n    </bpmn:sequenceFlow>',
        '<bpmn:sequenceFlow id="F_G16" name="Payment retained or transferred" sourceRef="G_RefundDecision" targetRef="T_OfferAnotherAppointment">\n    </bpmn:sequenceFlow>')],
        "re-source F_G16 from the gateway")
    # 3. T_RequestRefund's incoming now comes from the gateway
    edit(p, [('<bpmn:incoming>F_G12</bpmn:incoming>\n      <bpmn:outgoing>F_G13</bpmn:outgoing>',
              '<bpmn:incoming>F_G122</bpmn:incoming>\n      <bpmn:outgoing>F_G13</bpmn:outgoing>')],
         "point T_RequestRefund at F_G122")


def retarget_flow(path, flow_id, new_source, label):
    """Point an existing sequence flow at a new source, handling both a self-closing tag
    and one with a body - the two files serialise flows differently."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r'<bpmn:sequenceFlow id="%s"[^>]*?>' % flow_id, text)
    if not m:
        print(f"  !! {path.name}: {flow_id} not found")
        return False
    tag = m.group(0)
    if 'sourceRef=' not in tag:
        print(f"  !! {path.name}: {flow_id} has no sourceRef")
        return False
    new_tag = re.sub(r'sourceRef="[^"]*"', f'sourceRef="{new_source}"', tag)
    if new_tag == tag:
        print(f"  = {path.name}: {flow_id} already sourced from {new_source}")
        return True
    path.write_text(text[:m.start()] + new_tag + text[m.end():], encoding="utf-8")
    note(f"{path.name}: {label}")
    return True


def fix_parallel_gateways(check):
    """DEF-M2: make the urgent-treatment AND-split explicit in O1 and S3."""
    for name, task, gid, f_a, f_b in (
            ("O1_Operational_Merged.bpmn", "T_AuthoriseUrgentTreatment",
             "G_UrgentTreatmentAuthorised", "F_3_28", "F_3_29"),
            ("S3_Strategic_Treatment_To_Aftercare.bpmn", "T_AuthoriseUrgentTreatment",
             "G_UrgentTreatmentAuthorised", "F_D22", "F_D23")):
        p = MODELS / name
        if check:
            print(f"  (check) would insert {gid} in {name}")
            continue
        new_in = f_a + "a"
        # 1. the task leaves only to the new gateway
        edit(p, [(
            f'<bpmn:outgoing>{f_a}</bpmn:outgoing>\n      <bpmn:outgoing>{f_b}</bpmn:outgoing>\n    </bpmn:userTask>',
            f'<bpmn:outgoing>{new_in}</bpmn:outgoing>\n    </bpmn:userTask>\n'
            f'    <bpmn:parallelGateway id="{gid}" name="Treatment proceeds and the reason is referred to Finance">\n'
            f'      <bpmn:incoming>{new_in}</bpmn:incoming>\n'
            f'      <bpmn:outgoing>{f_a}</bpmn:outgoing>\n'
            f'      <bpmn:outgoing>{f_b}</bpmn:outgoing>\n'
            f'    </bpmn:parallelGateway>')], f"insert {gid}")
        # 2. the split flow, inserted immediately before the first branch flow
        text = p.read_text(encoding="utf-8")
        m = re.search(r'<bpmn:sequenceFlow id="%s"[^>]*?>' % f_a, text)
        if m and new_in not in text:
            p.write_text(text[:m.start()]
                         + f'<bpmn:sequenceFlow id="{new_in}" sourceRef="{task}" targetRef="{gid}" />\n    '
                         + text[m.start():], encoding="utf-8")
            note(f"{name}: insert {new_in}")
        else:
            print(f"  = {name}: {new_in} step already applied")
        # 3. the two branches now leave the gateway
        retarget_flow(p, f_a, gid, f"re-source {f_a} from {gid}")
        retarget_flow(p, f_b, gid, f"re-source {f_b} from {gid}")


def fix_s1_decision(check):
    """DEF-M3: S1 branches on the controlled referralDecision, from its own form."""
    p = MODELS / "S1_Strategic_Landscape.bpmn"
    if check:
        print("  (check) would repoint S1 G_Accepted at referralDecision")
        return
    text = p.read_text(encoding="utf-8")
    if text.count('formId="form-register-referral"') != 1:
        print(f"  !! S1: expected one form-register-referral reference, "
              f"found {text.count('formId=\"form-register-referral\"')}")
    else:
        p.write_text(text.replace('formId="form-register-referral"',
                                  'formId="form-register-referral-landscape"'), encoding="utf-8")
        note("S1_Strategic_Landscape.bpmn: point T_Register at the landscape form")
    edit(p, [(
        '<bpmn:sequenceFlow id="F_6" name="Accepted" sourceRef="G_Accepted" targetRef="T_BookAppointment">\n'
        '      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">= accepted = true</bpmn:conditionExpression>',
        '<bpmn:sequenceFlow id="F_6" name="Accepted" sourceRef="G_Accepted" targetRef="T_BookAppointment">\n'
        '      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">= referralDecision = "accepted"</bpmn:conditionExpression>')],
        "F_6 condition -> referralDecision")
    edit(p, [(
        '<bpmn:sequenceFlow id="F_7" name="Not accepted" sourceRef="G_Accepted" targetRef="T_NotifyOutcome">\n'
        '      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">= accepted = false</bpmn:conditionExpression>\n'
        '    </bpmn:sequenceFlow>',
        '<bpmn:sequenceFlow id="F_7" name="Not accepted" sourceRef="G_Accepted" targetRef="T_NotifyOutcome">\n'
        '    </bpmn:sequenceFlow>')], "F_7 becomes a true default flow")


def new_landscape_form():
    """The S1 registration form: documentation completeness plus the decision."""
    src = json.loads((FORMS / "form-register-referral.form").read_text(encoding="utf-8"),
                     object_pairs_hook=OrderedDict)
    doc = OrderedDict()
    for k, v in src.items():
        doc[k] = v
    doc["id"] = "form-register-referral-landscape"
    comps = []
    for c in src["components"]:
        if c.get("type") == "text":
            c = OrderedDict(c)
            c["id"] = "Header_form-register-referral-landscape"
            c["text"] = "# Register the referral, confirm identification and record the decision"
            comps.append(c)
            continue
        if c.get("key") in ("transferDecision", "referralDecision"):
            continue
        comps.append(c)
    comps.append(OrderedDict([
        ("type", "select"), ("key", "referralDecision"),
        ("label", "Referral decision after documentation review"),
        ("values", [
            OrderedDict([("label", "Accepted"), ("value", "accepted")]),
            OrderedDict([("label", "Rejected"), ("value", "rejected")]),
            OrderedDict([("label", "Information required"), ("value", "information required")]),
            OrderedDict([("label", "Redirected"), ("value", "redirected")]),
        ]),
        ("validate", OrderedDict([("required", True)])),
    ]))
    doc["components"] = comps
    return doc


def fix_forms(check):
    """DEF-F1 and DEF-F2."""
    if not check:
        p = FORMS / "form-register-referral-landscape.form"
        if not p.exists():
            p.write_text(json.dumps(new_landscape_form(), indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
            note("created form-register-referral-landscape.form")

    def load(name):
        return json.loads((FORMS / f"{name}.form").read_text(encoding="utf-8"),
                          object_pairs_hook=OrderedDict)

    def save(name, doc):
        (FORMS / f"{name}.form").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def drop(name, key):
        doc = load(name)
        before = len(doc["components"])
        doc["components"] = [c for c in doc["components"] if c.get("key") != key]
        if len(doc["components"]) < before:
            if check:
                print(f"  (check) would remove {key} from {name}")
            else:
                save(name, doc)
                note(f"{name}: removed misplaced field {key}")
        else:
            print(f"  = {name}: {key} not present")

    def add(name, comp):
        doc = load(name)
        if any(c.get("key") == comp["key"] for c in doc["components"]):
            print(f"  = {name}: {comp['key']} already present")
            return
        if check:
            print(f"  (check) would add {comp['key']} to {name}")
            return
        doc["components"].append(comp)
        save(name, doc)
        note(f"{name}: added {comp['key']}")

    drop("form-prepare-accessible-format", "followUpSlotWithinPeriod")

    add("form-check-referral-documents", OrderedDict([
        ("type", "select"), ("key", "documentationCheckResult"),
        ("label", "Documentation check outcome"),
        ("values", [OrderedDict([("label", "Complete"), ("value", "complete")]),
                    OrderedDict([("label", "Incomplete"), ("value", "incomplete")])]),
        ("validate", OrderedDict([("required", True)])),
    ]))

    add("form-clinic-letter-admin-check", OrderedDict([
        ("type", "textarea"), ("key", "letterRecipients"),
        ("label", "Recipients the letter is to be distributed to"),
        ("validate", OrderedDict([("required", True), ("maxLength", 300)])),
    ]))

    add("form-refund-decision", OrderedDict([
        ("type", "checkbox"), ("key", "refundAuthorised"),
        ("label", "Refund authorised by a member of the Finance Team?"),
        ("validate", OrderedDict([("required", True)])),
    ]))


def add_di(check):
    """The new gateways need a BPMNShape, and their flows a BPMNEdge, or the engine
    accepts the model but the readable export shows a gap in the path."""
    plan = {
        "O1_Operational_Merged.bpmn": {
            "flows": [("F_3_28", '<bpmn:sequenceFlow id="F_3_28a" sourceRef="T_AuthoriseUrgentTreatment" targetRef="G_UrgentTreatmentAuthorised" />')],
            "shapes": [("G_UrgentTreatmentAuthorised", 8700, 901, 50, 50)],
            "new_edges": [("F_3_28a", [("8655", "926"), ("8700", "926")])],
            "moved": [("F_3_28", ("8655", "926"), ("8750", "926")),
                      ("F_3_29", ("8655", "926"), ("8750", "926"))],
        },
        "S3_Strategic_Treatment_To_Aftercare.bpmn": {
            "flows": [("F_D22", '<bpmn:sequenceFlow id="F_D22a" sourceRef="T_AuthoriseUrgentTreatment" targetRef="G_UrgentTreatmentAuthorised" />')],
            "shapes": [("G_UrgentTreatmentAuthorised", 3482, 662, 50, 50),
                       ("G_RefundDecision", 8270, 412, 50, 50)],
            "new_edges": [("F_D22a", [("3437", "687"), ("3482", "687")]),
                          ("F_G122", [("8320", "437"), ("8327", "437")])],
            "moved": [("F_D22", ("3437", "687"), ("3532", "687")),
                      ("F_D23", ("3437", "687"), ("3532", "687")),
                      ("F_G16", ("8267", "437"), ("8320", "437")),
                      ("F_G12", ("8267", "437"), ("8270", "437"))],
        },
    }
    for name, spec in plan.items():
        p = MODELS / name
        if check:
            print(f"  (check) would add DI for {name}")
            continue
        text = p.read_text(encoding="utf-8")
        # 1. the missing sequence flow element, placed before the branch it feeds
        for anchor_id, flow in spec["flows"]:
            if re.search(r'<bpmn:sequenceFlow id="%s"[^>]*?>' % flow.split('id="')[1].split('"')[0], text):
                print(f"  = {name}: split flow already present")
                continue
            m = re.search(r'<bpmn:sequenceFlow id="%s"[^>]*?>' % anchor_id, text)
            if not m:
                print(f"  !! {name}: anchor flow {anchor_id} not found")
                continue
            text = text[:m.start()] + flow + "\n    " + text[m.start():]
            note(f"{name}: insert the split flow")

        # 2. shapes and edges for the new elements
        di = []
        for el, x, y, w, h in spec["shapes"]:
            if f'bpmnElement="{el}"' in text:
                continue
            di.append(f'    <bpmndi:BPMNShape id="{el}_di" bpmnElement="{el}">\n'
                      f'      <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />\n'
                      f'    </bpmndi:BPMNShape>')
        for fid, pts in spec["new_edges"]:
            if f'bpmnElement="{fid}"' in text:
                continue
            wp = "\n".join(f'      <di:waypoint x="{a}" y="{b}" />' for a, b in pts)
            di.append(f'    <bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">\n{wp}\n'
                      f'    </bpmndi:BPMNEdge>')
        if di:
            text = text.replace("  </bpmndi:BPMNPlane>", "\n".join(di) + "\n  </bpmndi:BPMNPlane>")
            note(f"{name}: added {len(di)} DI element(s)")

        # 3. edges of the re-sourced flows now start at the gateway
        for fid, old, new in spec["moved"]:
            m = re.search(r'<bpmndi:BPMNEdge[^>]*bpmnElement="%s"[^>]*>(.*?)</bpmndi:BPMNEdge>' % fid,
                          text, re.S)
            if not m:
                continue
            body = m.group(1)
            first = re.search(r'<di:waypoint x="([\d.]+)" y="([\d.]+)"', body)
            if first and (first.group(1), first.group(2)) == old:
                body2 = body.replace(f'<di:waypoint x="{old[0]}" y="{old[1]}"',
                                     f'<di:waypoint x="{new[0]}" y="{new[1]}"', 1)
                text = text[:m.start(1)] + body2 + text[m.end(1):]
                note(f"{name}: move the start of {fid}")
        p.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    print("DEF-M1 refund decision gateway:")
    fix_refund_gateway(args.check)
    print("DEF-M2 explicit parallel split for urgent treatment:")
    fix_parallel_gateways(args.check)
    print("DEF-M3 S1 decision variable:")
    fix_s1_decision(args.check)
    print("DI for the new gateways and flows:")
    add_di(args.check)
    print("DEF-F1 / DEF-F2 form fields:")
    fix_forms(args.check)

    print(f"\n{len(changes)} change(s)" + ("  (check mode)" if args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
