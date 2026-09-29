/**
 * Worker-driven end-to-end demonstration.
 *
 * The acceptance harness (09_Tests_and_Tools/run-acceptance.mjs) completes BOTH the user tasks
 * and the automated jobs through the API, which measures the model but proves
 * nothing about the workers. This script inverts that: it plays only the human
 * roles - it completes user tasks and nothing else - so every service task and
 * send task must be completed by a running instance of the Java worker fleet in
 * workers/. If no worker is subscribed, the case hangs and the run fails.
 *
 *   node tools/run-worker-demo.mjs happy
 *   node tools/run-worker-demo.mjs capacity-unavailable
 *   node tools/run-worker-demo.mjs payment-declined
 *   node tools/run-worker-demo.mjs transient-retry
 *   node tools/run-worker-demo.mjs all
 *
 * The worker fleet must already be running with the matching environment (the
 * scenario table below prints the environment each case needs).
 */
import fs from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

const BASE = 'http://127.0.0.1:8080/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');
// Evidence lives in evidence/ in the team workspace and in 05_Test_Evidence/
// in the delivered package; either layout must work.
const EVIDENCE = fs.existsSync('05_Test_Evidence')
  ? path.resolve('05_Test_Evidence/worker-run')
  : path.resolve('evidence/worker-run');

async function api(method, url, body) {
  const r = await fetch(BASE + url, {
    method,
    headers: { Authorization: AUTH, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const text = await r.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON error body */ }
  return { status: r.status, json, text };
}

const search = (kind, body) => api('POST', `/${kind}/search`, body || {});
const publish = (name, correlationKey, variables) =>
  api('POST', '/messages/publication', { name, correlationKey, variables });

const elements = async (key) =>
  ((await search('element-instances', { filter: { processInstanceKey: key } })).json?.items || [])
    .map(e => ({ id: e.elementId, type: e.type, state: e.state }));

const jobs = async (key) =>
  ((await search('jobs', { filter: { processInstanceKey: key, state: 'CREATED' } })).json?.items || []);

const tasks = async (key) =>
  ((await search('user-tasks', { filter: { processInstanceKey: key, state: 'CREATED' } })).json?.items || []);

const incidents = async (key) =>
  ((await search('incidents', { filter: { processInstanceKey: key } })).json?.items || []);

const vars = async (key) =>
  Object.fromEntries((((await search('variables', { filter: { processInstanceKey: key } })).json?.items) || [])
    .map(v => [v.name, v.value]));

const instance = async (key) =>
  ((await search('process-instances', { filter: { processInstanceKey: key } })).json?.items || [])[0];

const unquote = (v) => String(v ?? '').replace(/^"|"$/g, '');

/** Cancel anything still active so each scenario starts from a clean engine. */
async function cleanSlate() {
  const r = await search('process-instances', { filter: { state: 'ACTIVE' } });
  for (const i of r.json?.items || []) {
    await api('POST', `/process-instances/${i.processInstanceKey}/cancellation`, {});
  }
  const inc = await search('incidents', { filter: { state: 'PENDING' } });
  for (const n of inc.json?.items || []) {
    await api('POST', `/incidents/${n.incidentKey}/resolution`, {});
  }
}

/**
 * The message-publication response carries a message key, not the instance key,
 * so the instance has to be found by the patientId it was started with.
 */
async function findInstance(processDefinitionId, patientId, timeoutMs = 25000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const r = await search('process-instances', {
      filter: { processDefinitionId },
      sort: [{ field: 'startDate', order: 'DESC' }]
    });
    for (const i of r.json?.items || []) {
      const v = await vars(i.processInstanceKey);
      if (unquote(v.patientId) === patientId) {
        return i;
      }
    }
    await sleep(400);
  }
  return null;
}

// --------------------------------------------------------------- human script
// What each human hands over at each user task. The automated activities are
// deliberately absent: a worker owns them, and the run fails if one does not.
//
// A value may be an array, which supplies a different answer on each visit to
// the same task (the last entry repeats). The funding route needs it: a route
// that is not approved loops back for approval, so the second visit must
// approve it or the instance spins forever.
const HUMAN_PLAN = {
  T_ReceiveReferral: { documentsComplete: true },
  T_CheckReferralDocuments: { documentsComplete: true },
  T_ClinicalReviewReferral: { referralDecision: 'accepted' },
  T_RecordReferralDecision: {},
  T_ForwardAcceptedReferral: {},
  T_ReceiveBookingRequest: { referralUrgency: 'routine', preferredTimeframeDays: 28 },
  T_SelectAndBookSlot: { appointmentReference: 'APT-0001', appointmentWithin14Days: true },
  T_ConfirmBooking: { bookingConfirmed: true },
  T_TelephonePatient: {},
  T_RecordContactAttempt: { contactSuccessful: true },
  T_NewPatientConsultation: { consentGiven: true },
  T_RecordPatientConsent: {},
  T_CreateTreatmentBookingRequest: { requestAuthorised: true, treatmentCode: 'CHEMO-6', treatmentCycles: 6 },
  T_ValidateTreatmentRequest: {},
  T_DetermineFundingRoute: [
    { fundingApproved: false, advancePaymentRequired: true, chargeAmount: 480.0, currency: 'GBP' },
    { fundingApproved: true, advancePaymentRequired: true, chargeAmount: 480.0, currency: 'GBP' }
  ],
  T_RequestFundingApproval: { fundingApproved: true },
  T_RecordFundingApproval: {},
  T_RecordPayment: {},
  T_HandlePaymentFailure: {},
  T_ConfirmTreatmentSchedule: {},
  // capacity-unavailable branch
  T_ResolveCapacity: { capacityEscalationResolved: true, appointmentReference: 'APT-0002' },
  T_KeepPending: {},
  // payment-exception branches
  T_MarkForInvestigation: {},
  T_ResolveTransaction: {},
  T_AuthoriseUrgentTreatment: {},
  T_ReferUnconfirmedPayment: {},
  T_AdviseNoTreatment: {},
  T_ReturnUnauthorisedRequest: {},

  // ---- PR_TreatmentToAftercare (S3). Only the tasks on the driven path are
  // listed; every automated activity between them belongs to a worker.
  T_ValidateRequest: { requestAuthorised: true, treatmentCode: 'CHEMO-6', treatmentCycles: 6 },
  T_DetermineFunding: { fundingApproved: true, advancePaymentRequired: true, chargeAmount: 480.0, currency: 'GBP' },
  T_DeliverTreatmentCycle: [
    { furtherCyclesPlanned: true },     // first cycle: another one is planned
    { furtherCyclesPlanned: false }     // second visit: treatment finished, write the letter
  ],
  T_ReviewCycleResults: { fitToContinue: false, urgentPostponement: false },
  T_ModifyTreatment: { financialImpact: false },
  T_ApplyTreatmentChange: {},
  T_PrepareClinicLetter: {},
  T_ApproveClinicLetter: { letterApproved: true },
  T_AdministrativeCheck: { suspectedClinicalError: false, accessibleFormatRequired: false },
  T_RequestFollowUp: {},
  T_ArrangeFollowUp: { followUpSlotWithinPeriod: true },
  // The patient cancels: rather than completing this task, the correlated
  // boundary message is published, which is what routes the instance down the
  // non-attendance and refund path.
  T_ConfirmFollowUp: { __publish: 'Patient cancellation or non-attendance' },
  T_RecordNonAttendance: { appointmentPaid: true },
  T_RefundDecision: { refundAuthorised: true, refundAmount: 480.0 },
  T_RecordRefund: {},
  T_OfferAnotherAppointment: {},

  // ---- PR_EnquiryHandling (S3)
  T_ClassifyEnquiry: { enquiryType: 'administrative' },
  T_AnswerAdministrative: {},
  T_AnswerClinical: {},
  T_HandleUrgentConcern: {},
  T_RecordEnquiryOutcome: {}
};

const SCENARIOS = {
  happy: {
    label: 'Worker-driven happy path',
    start: { documentsComplete: true },
    workerEnv: {},
    expectReached: ['T_QueryAvailableSlots', 'T_RequestTreatmentCapacity', 'T_SendSecurePaymentRequest',
                    'T_ConfirmTreatmentSchedule'],
    expectEnd: 'COMPLETED',
    expectVars: { suitableSlotFound: true, treatmentCapacityConfirmed: true, paymentStatus: 'confirmed',
                  cardDataStored: false },
    expectWorkerLog: ['scheduling service returned', 'capacity confirmed on attempt 1',
                      'provider confirmed', 'no card data read']
  },
  'capacity-unavailable': {
    label: 'External capacity unavailable, then confirmed on the retry',
    start: { documentsComplete: true },
    workerEnv: { HPAS_CAPACITY_UNAVAILABLEONCE: 'true' },
    expectReached: ['T_KeepPending', 'T_RequestTreatmentCapacity', 'T_ConfirmTreatmentSchedule'],
    expectMinOccurrences: { T_RequestTreatmentCapacity: 2 },
    expectEnd: 'COMPLETED',
    expectVars: { duplicateAppointmentCreated: false },
    expectWorkerLog: ['no capacity on attempt 1', 'capacity confirmed on attempt 2',
                      'retry recorded against the existing request']
  },
  'payment-declined': {
    // The decline is handled and the further attempt the case study requires is
    // permitted, which succeeds. The final variable is therefore 'confirmed';
    // what proves the decline happened is the worker's own log and the fact that
    // the failure-handling activity was reached.
    label: 'Provider declines the payment; handled, then the permitted retry succeeds',
    start: { documentsComplete: true },
    workerEnv: { HPAS_PAYMENT_OUTCOME: 'DECLINED' },
    expectReached: ['T_SendSecurePaymentRequest', 'T_HandlePaymentFailure'],
    expectVars: { paymentStatus: 'confirmed', cardDataStored: false },
    expectWorkerLog: ['provider declined', 'a further attempt is permitted']
  },
  'transient-retry': {
    label: 'Scheduling service fails once; the engine retry recovers it',
    start: { documentsComplete: true },
    workerEnv: { HPAS_FAILURE_MODE: 'rules', HPAS_FAILURE_PREFIX: 'query-available-appointment-slots' },
    expectReached: ['T_QueryAvailableSlots', 'T_SelectAndBookSlot'],
    expectEnd: 'COMPLETED',
    expectVars: { suitableSlotFound: true },
    expectWorkerLog: ['injected transient failure', 'scheduling service returned']
  },

  // ------------------------------------------------------------------ S3 paths
  // These three exercise the workers that are bound only in the strategic
  // treatment, enquiry and reporting processes, and they drive the two
  // processes the acceptance evaluation lists as deployed but never run.
  'aftercare-cycles': {
    label: 'Treatment cycles, clinic letter, then cancellation and refund',
    processDefinitionId: 'PR_TreatmentToAftercare',
    startKind: 'message',
    startName: 'Authorised treatment booking request',
    start: { treatmentCode: 'CHEMO-6', treatmentCycles: 6 },
    workerEnv: {},
    expectReached: ['T_RequestTreatmentCapacity', 'T_RequestSecurePayment', 'T_RequestBloodTest',
                    'T_DistributeClinicLetter', 'T_RequestRefund', 'T_RecordNonAttendance',
                    'E_PathwayReviewed'],
    expectMinOccurrences: { T_DeliverTreatmentCycle: 2, T_RequestBloodTest: 1 },
    expectVars: { bloodTestRequested: true, correspondenceSent: true, refundStatus: 'refunded' },
    expectWorkerLog: ['capacity confirmed', 'provider confirmed', 'ordered LAB-',
                      'dispatched LTR-', 'refund REF-']
  },
  enquiry: {
    label: 'Patient enquiry classified, answered and closed',
    processDefinitionId: 'PR_EnquiryHandling',
    startKind: 'message',
    startName: 'Patient enquiry',
    start: {},
    workerEnv: {},
    expectReached: ['T_ClassifyEnquiry', 'T_AnswerAdministrative', 'T_RecordEnquiryOutcome', 'E_EnquiryClosed'],
    expectEnd: 'COMPLETED'
  },
  reporting: {
    label: 'Monthly management report generated',
    processDefinitionId: 'PR_ManagementReporting',
    startKind: 'process',
    startName: 'PR_ManagementReporting',
    start: { reportPeriod: '2026-09' },
    workerEnv: {},
    expectVars: { reportGenerated: true },
    expectWorkerLog: ['generated report RPT-'],
    // The engine will not create this instance on demand: the process's only
    // start event is a timer (`R/P1M`), so there is no none start event to
    // create from and the API answers 409. It stays in the file so the attempt
    // and its reason are recorded rather than forgotten, and it is excluded
    // from the default suite.
    skip: true,
    skipReason: 'timer-only start event (R/P1M); the engine answers 409 to a direct create, '
      + 'so this worker is verified by the start-up coverage check rather than executed'
  }
};

async function waitForInstance(key, { timeoutMs = 120000, idleMs = 1200, maxHumanSteps = 90, patientId = '' } = {}) {
  const started = Date.now();
  const seenTask = new Set();
  const seenJob = new Set();
  const visit = new Map();
  let lastProgress = Date.now();
  const trace = [];
  while (Date.now() - started < timeoutMs) {
    if (trace.filter(t => t.kind === 'userTask').length > maxHumanSteps) {
      return { trace, incidents: [], error: 'the instance visited more than ' + maxHumanSteps
        + ' human steps; a branch is almost certainly looping' };
    }
    const inc = await incidents(key);
    if (inc.length) {
      return { trace, incidents: inc, error: 'incident: ' + inc.map(i => i.errorType + '@' + i.elementId).join(';') };
    }
    const openTasks = await tasks(key);
    const openJobs = await jobs(key);
    if (openTasks.length) {
      const t = openTasks[0];
      if (!seenTask.has(t.userTaskKey)) {
        seenTask.add(t.userTaskKey);
        const n = visit.get(t.elementId) || 0;
        visit.set(t.elementId, n + 1);
        const def = HUMAN_PLAN[t.elementId] ?? {};
        const plan = Array.isArray(def) ? (def[Math.min(n, def.length - 1)] ?? {}) : def;
        if (plan.__publish) {
          // An interrupting boundary message replaces the task rather than
          // completing it - the patient cancelling the follow-up appointment.
          const pub = await publish(plan.__publish, patientId, { patientId });
          trace.push({ kind: 'boundary', elementId: t.elementId, by: 'message: ' + plan.__publish,
                       http: pub.status });
          lastProgress = Date.now();
          await sleep(600);
          continue;
        }
        await api('POST', `/user-tasks/${t.userTaskKey}/completion`, { variables: plan });
        trace.push({ kind: 'userTask', elementId: t.elementId, by: 'human (this script)', set: plan });
        lastProgress = Date.now();
        continue;
      }
    }
    if (openJobs.length) {
      const j = openJobs[0];
      if (!seenJob.has(j.jobKey)) {
        seenJob.add(j.jobKey);
        trace.push({ kind: 'job', elementId: j.elementId, type: j.type, by: 'worker' });
      }
      // the worker fleet is expected to complete it; do NOT complete it here
      if (Date.now() - lastProgress > 25000) {
        const inst = await instance(key);
        if (inst && inst.state !== 'ACTIVE') break;
        return { trace, incidents: [], error: 'job not completed by any worker: '
          + j.type + ' at ' + j.elementId + ' (is the worker fleet running?)' };
      }
    } else {
      lastProgress = Date.now();
      const inst = await instance(key);
      if (inst && inst.state !== 'ACTIVE') {
        return { trace, incidents: [], state: inst.state };
      }
    }
    await sleep(400);
  }
  return { trace, incidents: [], error: 'timeout waiting for the instance to finish' };
}

function counts(list) {
  const out = {};
  for (const e of list) out[e.id] = (out[e.id] || 0) + 1;
  return out;
}

async function runCase(name) {
  const c = SCENARIOS[name];
  // Unique per run: a leftover instance from an earlier attempt must never be
  // mistaken for this one, and the engine's search is eventually consistent.
  const patientId = 'P-' + name + '-' + Date.now();
  const definition = c.processDefinitionId || 'PR_Operational_Merged';
  await cleanSlate();
  await sleep(1500);

  let startStatus;
  if (c.startKind === 'process') {
    // A timer-start process has no message to publish; the instance is created
    // directly, which is how a monthly reporting run is triggered by hand.
    const r = await api('POST', '/process-instances', {
      processDefinitionId: c.startName, variables: { patientId, ...c.start }
    });
    startStatus = r.status;
  } else {
    const r = await publish(c.startName || 'Patient referral', patientId, { patientId, ...c.start });
    startStatus = r.status;
  }
  if (startStatus >= 300) throw new Error('start failed: ' + startStatus);

  const found = await findInstance(definition, patientId);
  if (!found) {
    return {
      scenario: name, label: c.label, workerEnv: c.workerEnv, processInstanceKey: null,
      state: null, reached: [], variableCount: 0, variables: {}, trace: [], incidents: [],
      status: 'FAIL',
      problems: ['no ' + definition + ' instance was started (HTTP ' + startStatus + ')']
    };
  }
  const key = String(found.processInstanceKey);
  const outcome = await waitForInstance(key, { patientId });
  const reached = (await elements(key)).map(e => e.id);
  const cnt = counts(await elements(key));
  const v = await vars(key);
  const problems = [];
  if (outcome.error) problems.push(outcome.error);
  for (const want of c.expectReached || []) {
    if (!reached.includes(want)) problems.push('did not reach ' + want);
  }
  for (const [want, min] of Object.entries(c.expectMinOccurrences || {})) {
    if ((cnt[want] || 0) < min) problems.push(want + ' occurred ' + (cnt[want] || 0) + ' time(s), expected ' + min);
  }
  if (c.expectEnd) {
    const inst = await instance(key);
    if (!inst || inst.state !== c.expectEnd) problems.push('final state ' + (inst && inst.state) + ', expected ' + c.expectEnd);
  }
  for (const [want, expected] of Object.entries(c.expectVars || {})) {
    const actual = v[want];
    if (unquote(actual) !== String(expected)) {
      problems.push('variable ' + want + ' = ' + JSON.stringify(actual) + ', expected ' + JSON.stringify(expected));
    }
  }
  // REQ-21 is about absence: the strongest test is that no card-shaped variable
  // exists in the instance at all, checked by name.
  const forbiddenNames = /^(cardNumber|cardHolder|cardholderName|pan|cvv|cvc|securityCode|cardSecurityCode|fullCardNumber|expiryDate|pin|trackData)$/i;
  for (const name of Object.keys(v)) {
    if (forbiddenNames.test(name)) {
      problems.push('a card-like variable reached the process: ' + name);
    }
  }
  // The worker's own log is the evidence that a failure path ran rather than
  // being described: a path that was taken leaves a line in it.
  if (c.expectWorkerLog?.length) {
    const logFile = path.join(EVIDENCE, 'workers-' + name + '.log');
    const log = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8') : '';
    for (const phrase of c.expectWorkerLog) {
      if (!log.includes(phrase)) {
        problems.push('worker log does not contain ' + JSON.stringify(phrase));
      }
    }
  }
  return {
    scenario: name, label: c.label, workerEnv: c.workerEnv, processInstanceKey: key,
    state: (await instance(key))?.state, reached, variableCount: Object.keys(v).length,
    variables: v, trace: outcome.trace, incidents: outcome.incidents,
    status: problems.length ? 'FAIL' : 'PASS', problems
  };
}

const all = process.argv[2] === 'all' || !process.argv[2];
const names = all
  ? Object.keys(SCENARIOS).filter(n => !SCENARIOS[n].skip)
  : [process.argv[2]];
for (const n of names) {
  if (!SCENARIOS[n]) {
    console.error('unknown scenario: ' + n + '  (one of ' + Object.keys(SCENARIOS).join(', ') + ')');
    process.exit(2);
  }
}
if (all) {
  const skipped = Object.keys(SCENARIOS).filter(n => SCENARIOS[n].skip);
  for (const n of skipped) {
    console.log('skipping %s: %s', n, SCENARIOS[n].skipReason || 'marked skip');
  }
}

fs.mkdirSync(EVIDENCE, { recursive: true });
const results = [];
for (const n of names) {
  const c = SCENARIOS[n];
  console.log('\n=== %s ===', c.label);
  if (Object.keys(c.workerEnv).length) {
    console.log('    worker environment needed: '
      + Object.entries(c.workerEnv).map(([k, v]) => k + '=' + v).join(' '));
  }
  const r = await runCase(n);
  results.push(r);
  console.log('    instance %s  state=%s  %s', r.processInstanceKey, r.state, r.status);
  for (const t of r.trace) {
    console.log('      ' + String(t.kind).padEnd(9) + String(t.elementId).padEnd(36) + 'by ' + t.by
      + (t.by === 'worker' ? '  [' + t.type + ']' : ''));
  }
  for (const p of r.problems) console.log('      ! ' + p);
  console.log('    worker-set variables: %s', Object.keys(r.variables).filter(k =>
    /slot|capacity|payment|refund|letter|correspondence|bloodTest|report|duplicate|cardData|episode/.test(k)).join(', '));
}
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const file = path.join(EVIDENCE, 'worker-demo-' + stamp + '.json');
fs.writeFileSync(file, JSON.stringify({
  target: BASE, executedAt: new Date().toISOString(), results,
  summary: { total: results.length, passed: results.filter(r => r.status === 'PASS').length }
}, null, 2));
console.log('\n%s of %s scenario(s) passed   -> %s',
  results.filter(r => r.status === 'PASS').length, results.length, path.relative(process.cwd(), file));
process.exit(results.every(r => r.status === 'PASS') ? 0 : 1);
