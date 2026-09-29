#!/usr/bin/env python3
"""Build the requirement -> test-case traceability matrix.

Two inputs, both artefacts rather than prose:

  output/tables/traceability.md              the 44 requirements and their verdicts
  extract/acceptance-run/acceptance-run.json which model elements each of the 18
                                             executed cases actually reached

The bridge between them is REQ_ELEMENTS below: the identifiers of the operational
model elements that carry each requirement. That mapping is curated (a regex over
the prose evidence column does not work, because that column cites the strategic
models' identifiers while the executed cases drive the operational model), but it
is reviewable line by line, and the test-case column is then computed from the
run data - a case is listed only if the engine recorded that it reached the
element. A requirement whose elements no case reached is reported as uncovered.

usage: python tools/build-reqtest.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACE = os.path.join(ROOT, 'output', 'tables', 'traceability.md')
RUN = os.path.join(ROOT, 'extract', 'acceptance-run', 'acceptance-run.json')

# ---------------------------------------------------------------- the bridge
# requirement -> operational model elements that carry it (O1_Operational_Merged)
REQ_ELEMENTS = {
    'REQ-01': ['T_ReceiveReferral'],
    'REQ-02': ['T_CheckReferralDocuments'],
    'REQ-03': ['T_RequestMissingDocuments'],
    'REQ-04': ['T_ClinicalReviewReferral', 'T_RecordReferralDecision'],
    'REQ-05': ['T_RecordReferralDecision'],
    'REQ-06': ['G_ReferralDecision', 'T_ForwardAcceptedReferral'],
    'REQ-07': ['T_NotifyReferralOutcome', 'T_RedirectReferral'],
    'REQ-08': ['T_QueryAvailableSlots'],
    'REQ-09': ['G_WithinFourteenDays', 'T_TelephonePatient'],
    'REQ-10': ['G_ContactSuccessful', 'T_RecordContactAttempt'],
    'REQ-11': ['T_ExpediteUrgentBooking'],
    'REQ-12': ['G_SlotsAvailable', 'T_ResolveCapacity'],
    'REQ-13': ['G_PatientConsent', 'T_NewPatientConsultation', 'T_RecordPatientConsent'],
    'REQ-14': ['G_RequestAuthorised', 'T_ReturnUnauthorisedRequest', 'T_ValidateTreatmentRequest'],
    'REQ-15': ['T_RequestTreatmentCapacity'],
    'REQ-16': ['G_CapacityConfirmed', 'T_KeepPending'],
    'REQ-17': ['T_DetermineFundingRoute'],
    'REQ-18': ['G_FundingApproved', 'T_RecordFundingApproval', 'T_RequestFundingApproval'],
    'REQ-19': ['G_AdvancePaymentRequired', 'T_ConfirmTreatmentSchedule'],
    'REQ-20': ['T_SendSecurePaymentRequest'],
    'REQ-22': ['G_PaymentOutcome', 'T_HandlePaymentFailure'],
    'REQ-23': ['T_MarkForInvestigation', 'T_ResolveTransaction'],
    'REQ-24': ['T_AuthoriseUrgentTreatment', 'T_ReferUnconfirmedPayment'],
}

# requirements that no executed case covers, and why - stated rather than implied
REQ_NOTE = {
    'REQ-11': 'Element present but no case drives the urgent branch; not executed in this run',
    'REQ-21': 'No card field exists in any form; verified by design inspection, not by a test',
    'REQ-25': 'Finance refund scope is modelled in S3, outside the operational initial release',
    'REQ-26': 'Cancellation and refund scope is modelled in S3, outside the initial release',
    'REQ-27': 'Chemotherapy cycle review is modelled in S3, outside the initial release',
    'REQ-28': 'Treatment modification is modelled in S3, outside the initial release',
    'REQ-29': 'Urgent postponement is modelled in S3, outside the initial release',
    'REQ-30': 'The financial-impact gate is modelled in S3, outside the initial release',
    'REQ-31': 'Clinic letter timing is modelled in S3; not part of the merged operational model',
    'REQ-32': 'Clinical-content responsibility is modelled in S3; no operational case exists',
    'REQ-33': 'The weekly reminder ladder is modelled in S3; no operational case exists',
    'REQ-34': 'PR_EnquiryHandling was deployed but was not driven by any executed case',
    'REQ-35': 'Urgency classification is modelled but no rule set was agreed; not executed',
    'REQ-36': 'Not implemented in the initial release; no role-enforcement test was run',
    'REQ-37': 'Forms capture the actor; immutability is not implemented and was not tested',
    'REQ-38': 'Only a form field exists; there is no identity-matching step to test',
    'REQ-39': 'No timeout or fallback exists on the service tasks; not executed',
    'REQ-40': 'PR_ManagementReporting was deployed but was not driven by any executed case',
    'REQ-41': 'Out of scope for the initial release; no preference attribute is modelled',
    'REQ-42': 'Cancellation and non-attendance are modelled in S3; not in the operational model',
    'REQ-43': 'Follow-up scheduling is modelled in S3; not in the operational model',
    'REQ-44': 'The elements exist but there is no correlation view to assert against',
}

OUT_REQ = os.path.join(ROOT, 'output', 'tables', 'req-to-test.md')
OUT_TEST = os.path.join(ROOT, 'output', 'tables', 'test-to-req.md')


def read_traceability():
    rows = []
    with open(TRACE, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith('|'):
                continue
            cells = [c.strip() for c in line.strip('|').split('|')]
            if len(cells) < 5 or cells[0] == 'ID' or set(cells[0]) <= set('-: '):
                continue
            rows.append(cells[:5])
    return rows


def abridge(text, n=58):
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= n else text[:n - 1].rstrip(' ,;') + '\u2026'


def case_list(hits, total):
    """Keep the matrix readable: 18 identifiers in one cell helps nobody."""
    if not hits:
        return '\u2014'
    if len(hits) == total:
        return 'all %d cases' % total
    if len(hits) > 4:
        return '%s, %s (+%d more)' % (hits[0], hits[1], len(hits) - 2)
    return ', '.join(hits)


def main():
    rows = read_traceability()
    data = json.load(open(RUN, encoding='utf-8'))
    cases = {r['id']: r for r in data['results']}
    tc_order = sorted(cases, key=lambda c: int(c.split('-')[1]))

    reached = {tc: set(cases[tc]['reached']) for tc in tc_order}
    per_req, used = [], set()
    for rid, text, strat, impl, verdict in rows:
        have = REQ_ELEMENTS.get(rid, [])
        used |= set(have)
        hits = [tc for tc in tc_order if set(have) & reached[tc]]
        per_req.append((rid, text, verdict, have, hits))

    direct = [r for r in per_req if r[4]]
    missing = [r for r in per_req if not r[4]]

    with open(OUT_REQ, 'w', encoding='utf-8') as fh:
        fh.write('| Requirement | Requirement (abridged) | Verdict | Operational element(s) | Executed case(s) | Basis |\n')
        fh.write('| --- | --- | --- | --- | --- | --- |\n')
        for rid, text, verdict, have, hits in per_req:
            basis = 'Executed against build 1.0' if hits else REQ_NOTE.get(rid, 'No executed case')
            elems = ', '.join('`%s`' % e for e in have) or '\u2014'
            fh.write('| %s | %s | %s | %s | %s | %s |\n'
                     % (rid, abridge(text), verdict, elems,
                        case_list(hits, len(tc_order)), basis))

    rev = {tc: [r[0] for r in per_req if tc in r[4]] for tc in tc_order}
    with open(OUT_TEST, 'w', encoding='utf-8') as fh:
        fh.write('| Test case | Objective | Requirements exercised | Status | Instance key |\n')
        fh.write('| --- | --- | --- | --- | --- |\n')
        for tc in tc_order:
            fh.write('| %s | %s | %s | %s | %s |\n'
                     % (tc, abridge(cases[tc]['title'], 56), ', '.join(rev[tc]) or '\u2014',
                        cases[tc]['status'], cases[tc]['processInstanceKey']))

    unreferenced = sorted((set().union(*reached.values()) if reached else set()) - used)

    print('requirements                        : %d' % len(per_req))
    print('  with at least one executed case   : %d' % len(direct))
    print('  no executed case                  : %d' % len(missing))
    print('executed cases                      : %d (%d PASS)'
          % (len(cases), sum(1 for c in cases.values() if c['status'] == 'PASS')))
    print('operational elements no case reached: %d %s'
          % (len([e for e in unreferenced]), ', '.join(unreferenced)))
    print('wrote output/tables/req-to-test.md and output/tables/test-to-req.md')


if __name__ == '__main__':
    sys.exit(main())
