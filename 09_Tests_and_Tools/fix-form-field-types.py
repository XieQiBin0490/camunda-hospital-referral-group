#!/usr/bin/env python3
"""Correct the Camunda 8 form field types in 03_Forms/.

Improvement 5 of the review action list: "collect different business data with the
right input control (date, number, ...) instead of a plain text box".

The script is intentionally declarative: every change is listed in SPEC below, and
every category of change carries the evidence that justifies it. Run with --dry-run
to print the plan without touching a file.

Evidence sources used to justify each change:
  * gateway conditions in 02_BPMN_Models/*.bpmn  (FEEL expressions)
  * variable names read by the Java workers in 04_Java_Worker (JobContext accessors)
  * task names in 08_Repository_Documents/model-inventory.md
"""

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMS = ROOT / "03_Forms"
MODELS = ROOT / "02_BPMN_Models"
WORKERS = ROOT / "04_Java_Worker" / "src" / "main" / "java"

# --------------------------------------------------------------------------- #
# 1. Controlled value sets.
#    Every option value is the literal string the FEEL gateway conditions and the
#    Java workers already compare against, so the process variable type does not
#    change when a text box becomes a select.
# --------------------------------------------------------------------------- #
SELECT_OPTIONS = {
    "referralDecision": [
        ("Accepted", "accepted"),
        ("Rejected", "rejected"),
        ("Information required", "information required"),
        ("Redirected", "redirected"),
    ],
    "referralUrgency": [("Urgent", "urgent"), ("Routine", "routine")],
    "paymentStatus": [
        ("Confirmed", "confirmed"),
        ("Declined", "declined"),
        ("No response", "no response"),
        ("Urgent clinical need", "urgent clinical need"),
    ],
    "enquiryType": [
        ("Administrative", "administrative"),
        ("Financial", "financial"),
        ("Clinical", "clinical"),
        ("Urgent clinical", "urgent clinical"),
    ],
    "currency": [("Pound sterling (GBP)", "GBP"), ("Euro (EUR)", "EUR"), ("US dollar (USD)", "USD")],
    "communicationPreference": [
        ("Standard post", "post"),
        ("Email", "email"),
        ("Accessible format", "accessible format"),
        ("Translation", "translation"),
        ("Via a representative", "representative"),
    ],
    "refundDecision": [
        ("Retained by the hospital", "retained"),
        ("Transferred to another episode", "transferred"),
        ("Refunded to the patient", "refunded"),
    ],
}

# --------------------------------------------------------------------------- #
# 2. Type corrections.
#    (a) DEF-FORM-01: a boolean checkbox was bound to a variable the model
#        compares numerically, so the gateway could never take the intended
#        branch. Evidence: S1 letterDelayDays <= 7 / > 7,
#        S3 letterAgeMonths < 1 / < 3 / >= 1 / >= 3.
#    (b) DEF-FORM-02: a free-text box was bound to a variable the model compares
#        against an exact controlled value.
# --------------------------------------------------------------------------- #
RETYPE = {
    "form-deliver-treatment-cycle": {
        "letterDelayDays": {"type": "number", "label": "Delay in producing the letter, in days",
                            "validate": {"required": True, "min": 0, "max": 365}},
    },
    "form-follow-up-review": {
        "letterDelayDays": {"type": "number", "label": "Delay in producing the letter, in days",
                            "validate": {"required": True, "min": 0, "max": 365}},
    },
    "form-escalate-to-manager": {
        "letterAgeMonths": {"type": "number", "label": "Age of the outstanding letter, in months",
                            "validate": {"required": True, "min": 0, "max": 120}},
    },
    "form-issue-letter-reminder": {
        "letterAgeMonths": {"type": "number", "label": "Age of the outstanding letter, in months",
                            "validate": {"required": True, "min": 0, "max": 120}},
    },
    "form-clinical-review-referral": {"referralDecision": {"type": "select"}},
    "form-record-referral-decision": {"referralDecision": {"type": "select"}},
    "form-forward-accepted-referral": {"referralUrgency": {"type": "select"}},
    "form-validate-booking-request": {"referralUrgency": {"type": "select"}},
    "form-handle-payment-failure": {"paymentStatus": {"type": "select"}},
    "form-classify-enquiry": {"enquiryType": {"type": "select"}},
}

# --------------------------------------------------------------------------- #
# 3. Missing controls.
#    Each key below is either (i) read by a Java worker through a JobContext
#    accessor, or (ii) named in the task description recorded in
#    model-inventory.md. No key is invented.
# --------------------------------------------------------------------------- #
ADD = {
    "form-register-referral": [
        ("textfield", "referralReference", "Referral reference issued at registration",
         {"required": True, "maxLength": 40}),
        ("textfield", "referringOrganisation", "Referring organisation (GP practice or hospital)",
         {"required": True, "maxLength": 120}),
        ("textfield", "requestedSpeciality", "Requested speciality or service",
         {"required": True, "maxLength": 80}),
        ("select", "referralUrgency", "Referral urgency"),
    ],
    "form-receive-referral": [
        ("textfield", "referralReference", "Referral reference issued at registration",
         {"required": True, "maxLength": 40}),
        ("textfield", "referringOrganisation", "Referring organisation (GP practice or hospital)",
         {"required": True, "maxLength": 120}),
        ("select", "referralUrgency", "Referral urgency"),
    ],
    "form-check-referral-documents": [
        ("textarea", "missingDocuments", "Documents missing from the referral (list them)",
         {"maxLength": 500}),
    ],
    "form-select-book-appointment": [
        ("datetime", "appointmentDate", "Date of the booked appointment",
         {"required": True}, {"subtype": "date"}),
        ("textfield", "requestedSpeciality", "Requested speciality or service",
         {"required": True, "maxLength": 80}),
        ("number", "preferredTimeframeDays", "Requested booking timeframe, in days",
         {"required": True, "min": 1, "max": 365}),
    ],
    "form-request-follow-up": [
        ("number", "preferredTimeframeDays", "Clinically specified follow-up period, in days",
         {"required": True, "min": 1, "max": 365}),
    ],
    "form-treatment-booking-request": [
        ("textfield", "treatmentCode", "Treatment or procedure code",
         {"required": True, "maxLength": 40}),
        ("number", "treatmentCycles", "Number of treatment cycles requested",
         {"required": True, "min": 1, "max": 12}),
        ("textfield", "requiredResource", "Resource required (for example chair, bed, theatre)",
         {"required": True, "maxLength": 80}),
        ("number", "chargeAmount", "Charge to the patient for this request, in whole GBP",
         {"required": True, "min": 0}),
        ("select", "currency", "Currency"),
    ],
    "form-record-funding-approval": [
        ("textfield", "fundingOrganisation", "Funding organisation or insurer",
         {"required": True, "maxLength": 120}),
        ("textfield", "fundingAuthorisationReference", "Funding authorisation reference",
         {"required": True, "maxLength": 40}),
        ("number", "approvedAmount", "Amount approved, in whole GBP",
         {"required": True, "min": 0}),
        ("select", "currency", "Currency"),
        ("textarea", "fundingLimitations", "Limitations attached to the approval",
         {"maxLength": 500}),
    ],
    "form-record-payment": [
        ("textfield", "paymentReference", "Payment reference returned by the provider",
         {"required": True, "maxLength": 40}),
        ("number", "paymentAmount", "Amount paid, in whole GBP", {"required": True, "min": 0}),
        ("datetime", "paymentDate", "Date the payment was taken", {"required": True},
         {"subtype": "date"}),
        ("select", "currency", "Currency"),
    ],
    "form-record-refund": [
        ("textfield", "refundReference", "Refund reference returned by the provider",
         {"required": True, "maxLength": 40}),
        ("number", "refundAmount", "Amount refunded, in whole GBP", {"required": True, "min": 0}),
        ("datetime", "refundDate", "Date the refund was issued", {"required": True},
         {"subtype": "date"}),
    ],
    "form-refund-decision": [
        ("select", "refundDecision", "Decision taken on the payment"),
        ("number", "refundAmount", "Amount to refund, in whole GBP", {"min": 0}),
    ],
    "form-deliver-treatment-cycle": [
        ("textfield", "cycleReference", "Treatment cycle reference", {"maxLength": 40}),
        ("datetime", "treatmentCycleDate", "Date the cycle was administered", {},
         {"subtype": "date"}),
    ],
    "form-clinic-letter-admin-check": [
        # Closes DEF-FORM-03: gateway G_CommunicationPreference branches on
        # accessibleFormatRequired, which no form ever collected, so the
        # "accessible format / translation / representative" branch was
        # unreachable. communicationPreference is read by
        # SendAppointmentConfirmationLetterWorker (findString, default "post").
        ("checkbox", "accessibleFormatRequired",
         "Does the patient require an accessible format, translation or a representative?",
         {"required": True}),
        ("select", "communicationPreference", "Preferred communication channel"),
    ],
    "form-prepare-accessible-format": [
        ("select", "communicationPreference", "Format or language actually produced"),
    ],
    "form-review-management-reports": [
        ("textfield", "reportPeriod", "Reporting period (YYYY-MM)",
         {"required": True, "pattern": "^[0-9]{4}-(0[1-9]|1[0-2])$"}),
    ],
    "form-validate-treatment-request": [
        ("number", "treatmentCycles", "Number of treatment cycles confirmed",
         {"required": True, "min": 1, "max": 12}),
        ("textfield", "requiredResource", "Resource confirmed for the request",
         {"required": True, "maxLength": 80}),
    ],
    "form-record-pending-booking": [
        ("textfield", "requiredResource", "Resource that could not be confirmed",
         {"required": True, "maxLength": 80}),
        ("number", "preferredTimeframeDays", "Requested timeframe that could not be met, in days",
         {"min": 1, "max": 365}),
    ],
}

# --------------------------------------------------------------------------- #
# 4. Validation (improvement 4). Two rules, both derived from the model:
#    (a) patientId is requireString() in 13 workers -> required, with a pattern
#        that accepts the identifiers the project's own evidence uses
#        (for example "P-enquiry-1790598559277").
#    (b) every variable a gateway branches on must be answered, otherwise FEEL
#        evaluates null and the default flow is taken silently.
# --------------------------------------------------------------------------- #
PATIENT_ID_VALIDATE = {"required": True, "pattern": "^[A-Za-z0-9][A-Za-z0-9\\-]{2,39}$"}

# Static option defaults that mirror the fallback the Java worker already applies,
# so the form and the worker agree instead of the worker silently substituting.
SELECT_DEFAULTS = {"currency": "GBP", "communicationPreference": "post"}

# Fields that must always be answered even though no gateway branches on them yet.
# refundDecision is the decision T_RefundDecision exists to record; the model
# currently splits after that task without a gateway (see DEF-FORM-05).
ALWAYS_REQUIRED = {"currency", "refundDecision"}

GATEWAY_VARIABLES = {
    "accessibleFormatRequired", "advancePaymentRequired", "appointmentPaid",
    "appointmentWithin14Days", "consentGiven", "contactSuccessful",
    "documentsComplete", "enquiryType", "financialImpact", "fitToContinue",
    "followUpSlotWithinPeriod", "fundingApproved", "furtherCyclesPlanned",
    "letterAgeMonths", "letterApproved", "letterDelayDays", "paymentStatus",
    "referralDecision", "referralUrgency", "requestAuthorised",
    "suitableSlotFound", "suspectedClinicalError", "treatmentCapacityConfirmed",
    "urgentPostponement",
}
# Deliberately absent: "accepted", which S1_Strategic_Landscape.bpmn branches on but
# no form collects and no other model uses. That is a model defect, not a form
# defect, and is recorded in the change log rather than patched here.


def load(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=OrderedDict)


def dump(path, doc):
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def ordered(*pairs):
    return OrderedDict(pairs)


def build_component(kind, key, label, validate=None, extra=None):
    comp = ordered(("type", kind), ("key", key), ("label", label))
    if kind == "select":
        comp["values"] = [
            ordered(("label", lbl), ("value", val)) for lbl, val in SELECT_OPTIONS[key]
        ]
        if key in SELECT_DEFAULTS:
            comp["defaultValue"] = SELECT_DEFAULTS[key]
    if extra:
        for k, v in extra.items():
            comp[k] = v
    if validate:
        comp["validate"] = OrderedDict(sorted(validate.items()))
    return comp


def apply_to_form(form_id, doc, log):
    components = doc["components"]
    by_key = {c.get("key"): c for c in components if c.get("key")}

    # ---- type corrections + value sets -----------------------------------
    for key, change in RETYPE.get(form_id, {}).items():
        comp = by_key.get(key)
        if comp is None:
            log.append(f"  !! {form_id}: retype target {key} not found")
            continue
        old = comp["type"]
        comp["type"] = change["type"]
        if "label" in change:
            comp["label"] = change["label"]
        if change["type"] == "select":
            comp["values"] = [
                ordered(("label", lbl), ("value", val)) for lbl, val in SELECT_OPTIONS[key]
            ]
        if "validate" in change:
            comp["validate"] = OrderedDict(sorted(change["validate"].items()))
        log.append(f"  ~ {form_id}: {key} {old} -> {change['type']}")

    # ---- missing controls -------------------------------------------------
    for spec in ADD.get(form_id, []):
        kind, key, label = spec[0], spec[1], spec[2]
        validate = spec[3] if len(spec) > 3 else None
        extra = spec[4] if len(spec) > 4 else None
        if key in by_key:
            log.append(f"  = {form_id}: {key} already present, skipped")
            continue
        comp = build_component(kind, key, label, validate, extra)
        components.append(comp)
        by_key[key] = comp
        log.append(f"  + {form_id}: {key} ({kind})")

    # ---- validation -------------------------------------------------------
    for comp in components:
        key = comp.get("key")
        if not key or comp.get("type") in ("text", "html"):
            continue
        if key == "patientId":
            comp["validate"] = OrderedDict(sorted(PATIENT_ID_VALIDATE.items()))
            continue
        if key in GATEWAY_VARIABLES or key in ALWAYS_REQUIRED:
            if "validate" not in comp:
                comp["validate"] = OrderedDict([("required", True)])
            elif not comp["validate"].get("required"):
                comp["validate"]["required"] = True
                comp["validate"] = OrderedDict(sorted(comp["validate"].items()))
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    touched = set(RETYPE) | set(ADD)
    log = []
    changed = 0
    for path in sorted(FORMS.glob("*.form")):
        form_id = path.stem
        doc = load(path)
        before = json.dumps(doc, sort_keys=True)
        # The validation pass (section 4) applies to every form, including the ones
        # with no type correction, so a gateway variable is required everywhere it
        # is collected.
        apply_to_form(form_id, doc, log)
        after = json.dumps(doc, sort_keys=True)
        if before != after:
            changed += 1
            if not args.dry_run:
                dump(path, doc)

    print("\n".join(log))
    missing = [f for f in sorted(touched) if not (FORMS / f"{f}.form").exists()]
    for name in missing:
        print(f"MISSING FORM: {name}.form", file=sys.stderr)
    print(f"\nforms changed: {changed} of {len(list(FORMS.glob('*.form')))}")
    print(f"forms with a type correction or a new control: {len(touched)}")
    if args.dry_run:
        print("(dry run - nothing written)")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
