/**
 * Execute the acceptance test cases against the models deployed on the local
 * Camunda 8 cluster, and record the REAL results.
 *
 *   node 09_Tests_and_Tools/run-acceptance.mjs
 *
 * Evidence is written to extract/acceptance-run/ as JSON plus a plain-text log.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const EVID = path.join(ROOT, 'extract', 'acceptance-run');
fs.mkdirSync(EVID, { recursive: true });

const B = process.env.C8_BASE || 'http://127.0.0.1:8080/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function api(method, url, body) {
  const res = await fetch(B + url, {
    method,
    headers: { Authorization: AUTH, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const text = await res.text();
  let json = null; try { json = text ? JSON.parse(text) : null; } catch { /* not json */ }
  return { status: res.status, ok: res.ok, json, text };
}
const search = (kind, body) => api('POST', `/${kind}/search`, body || {});

async function cleanSlate() {
  const r = await search('process-instances', { filter: { state: 'ACTIVE' } });
  for (const i of (r.json && r.json.items) || []) {
    await api('POST', `/process-instances/${i.processInstanceKey}/cancellation`, {});
  }
  const ic = await search('incidents', {});
  for (const n of (ic.json && ic.json.items) || []) {
    await api('POST', `/incidents/${n.incidentKey}/resolution`, {});
  }
  await sleep(300);
}
async function newestInstance(processDefinitionId) {
  const r = await search('process-instances', { filter: { processDefinitionId }, sort: [{ field: 'startDate', order: 'DESC' }] });
  return (r.json && r.json.items && r.json.items[0]) || null;
}
async function instanceByKey(key) {
  const r = await search('process-instances', { filter: { processInstanceKey: key } });
  return (r.json && r.json.items && r.json.items[0]) || null;
}
async function elements(key) {
  const r = await search('element-instances', { filter: { processInstanceKey: key } });
  return ((r.json && r.json.items) || []).map(e => ({ id: e.elementId, type: e.type, state: e.state, incident: e.incidentKey }));
}
async function incidents(key) {
  const r = await search('incidents', { filter: { processInstanceKey: key } });
  return ((r.json && r.json.items) || []).map(n => ({ elementId: n.elementId, type: n.errorType, message: String(n.errorMessage).slice(0, 300) }));
}
async function userTasks(key) {
  const r = await search('user-tasks', { filter: { processInstanceKey: key, state: 'CREATED' } });
  return (r.json && r.json.items) || [];
}
async function jobs(key) {
  const r = await search('jobs', { filter: { processInstanceKey: key, state: 'CREATED' } });
  return (r.json && r.json.items) || [];
}
const completeTask = (k, vars) => api('POST', `/user-tasks/${k}/completion`, { variables: vars || {} });
const completeJob = (k, vars) => api('POST', `/jobs/${k}/completion`, { variables: vars || {} });
const publish = (name, correlationKey, variables) => api('POST', '/messages/publication', { name, correlationKey, variables });

async function variables(key) {
  const r = await search('variables', { filter: { processInstanceKey: key } });
  const out = {};
  for (const v of (r.json && r.json.items) || []) out[v.name] = v.value;
  return out;
}

/**
 * Drive an instance to completion.
 *
 * `plan` maps an element id to either an object of variables, or an array of
 * objects used in order for the 1st, 2nd, ... completion of that element
 * (the last entry repeats). Only ONE new element is completed per poll, because
 * the RDBMS-backed secondary storage lags behind the engine: completing a stale
 * key returns 404 and, if we do not serialise, the same task is retried
 * repeatedly.
 */
async function drive(key, plan, maxSteps = 120) {
  const trace = [];
  const done = new Set();
  const seen = {};
  for (let step = 0; step < maxSteps; step++) {
    const inst = await instanceByKey(key);
    if (!inst) return { state: 'GONE', trace };
    if (inst.state !== 'ACTIVE') return { state: inst.state, trace, endDate: inst.endDate };

    const inc = await incidents(key);
    if (inc.length) return { state: 'INCIDENT', trace, incidents: inc };

    const tasks = (await userTasks(key)).filter(t => !done.has(t.userTaskKey));
    const pending = (await jobs(key)).filter(j => !done.has(j.jobKey));

    const next = tasks[0] ? { kind: 'userTask', key: tasks[0].userTaskKey, el: tasks[0].elementId, name: tasks[0].name }
      : pending[0] ? { kind: 'job', key: pending[0].jobKey, el: pending[0].elementId, type: pending[0].type }
        : null;

    if (!next) {
      let settled = false;
      for (let w = 0; w < 24 && !settled; w++) {
        await sleep(500);
        const i2 = await instanceByKey(key);
        if (i2 && i2.state !== 'ACTIVE') return { state: i2.state, trace, endDate: i2.endDate };
        const t2 = (await userTasks(key)).filter(t => !done.has(t.userTaskKey));
        const j2 = (await jobs(key)).filter(j => !done.has(j.jobKey));
        if (t2.length || j2.length) settled = true;
      }
      if (!settled) {
        const again = await instanceByKey(key);
        return { state: again && again.state !== 'ACTIVE' ? again.state : 'WAITING', trace,
          stalledAfterEvents: (await elements(key)).length };
      }
      continue;
    }

    const n = seen[next.el] = (seen[next.el] || 0) + 1;
    let spec = plan[next.el];
    if (Array.isArray(spec)) spec = spec[Math.min(n - 1, spec.length - 1)];
    const vars = Object.assign({ patientId: 'P-ACCEPT' }, spec || {});

    trace.push({ kind: next.kind, elementId: next.el, name: next.name || next.type, occurrence: n, set: vars });
    const r = next.kind === 'userTask' ? await completeTask(next.key, vars) : await completeJob(next.key, vars);
    // 200 = accepted; 404 = the key is stale (already completed) and must not be
    // retried; anything else is a genuine failure worth retrying once.
    if (r.ok || r.status === 404) done.add(next.key);
    else trace.push({ kind: 'error', elementId: next.el, status: r.status, body: r.text.slice(0, 240) });
    await sleep(600);
  }
  return { state: 'MAX_STEPS', trace };
}

/* ------------------------------------------------------------------ cases */

const V = {
  ok: { documentsComplete: true },
  missing: { documentsComplete: false },
  accept: { referralDecision: 'accepted' },
  reject: { referralDecision: 'rejected' },
  redirect: { referralDecision: 'redirected' },
  routine: { referralUrgency: 'routine' },
  urgent: { referralUrgency: 'urgent' },
  slotYes: { suitableSlotFound: true },
  slotNo: { suitableSlotFound: false },
  in14: { appointmentWithin14Days: true },
  out14: { appointmentWithin14Days: false },
  contactYes: { contactSuccessful: true },
  contactNo: { contactSuccessful: false },
  consentYes: { consentGiven: true },
  consentNo: { consentGiven: false },
  authYes: { requestAuthorised: true },
  authNo: { requestAuthorised: false },
  capYes: { treatmentCapacityConfirmed: true },
  capNo: { treatmentCapacityConfirmed: false },
  fundYes: { fundingApproved: true },
  fundNo: { fundingApproved: false },
  payReq: { advancePaymentRequired: true },
  payNotReq: { advancePaymentRequired: false },
  paid: { paymentStatus: 'confirmed' },
  declined: { paymentStatus: 'declined' },
  noResponse: { paymentStatus: 'no response' },
  urgentClinical: { paymentStatus: 'urgent clinical need' }
};

/**
 * Plan for the operational model PR_Operational_Merged.
 * NOTE: the variable that decides a gateway must be set on the task that
 * PRECEDES the gateway, so consent is decided on T_NewPatientConsultation.
 */
function plan(over = {}) {
  return Object.assign({
    T_ReceiveReferral: V.ok,
    T_CheckReferralDocuments: V.ok,
    T_ClinicalReviewReferral: V.ok,
    T_RecordReferralDecision: V.accept,
    T_ForwardAcceptedReferral: {},
    T_ReceiveBookingRequest: V.routine,
    T_QueryAvailableSlots: V.slotYes,
    T_SelectAndBookSlot: {},
    T_ConfirmBooking: {},
    T_SendAppointmentLetter: V.out14,
    T_TelephonePatient: V.contactYes,
    T_RecordContactAttempt: V.contactYes,
    T_NewPatientConsultation: V.consentYes,
    T_RecordPatientConsent: {},
    T_CreateTreatmentBookingRequest: V.authYes,
    T_ValidateTreatmentRequest: {},
    T_RequestTreatmentCapacity: V.capYes,
    T_DetermineFundingRoute: V.fundYes,
    T_RecordFundingApproval: V.payNotReq,
    T_ConfirmTreatmentSchedule: {}
  }, over);
}

const CASES = [
  { id: 'TC-01', title: 'Complete referral documentation is accepted for clinical review',
    start: V.ok, plan: V.ok,
    expectReached: ['T_ClinicalReviewReferral', 'T_RecordReferralDecision'],
    expectVars: { documentsComplete: true } },

  { id: 'TC-02', title: 'Missing documentation triggers a request and a return path',
    start: V.missing,
    plan: { T_ReceiveReferral: V.missing,
      T_CheckReferralDocuments: [V.missing, V.ok],
      T_RequestMissingDocuments: {},
      T_ClinicalReviewReferral: V.ok, T_RecordReferralDecision: V.accept,
      T_ForwardAcceptedReferral: {}, T_ReceiveBookingRequest: V.routine, T_QueryAvailableSlots: V.slotYes,
      T_SelectAndBookSlot: {}, T_ConfirmBooking: {}, T_SendAppointmentLetter: V.out14,
      T_NewPatientConsultation: V.consentYes, T_RecordPatientConsent: {},
      T_CreateTreatmentBookingRequest: V.authYes, T_ValidateTreatmentRequest: {}, T_RequestTreatmentCapacity: V.capYes,
      T_DetermineFundingRoute: V.fundYes, T_RecordFundingApproval: V.payNotReq, T_ConfirmTreatmentSchedule: {} },
    expectReached: ['T_RequestMissingDocuments', 'T_ClinicalReviewReferral'],
    expectMinOccurrences: { T_CheckReferralDocuments: 2 } },

  { id: 'TC-03', title: 'Rejected referral closes with a notification',
    start: V.ok,
    plan: { T_ReceiveReferral: V.ok, T_CheckReferralDocuments: V.ok, T_ClinicalReviewReferral: V.ok,
      T_RecordReferralDecision: V.reject, T_NotifyReferralOutcome: {} },
    expectReached: ['T_NotifyReferralOutcome'], expectEnd: 'COMPLETED',
    expectNotReached: ['T_ForwardAcceptedReferral'] },

  { id: 'TC-04', title: 'Redirected referral is sent to another specialist service',
    start: V.ok,
    plan: { T_ReceiveReferral: V.ok, T_CheckReferralDocuments: V.ok, T_ClinicalReviewReferral: V.ok,
      T_RecordReferralDecision: V.redirect, T_RedirectReferral: {} },
    expectReached: ['T_RedirectReferral'], expectEnd: 'COMPLETED' },

  { id: 'TC-05', title: 'No suitable appointment slot is escalated to the pathway coordinator',
    start: V.ok,
    plan: plan({ T_QueryAvailableSlots: [V.slotNo, V.slotYes], T_ResolveCapacity: {}, T_SelectAndBookSlot: {} }),
    expectReached: ['T_ResolveCapacity', 'T_SelectAndBookSlot'],
    expectMinOccurrences: { T_QueryAvailableSlots: 2 } },

  { id: 'TC-06', title: 'Appointment within 14 days requires a telephone call',
    start: V.ok,
    plan: plan({ T_SendAppointmentLetter: V.in14, T_TelephonePatient: V.contactYes, T_RecordContactAttempt: V.contactYes }),
    expectReached: ['T_TelephonePatient', 'T_RecordContactAttempt'] },

  { id: 'TC-07', title: 'Appointment more than 14 days away skips the telephone call',
    start: V.ok, plan: plan({ T_SendAppointmentLetter: V.out14 }),
    expectReached: ['T_NewPatientConsultation'], expectNotReached: ['T_TelephonePatient'] },

  { id: 'TC-08', title: 'Unsuccessful contact is recorded and a further attempt is made',
    start: V.ok,
    plan: plan({ T_SendAppointmentLetter: V.in14,
      T_TelephonePatient: [V.contactNo, V.contactYes],
      T_RecordContactAttempt: [V.contactNo, V.contactYes] }),
    expectReached: ['T_TelephonePatient'], expectMinOccurrences: { T_TelephonePatient: 2 } },

  { id: 'TC-09', title: 'Patient refuses consent and the pathway closes',
    start: V.ok,
    plan: plan({ T_NewPatientConsultation: V.consentNo, T_AdviseNoTreatment: {} }),
    expectReached: ['T_AdviseNoTreatment'], expectEnd: 'COMPLETED',
    expectNotReached: ['T_CreateTreatmentBookingRequest'] },

  { id: 'TC-10', title: 'Unauthorised treatment booking request is returned to the clinical team',
    start: V.ok,
    plan: plan({ T_CreateTreatmentBookingRequest: [V.authNo, V.authYes],
      T_ReturnUnauthorisedRequest: {}, T_ValidateTreatmentRequest: {} }),
    expectReached: ['T_ReturnUnauthorisedRequest'],
    expectMinOccurrences: { T_CreateTreatmentBookingRequest: 2 } },

  { id: 'TC-11', title: 'Unavailable external capacity leaves the booking pending and retries',
    start: V.ok,
    plan: plan({ T_RequestTreatmentCapacity: [V.capNo, V.capYes], T_KeepPending: {} }),
    expectReached: ['T_KeepPending'], expectMinOccurrences: { T_RequestTreatmentCapacity: 2 } },

  { id: 'TC-12', title: 'Unapproved funding raises a funding approval request',
    start: V.ok,
    plan: plan({ T_DetermineFundingRoute: [V.fundNo, V.fundYes],
      T_RequestFundingApproval: {}, T_RecordFundingApproval: V.payNotReq }),
    expectReached: ['T_RequestFundingApproval', 'T_RecordFundingApproval'],
    expectMinOccurrences: { T_DetermineFundingRoute: 2 } },

  { id: 'TC-13', title: 'Happy path: referral accepted and treatment schedule confirmed',
    start: V.ok, plan: plan(),
    expectReached: ['T_ConfirmTreatmentSchedule'], expectEnd: 'COMPLETED' },

  { id: 'TC-14', title: 'Advance payment confirmed and recorded',
    start: V.ok,
    plan: plan({ T_RecordFundingApproval: V.payReq, T_SendSecurePaymentRequest: V.paid, T_RecordPayment: {} }),
    expectReached: ['T_SendSecurePaymentRequest', 'T_RecordPayment'], expectEnd: 'COMPLETED' },

  { id: 'TC-15', title: 'Declined payment is handled without creating a duplicate booking',
    start: V.ok,
    plan: plan({ T_RecordFundingApproval: V.payReq,
      T_SendSecurePaymentRequest: [V.declined, V.paid],
      T_HandlePaymentFailure: {}, T_RecordPayment: {} }),
    expectReached: ['T_HandlePaymentFailure', 'T_RecordPayment'],
    expectMinOccurrences: { T_SendSecurePaymentRequest: 2 } },

  { id: 'TC-16', title: 'Payment without a returned confirmation is investigated, not re-requested',
    start: V.ok,
    plan: plan({ T_RecordFundingApproval: V.payReq, T_SendSecurePaymentRequest: V.noResponse,
      T_MarkForInvestigation: {}, T_ResolveTransaction: {} }),
    expectReached: ['T_MarkForInvestigation', 'T_ResolveTransaction'],
    expectEnd: 'COMPLETED' },

  { id: 'TC-17', title: 'Urgent treatment proceeds without confirmed payment and is referred to Finance',
    start: V.ok,
    plan: plan({ T_RecordFundingApproval: V.payReq, T_SendSecurePaymentRequest: V.urgentClinical,
      T_AuthoriseUrgentTreatment: {}, T_ReferUnconfirmedPayment: {} }),
    expectReached: ['T_AuthoriseUrgentTreatment', 'T_ReferUnconfirmedPayment'],
    expectEnd: 'COMPLETED' },

  { id: 'TC-18', title: 'No advance payment required: no payment task is created',
    start: V.ok, plan: plan(),
    expectReached: ['T_ConfirmTreatmentSchedule'], expectNotReached: ['T_SendSecurePaymentRequest'],
    expectEnd: 'COMPLETED' }
];

/* --------------------------------------------------------------- execution */

const results = [];
const log = [];
const L = s => { log.push(s); console.log(s); };

L('Camunda 8 acceptance run');
L('target: ' + B);
L('started: ' + new Date().toISOString());
L('');

const defs = await search('process-definitions', {});
const defIds = ((defs.json && defs.json.items) || []).map(d => d.processDefinitionId).sort();
L(`deployed process definitions (${defIds.length}): ${defIds.join(', ')}`);
await cleanSlate();
L('cluster reset (active instances cancelled, incidents resolved)');
L('');

const eq = (a, b) => String(a) === String(b);

for (const c of CASES) {
  await cleanSlate();
  const t0 = Date.now();
  const pub = await publish('Patient referral', 'P-' + c.id, Object.assign({ patientId: 'P-' + c.id }, c.start));
  await sleep(3200);
  const inst = await newestInstance('PR_Operational_Merged');
  if (!inst) {
    results.push({ id: c.id, title: c.title, status: 'FAIL', problems: ['no instance started'], publishStatus: pub.status });
    L(`${c.id}  FAIL  no instance started`);
    continue;
  }
  const key = inst.processInstanceKey;
  const run = await drive(key, c.plan || {});
  const els = await elements(key);
  const reached = [...new Set(els.map(e => e.id))];
  const counts = {}; for (const e of els) counts[e.id] = (counts[e.id] || 0) + 1;
  const vars = await variables(key);
  const inc = await incidents(key);

  const problems = [];
  for (const id of c.expectReached || []) if (!reached.includes(id)) problems.push('did not reach ' + id);
  for (const id of c.expectNotReached || []) if (reached.includes(id)) problems.push('unexpectedly reached ' + id);
  for (const [k, n] of Object.entries(c.expectMinOccurrences || {})) if ((counts[k] || 0) < n) problems.push(`${k} expected at least ${n}, saw ${counts[k] || 0}`);
  if (c.expectEnd && run.state !== c.expectEnd) problems.push(`expected final state ${c.expectEnd}, saw ${run.state}`);
  if (inc.length) problems.push('incident: ' + inc.map(i => i.type + ' at ' + i.elementId).join('; '));
  for (const [k, v] of Object.entries(c.expectVars || {})) if (!eq(vars[k], v)) problems.push(`variable ${k} expected ${v}, saw ${JSON.stringify(vars[k])}`);

  const status = problems.length ? 'FAIL' : 'PASS';
  const decisions = {};
  for (const t of run.trace) for (const [k, v] of Object.entries(t.set || {})) decisions[k] = v;
  results.push({
    id: c.id, title: c.title, processDefinitionId: 'PR_Operational_Merged', processInstanceKey: key,
    status, problems, endState: run.state,
    startVariables: Object.assign({ patientId: 'P-' + c.id }, c.start),
    decisionsTaken: decisions,
    expectations: {
      reached: c.expectReached || [], notReached: c.expectNotReached || [],
      end: c.expectEnd || null, minOccurrences: c.expectMinOccurrences || {}
    },
    reached: reached.filter(x => /^[TGEB]/.test(x)),
    counts, variables: vars, incidents: inc,
    trace: run.trace.map(t => ({ kind: t.kind, elementId: t.elementId, occurrence: t.occurrence, set: t.set })),
    startedAt: new Date(t0).toISOString(), durationMs: Date.now() - t0
  });
  L(`${c.id}  ${status}  ${c.title}`);
  for (const p of problems) L('        ! ' + p);
  L(`        instance ${key}  final=${run.state}  events=${els.length}  ms=${Date.now() - t0}`);
}

const passed = results.filter(r => r.status === 'PASS').length;
const failed = results.length - passed;

L('');
L(`SUMMARY: ${results.length} cases executed, ${passed} passed, ${failed} failed`);
L('finished: ' + new Date().toISOString());

fs.writeFileSync(path.join(EVID, 'acceptance-run.json'), JSON.stringify({
  target: B, executedAt: new Date().toISOString(), processDefinitions: defIds,
  summary: { total: results.length, passed, failed }, results
}, null, 2), 'utf8');
fs.writeFileSync(path.join(EVID, 'acceptance-run.log'), log.join('\n') + '\n', 'utf8');
fs.writeFileSync(path.join(EVID, 'acceptance-cases.json'), JSON.stringify(
  CASES.map(c => ({ id: c.id, title: c.title, start: c.start, expectations: {
    reached: c.expectReached || [], notReached: c.expectNotReached || [],
    end: c.expectEnd || null, minOccurrences: c.expectMinOccurrences || {},
    vars: c.expectVars || {} } })), null, 2), 'utf8');
console.log('\nwrote extract/acceptance-run/acceptance-run.json and .log');
