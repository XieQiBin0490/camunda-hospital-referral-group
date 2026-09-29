/**
 * The interactive Tasklist run: one command, and the browser walks the process
 * form by form.
 *
 *   node tools/run-form-tasklist.mjs
 *
 * What it does, in order:
 *   1. starts the Java worker fleet (so the automated activities are done while
 *      you watch the browser, not by this script);
 *   2. starts one referral and cancels the two strategic twins, because all three
 *      models declare the same start message and you would otherwise see three
 *      copies of every task;
 *   3. opens Tasklist in a visible browser and logs in as demo/demo;
 *   4. finds the next open task of the operational instance, opens it, assigns it,
 *      fills the form, clicks "Complete Task", and repeats - so the browser moves
 *      from one form to the next until the instance finishes;
 *   5. writes a screenshot of every form it completed to evidence/form-demo/.
 *
 * This is the browser-level counterpart to run-worker-demo.mjs: that one plays the
 * humans through the REST API, this one plays them through the Tasklist UI with
 * the real forms.
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = 'http://127.0.0.1:8080';
const API = BASE + '/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');
const PROCESS = 'PR_Operational_Merged';
const START_MESSAGE = 'Patient referral';
const STRATEGIC_TWINS = ['PR_Landscape', 'PR_ReferralToAuthorisation'];

const PATIENT = 'UI-' + Date.now();
const STEP_DELAY = Number(process.env.STEP_DELAY_MS || 500);
const HEADLESS = process.env.HEADLESS === '1';

// ----------------------------------------------------------------- what a human types
// Keyed by model element id. A value may be an array, which supplies a different
// answer on each visit (the funding route loops until it is approved).
const PLAN = {
  T_ReceiveReferral: { documentsComplete: true },
  T_CheckReferralDocuments: { documentsComplete: true },
  T_ClinicalReviewReferral: { referralDecision: 'accepted' },
  T_RecordReferralDecision: { referralDecision: 'accepted' },
  T_ForwardAcceptedReferral: {},
  T_ReceiveBookingRequest: { referralUrgency: 'routine' },
  T_SelectAndBookSlot: { appointmentReference: 'APT-0001', appointmentWithin14Days: true },
  T_ConfirmBooking: { appointmentReference: 'APT-0001' },
  T_TelephonePatient: {},
  T_RecordContactAttempt: { contactSuccessful: true },
  T_NewPatientConsultation: { consentGiven: true },
  T_RecordPatientConsent: {},
  T_CreateTreatmentBookingRequest: { requestAuthorised: true },
  T_ValidateTreatmentRequest: { requestAuthorised: true },
  T_DetermineFundingRoute: [
    { fundingApproved: false, advancePaymentRequired: true, chargeAmount: 480 },
    { fundingApproved: true, advancePaymentRequired: true, chargeAmount: 480 }
  ],
  T_RequestFundingApproval: { fundingApproved: true },
  T_RecordFundingApproval: {},
  T_RecordPayment: {},
  T_HandlePaymentFailure: {},
  T_MarkForInvestigation: {},
  T_ResolveTransaction: {},
  T_AuthoriseUrgentTreatment: {},
  T_ReferUnconfirmedPayment: {},
  T_ConfirmTreatmentSchedule: {},
  T_ResolveCapacity: { appointmentReference: 'APT-0002' },
  T_KeepPending: {},
  T_AdviseNoTreatment: {},
  T_ReturnUnauthorisedRequest: {}
};

// ----------------------------------------------------------------- tiny API client
async function api(method, url, body) {
  const r = await fetch(API + url, {
    method,
    headers: { Authorization: AUTH, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const t = await r.text();
  if (r.status >= 300) throw new Error(`${method} ${url} -> ${r.status} ${t.slice(0, 200)}`);
  try { return t ? JSON.parse(t) : null; } catch { return null; }
}
const search = (kind, body) => api('POST', `/${kind}/search`, body || {});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/** The instance's variables, with quotes stripped and booleans coerced. */
async function currentVars(key) {
  const r = await search('variables', { filter: { processInstanceKey: key }, page: { from: 0, limit: 100 } });
  const out = {};
  for (const v of r.items || []) {
    let val = v.value;
    if (typeof val === 'string') {
      if (val === 'true') val = true;
      else if (val === 'false') val = false;
      else val = val.replace(/^"|"$/g, '');
    }
    out[v.name] = val;
  }
  return out;
}

function evidenceDir() {
  const dir = fs.existsSync(path.join(ROOT, '05_Test_Evidence'))
    ? path.join(ROOT, '05_Test_Evidence', 'form-demo')
    : path.join(ROOT, 'evidence', 'form-demo');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
const SHOTS = evidenceDir();
const transcript = [];
const say = (s) => { console.log(s); transcript.push(s); };

function locateJar() {
  const dirs = [path.join(ROOT, 'workers'), path.join(ROOT, '04_Java_Worker')];
  for (const d of dirs) {
    for (const p of [path.join(d, 'target', 'hospital-external-workers-1.0.0.jar'),
      path.join(d, 'prebuilt', 'hospital-external-workers-1.0.0.jar')]) {
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}

function locateForms() {
  for (const d of [path.join(ROOT, 'output', 'forms'), path.join(ROOT, '03_Forms')]) {
    if (fs.existsSync(d)) return d;
  }
  throw new Error('cannot find the forms directory');
}

// ----------------------------------------------------------------- form field mapping
/** key -> index among input-bearing components, from the form schema itself. */
function schemaInputKeys(formJson) {
  const keys = [];
  const walk = (comps) => {
    for (const c of comps || []) {
      if (!c || typeof c !== 'object') continue;
      const type = c.type || '';
      const isInput = c.key && !['group', 'spacer', 'image', 'iframe', 'text', 'button'].includes(type);
      if (isInput) keys.push({ key: c.key, type, label: (c.label || '').trim() });
      if (Array.isArray(c.components)) walk(c.components);
    }
  };
  walk(formJson.components);
  return keys;
}

function formFileFor(formId, formsDir) {
  const candidates = [path.join(formsDir, formId + '.form'), path.join(formsDir, formId)];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  return null;
}

// ----------------------------------------------------------------- browser helpers
/** What the rendered form currently holds for the keys the plan cares about. */
async function readBackFields(page, values) {
  return page.evaluate((vals) => {
    const out = {};
    const all = [...document.querySelectorAll('.fjs-element')];
    const leaves = all.filter(el => {
      if (!el.querySelector('input, textarea, select')) return false;
      const inner = [...el.querySelectorAll('.fjs-element')]
        .some(x => x !== el && x.querySelector('input, textarea, select'));
      return !inner;
    });
    for (const el of leaves) {
      const input = el.querySelector('input, textarea, select');
      const label = ((el.querySelector('label') || {}).innerText || '').trim();
      if (!input) continue;
      const v = input.type === 'checkbox' ? String(!!input.checked) : String(input.value || '');
      out[label] = v;
    }
    const wanted = Object.values(vals).map(v => String(v));
    const present = Object.entries(out).filter(([, v]) => v !== '' && v !== 'false');
    return {
      fields: out,
      allPresent: wanted.length === 0 || present.length >= wanted.length
    };
  }, values);
}

async function login(page) {
  await page.goto(BASE + '/tasklist', { waitUntil: 'networkidle2', timeout: 60000 });
  if (page.url().includes('/login')) {
    await page.type('input[name="username"]', 'demo', { delay: 30 });
    await page.type('input[name="password"]', 'demo', { delay: 30 });
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 }).catch(() => null),
      page.click('button[type=submit]')
    ]);
  }
  await sleep(1200);
}

async function clickByText(page, pattern) {
  const clicked = await page.evaluate((p) => {
    const re = new RegExp(p, 'i');
    const b = [...document.querySelectorAll('button, a, [role=button]')]
      .find(x => re.test((x.innerText || '').trim()) && (x.offsetWidth || x.offsetHeight));
    if (b) { b.click(); return (b.innerText || '').trim(); }
    return null;
  }, pattern);
  return clicked;
}

/**
 * Fill the fields the plan supplies, leaving anything else as it is.
 *
 * form-js wraps a form in a container that is itself an `.fjs-element` and holds
 * every input, so a positional match against `.fjs-element` addresses the wrong
 * thing - it once typed a boolean into a text field. Only *leaf* field elements
 * are candidates here, and each is matched to the schema by its label, which is
 * unique inside a form. Position is the fallback.
 */
/**
 * Prepare the form: mark every field the plan cares about, set the ones that are
 * a click (checkbox / radio / select), and report which need typing.
 *
 * Text fields are typed for real from Node. Writing `.value` directly updates the
 * DOM but not the form framework's state, so the box stays visually empty and the
 * submit goes unproven.
 */
async function prepareForm(page, schemaKeys, values, processVars) {
  return page.evaluate((schema, vals, existing) => {
    const done = [];
    const toType = [];
    const marked = [];
    const all = [...document.querySelectorAll('.fjs-element')];
    const leaves = all.filter(el => {
      if (!el.querySelector('input, textarea, select')) return false;
      const inner = [...el.querySelectorAll('.fjs-element')]
        .some(x => x !== el && x.querySelector('input, textarea, select'));
      return !inner;
    });
    const labelOf = (el) => ((el.querySelector('label') || {}).innerText || '').trim().toLowerCase();
    const norm = (s) => (s || '').trim().toLowerCase().replace(/\s+/g, ' ');

    for (const { key, label } of schema) {
      // A form submits every field it renders, so a blank field would overwrite an
      // existing process variable with an empty string - which is how
      // appointmentReference was wiped by the next task's form. Re-send what the
      // process already holds unless the plan says otherwise.
      let value;
      if (key in vals) value = vals[key];
      else if (key in existing) value = existing[key];
      else continue;
      let el = leaves.find(x => labelOf(x) === norm(label));
      if (!el) el = leaves.find(x => labelOf(x).startsWith(norm(label).slice(0, 24)));
      if (!el) el = leaves[schema.findIndex(s => s.key === key)];
      if (!el) { done.push(`${key}: no field found`); continue; }
      const input = el.querySelector('input, textarea, select');
      const kind = input.tagName === 'SELECT' ? 'select' : (input.type || 'text');
      input.setAttribute('data-hpas-key', key);
      marked.push(key);
      if (kind === 'checkbox') {
        if (!!input.checked !== !!value) input.click();
        done.push(`${key}=${!!value} (checkbox)`);
      } else if (kind === 'radio') {
        const opts = [...el.querySelectorAll('input[type=radio]')];
        const opt = opts.find(r => r.value === String(value)) || opts[Number(value) || 0];
        if (opt) { opt.click(); done.push(`${key}=${value} (radio)`); }
        else done.push(`${key}: no radio option for ${value}`);
      } else if (kind === 'select') {
        input.value = String(value);
        input.dispatchEvent(new Event('change', { bubbles: true }));
        done.push(`${key}=${value} (select)`);
      } else {
        toType.push({ key, value: String(value) });
        done.push(`${key}=${value} (${kind}, to type)`);
      }
    }
    return { done, toType, marked };
  }, schemaKeys, values, processVars || {});
}

/** Type one value, replacing whatever is there. */
async function typeInto(page, key, value) {
  const sel = `[data-hpas-key="${key}"]`;
  await page.click(sel);
  await page.keyboard.down('Control');
  await page.keyboard.press('KeyA');
  await page.keyboard.up('Control');
  await page.type(sel, value, { delay: 25 });
}

/** What the marked fields actually hold. */
async function readFields(page) {
  return page.evaluate(() => {
    const out = {};
    for (const el of document.querySelectorAll('[data-hpas-key]')) {
      const k = el.getAttribute('data-hpas-key');
      out[k] = el.type === 'checkbox' ? String(!!el.checked) : String(el.value ?? '');
    }
    return out;
  });
}

function mismatches(expected, actual) {
  const bad = [];
  for (const [k, v] of Object.entries(expected)) {
    const want = typeof v === 'boolean' ? String(v) : String(v);
    if (String(actual[k] ?? '') !== want) bad.push(`${k}: wanted ${JSON.stringify(want)}, form holds ${JSON.stringify(actual[k] ?? null)}`);
  }
  return bad;
}

// ----------------------------------------------------------------- main
const jar = locateJar();
if (!jar) {
  console.error('No worker jar. Build it first: mvn -f workers/pom.xml package');
  process.exit(2);
}
const formsDir = locateForms();
const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p => fs.existsSync(p));

say('=== Tasklist run ===');
say(`patient id     : ${PATIENT}`);
say(`worker jar     : ${path.relative(ROOT, jar)}`);
say(`forms          : ${path.relative(ROOT, formsDir)}`);

// 1. fleet
const fleetLog = fs.createWriteStream(path.join(SHOTS, 'worker-fleet.log'));
const fleet = spawn('java', ['--enable-native-access=ALL-UNNAMED', '-jar', jar],
  { cwd: path.dirname(jar), stdio: ['ignore', 'pipe', 'pipe'] });
fleet.stdout.pipe(fleetLog);
fleet.stderr.pipe(fleetLog);
say(`worker fleet   : started (pid ${fleet.pid}), waiting for it to subscribe`);
for (let i = 0; i < 60; i++) {
  await sleep(500);
  const log = fs.readFileSync(path.join(SHOTS, 'worker-fleet.log'), 'utf8');
  if (log.includes('workers subscribed and polling')) break;
}
say('worker fleet   : subscribed');

let browser = null;
let exitCode = 0;
try {
  // 2. start one referral, cancel the strategic twins
  await api('POST', '/messages/publication', {
    name: START_MESSAGE, correlationKey: PATIENT, variables: { patientId: PATIENT, documentsComplete: true }
  });
  await sleep(2500);
  let instance;
  for (let i = 0; i < 20 && !instance; i++) {
    const r = await search('process-instances', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 50 } });
    for (const inst of r.items || []) {
      if (inst.processDefinitionId === PROCESS) {
        const vars = await search('variables', { filter: { processInstanceKey: String(inst.processInstanceKey) } });
        if ((vars.items || []).some(v => v.name === 'patientId' && String(v.value).includes(PATIENT))) {
          instance = inst;
          break;
        }
      }
    }
    if (!instance) await sleep(500);
  }
  if (!instance) throw new Error('the operational instance did not start');
  const key = String(instance.processInstanceKey);
  say(`instance       : ${key} (${PROCESS})`);

  const actives = await search('process-instances', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 50 } });
  let cancelled = 0;
  for (const i of actives.items || []) {
    if (STRATEGIC_TWINS.includes(i.processDefinitionId)) {
      await api('POST', `/process-instances/${i.processInstanceKey}/cancellation`, {});
      cancelled++;
    }
  }
  say(`strategic twins: ${cancelled} cancelled (one start message wakes all three models)`);

  // 3. browser
  browser = await puppeteer.launch({
    executablePath: EDGE,
    headless: HEADLESS ? 'new' : false,
    defaultViewport: { width: 1500, height: 1000 },
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
    protocolTimeout: 420000
  });
  const page = await browser.newPage();
  await login(page);
  say(`tasklist       : logged in as demo, at ${page.url()}`);

  // 4. form by form
  const visit = new Map();
  const completed = [];
  let shot = 0;

  for (let step = 0; step < 40; step++) {
    // The next task may not exist yet: between two human steps there is usually an
    // automated activity, and the worker needs a moment to finish it. So wait for
    // a task to appear, and stop only when the instance itself has finished.
    let task = null;
    let state = 'ACTIVE';
    for (let wait = 0; wait < 40; wait++) {
      const tasks = await search('user-tasks', {
        filter: { processInstanceKey: key, state: 'CREATED' }, page: { from: 0, limit: 5 }
      });
      task = (tasks.items || [])[0];
      if (task) break;
      const inst = await search('process-instances', { filter: { processInstanceKey: key } });
      state = (inst.items || [])[0]?.state || 'UNKNOWN';
      if (state !== 'ACTIVE') break;
      await sleep(500);
    }
    if (!task) break;

    const n = visit.get(task.elementId) || 0;
    visit.set(task.elementId, n + 1);
    const def = PLAN[task.elementId] ?? {};
    const values = Array.isArray(def) ? (def[Math.min(n, def.length - 1)] ?? {}) : def;

    await page.goto(BASE + '/tasklist/' + task.userTaskKey, { waitUntil: 'networkidle2', timeout: 60000 });
    await sleep(STEP_DELAY + 2500);

    const rendered = await page.evaluate(() => document.querySelectorAll('.fjs-element').length);
    if (!rendered) {
      throw new Error(`the form did not render for ${task.elementId} (${task.userTaskKey})`);
    }

    const assigned = await clickByText(page, 'assign to me');
    if (assigned) await sleep(1200);

    // The task carries a formKey: ask the engine for the exact form it will
    // render, rather than guessing which file belongs to this task.
    let schemaKeys = null;
    if (task.formKey) {
      try {
        const form = await api('GET', `/forms/${task.formKey}`);
        const schema = typeof form.schema === 'string' ? JSON.parse(form.schema) : form.schema;
        if (schema && Array.isArray(schema.components)) {
          schemaKeys = schemaInputKeys(schema);
        }
      } catch (e) {
        say(`      (could not fetch form ${task.formKey}: ${e.message})`);
      }
    }
    if (!schemaKeys) {
      // fall back to the local file whose id matches the deployed formId
      const meta = task.formKey ? null : null;
      for (const f of fs.readdirSync(formsDir).filter(x => x.endsWith('.form'))) {
        const json = JSON.parse(fs.readFileSync(path.join(formsDir, f), 'utf8'));
        const keys = schemaInputKeys(json);
        if (Object.keys(values).length && Object.keys(values).every(k => keys.some(x => x.key === k))) {
          schemaKeys = keys;
          break;
        }
      }
    }
    if (!schemaKeys) schemaKeys = [];

    const prepared = await prepareForm(page, schemaKeys, values, currentVars(key));
    const filled = prepared.done;
    for (const { key, value } of prepared.toType) {
      await typeInto(page, key, value);
    }

    // Read every marked field back and re-type anything that did not land. A
    // dropped keystroke or an un-cleared box produces a value the gateway will not
    // match, and the instance quietly takes a different branch - which is exactly
    // what "accepte" and "acceptaccepte" did to a live run.
    //
    // Only fields this form actually renders are verified: the plan may name a
    // variable that belongs to the task after this one, and demanding it here
    // would fail on a form that is behaving correctly.
    const expected = Object.fromEntries(
      Object.entries(values).filter(([k]) => prepared.marked.includes(k)));
    let actual = await readFields(page);
    let bad = mismatches(expected, actual);
    for (let attempt = 0; attempt < 3 && bad.length; attempt++) {
      say(`      retrying ${bad.length} field(s): ${bad.join('; ')}`);
      for (const { key, value } of prepared.toType) {
        if (bad.some(b => b.startsWith(key + ':'))) await typeInto(page, key, value);
      }
      await sleep(300);
      actual = await readFields(page);
      bad = mismatches(expected, actual);
    }
    if (bad.length) {
      throw new Error(`the form for ${task.elementId} does not hold the planned values: ${bad.join('; ')}`);
    }
    if (prepared.done.some(d => d.includes('no field found'))) {
      say(`      note: ${prepared.done.filter(d => d.includes('no field found')).join(', ')}`);
    }
    await sleep(STEP_DELAY);

    shot++;
    const shotPath = path.join(SHOTS, `${String(shot).padStart(2, '0')}-${task.elementId}.png`);
    await page.screenshot({ path: shotPath, fullPage: true });

    const label = (task.name || task.elementId).slice(0, 52).padEnd(54);
    const submitted = await clickByText(page, '^complete task$|^complete$');
    if (!submitted) throw new Error(`no Complete button on ${task.elementId}`);
    completed.push({ elementId: task.elementId, userTaskKey: task.userTaskKey, values, filled,
      readBack: actual, screenshot: path.basename(shotPath) });
    say(`  ${String(shot).padStart(2, '0')}  ${label} filled: ${filled.join(', ') || '(nothing to fill)'}`);

    // Wait for the task to leave the list. If it is still there after a few
    // seconds the click did not register - the form had not finished wiring up -
    // so press it once more rather than completing the same form twice.
    let gone = false;
    for (let i = 0; i < 30; i++) {
      await sleep(500);
      const still = await search('user-tasks', { filter: { userTaskKey: String(task.userTaskKey), state: 'CREATED' } });
      if (!(still.items || []).length) { gone = true; break; }
      if (i === 8) {
        await clickByText(page, '^complete task$|^complete$');
      }
    }
    if (!gone) {
      const still = await search('user-tasks', { filter: { userTaskKey: String(task.userTaskKey), state: 'CREATED' } });
      if ((still.items || []).length) throw new Error(`task ${task.elementId} would not complete`);
    }
  }

  // 5. outcome
  const inst = await search('process-instances', { filter: { processInstanceKey: key } });
  const state = (inst.items || [])[0]?.state;
  const incidents = await search('incidents', { filter: { processInstanceKey: key, state: 'PENDING' } });
  const reached = await search('element-instances', { filter: { processInstanceKey: key } });
  const reachedIds = [...new Set((reached.items || []).map(e => e.elementId))];

  say('');
  say(`forms completed by hand : ${completed.length}`);
  say(`final instance state    : ${state}`);
  say(`open incidents          : ${(incidents.items || []).length}`);
  say(`automated activities    : ${reachedIds.filter(id => /^T_/.test(id)).length} task(s) reached in total`);
  say(`screenshots             : ${path.relative(process.cwd(), SHOTS)}`);

  const ok = state === 'COMPLETED' && (incidents.items || []).length === 0 && completed.length >= 5;
  say(`RESULT: ${ok ? 'the browser walked the whole process' : 'INCOMPLETE'}`);
  exitCode = ok ? 0 : 1;
  fs.writeFileSync(path.join(SHOTS, 'tasklist-run.json'), JSON.stringify({
    patientId: PATIENT, processInstanceKey: key, finalState: state,
    openIncidents: (incidents.items || []).length, formsCompleted: completed, transcript
  }, null, 2));
  say(`evidence: ${path.relative(process.cwd(), path.join(SHOTS, 'tasklist-run.json'))}`);
} catch (e) {
  say('FAILED: ' + e.message);
  exitCode = 1;
} finally {
  if (browser) {
    say('closing the browser in 8s');
    await sleep(8000);
    await browser.close();
  }
  fleet.kill();
  await sleep(500);
  fs.writeFileSync(path.join(SHOTS, 'tasklist-run.log'), transcript.join('\n') + '\n');
}
process.exit(exitCode);
