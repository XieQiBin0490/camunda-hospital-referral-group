/**
 * A button inside Tasklist that runs the whole diagram - slowly, so you can watch.
 *
 *   node tools/tasklist-button.mjs
 *
 * It opens Tasklist in a visible browser and injects a small control panel into
 * the page. You click a button; this process then drives the run. Between every
 * step it switches to the **Process** tab of the task, which is the diagram view,
 * and waits there long enough for the green markers to be seen moving from the
 * first activity to the last - the point is to watch the model run, not to have it
 * finish before you look.
 *
 * Buttons:
 *   Run the operational process   - the full 19-form path, paced for watching
 *   Run all six processes         - the whole model family
 *   Pause / Resume                - hold the run where it is
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

const PACE = Number(process.env.PACE_MS || 5000);       // how long to sit on the diagram
const SETTLE = Number(process.env.SETTLE_MS || 1500);   // how long a form takes to render

const OPERATIONAL = ['PR_Operational_Merged'];
const ALL = ['PR_Operational_Merged', 'PR_Landscape', 'PR_ReferralToAuthorisation',
  'PR_TreatmentToAftercare', 'PR_EnquiryHandling', 'PR_ManagementReporting'];

/** What to answer, by variable name - the same table the six-process run uses. */
const VALUE = {
  documentsComplete: true, referralDecision: 'accepted', redirectDestination: '',
  referralUrgency: 'routine', suitableSlotFound: true, appointmentWithin14Days: true,
  appointmentReference: 'APT-0001', contactSuccessful: true, consentGiven: true,
  requestAuthorised: true, treatmentCapacityConfirmed: true, fundingApproved: true,
  advancePaymentRequired: false, chargeAmount: 480, approvedAmount: 480,
  paymentStatus: 'confirmed', refundRequired: false, furtherCyclesPlanned: false,
  fitToContinue: true, urgentPostponement: false, letterApproved: true,
  suspectedClinicalError: false, accessibleFormatRequired: false, letterDelayDays: 0,
  financialImpact: false, followUpSlotWithinPeriod: false, appointmentPaid: false,
  enquiryType: 'administrative', reportPeriod: '2026-09', treatmentCode: 'TRT-001',
  treatmentCycles: 1
};

/**
 * The operational path, by task, with the answers that were verified to carry the
 * instance to COMPLETED - nineteen forms. The value may be an array, which is
 * consulted on each visit: the funding route is a loop, and walking it once
 * through the loop is the point of the demonstration.
 */
const PLAN_OPERATIONAL = {
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
  T_ValidateTreatmentRequest: {},
  T_DetermineFundingRoute: [
    { fundingApproved: false, advancePaymentRequired: true },
    { fundingApproved: true }
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

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
async function api(method, url, body) {
  const r = await fetch(API + url, {
    method,
    headers: { Authorization: AUTH, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const t = await r.text();
  if (r.status >= 300) throw new Error(`${method} ${url} -> ${r.status} ${t.slice(0, 160)}`);
  try { return t ? JSON.parse(t) : null; } catch { return null; }
}
const search = (kind, body) => api('POST', `/${kind}/search`, body || {});

function evidenceDir() {
  const dir = fs.existsSync(path.join(ROOT, '05_Test_Evidence'))
    ? path.join(ROOT, '05_Test_Evidence', 'watch-run')
    : path.join(ROOT, 'evidence', 'watch-run');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}
const SHOTS = evidenceDir();
const transcript = [];
const say = (s = '') => { console.log(s); transcript.push(s); };

function locateJar() {
  for (const d of [path.join(ROOT, 'workers'), path.join(ROOT, '04_Java_Worker')]) {
    for (const p of [path.join(d, 'target', 'hospital-external-workers-1.0.0.jar'),
      path.join(d, 'prebuilt', 'hospital-external-workers-1.0.0.jar')]) {
      if (fs.existsSync(p)) return p;
    }
  }
  return null;
}
const EDGE = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe'].find(p => fs.existsSync(p));

function schemaFields(formJson) {
  const out = [];
  const walk = (cs) => {
    for (const c of cs || []) {
      if (!c || typeof c !== 'object') continue;
      if (c.key && !['group', 'spacer', 'image', 'iframe', 'text', 'button'].includes(c.type || '')) {
        out.push({ key: c.key, label: (c.label || '').trim() });
      }
      walk(c.components);
    }
  };
  walk(formJson.components);
  return out;
}

async function login(page) {
  await page.goto(BASE + '/tasklist', { waitUntil: 'networkidle2', timeout: 60000 });
  if (page.url().includes('/login')) {
    await page.type('input[name="username"]', 'demo', { delay: 20 });
    await page.type('input[name="password"]', 'demo', { delay: 20 });
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 }).catch(() => null),
      page.click('button[type=submit]')
    ]);
  }
  await sleep(1000);
}

async function clickByText(page, pattern) {
  return page.evaluate((p) => {
    const re = new RegExp(p, 'i');
    const b = [...document.querySelectorAll('button, a, [role=button]')]
      .find(x => re.test((x.innerText || '').trim()) && (x.offsetWidth || x.offsetHeight));
    if (b) { b.click(); return (b.innerText || '').trim(); }
    return null;
  }, pattern);
}

async function prepareForm(page, schema, values) {
  return page.evaluate((sch, vals) => {
    const done = [], toType = [], marked = [];
    const leaves = [...document.querySelectorAll('.fjs-element')].filter(el => {
      if (!el.querySelector('input, textarea, select')) return false;
      return ![...el.querySelectorAll('.fjs-element')]
        .some(x => x !== el && x.querySelector('input, textarea, select'));
    });
    const labelOf = (el) => ((el.querySelector('label') || {}).innerText || '').trim().toLowerCase();
    const norm = (s) => (s || '').trim().toLowerCase().replace(/\s+/g, ' ');
    for (const { key, label } of sch) {
      if (!(key in vals)) continue;
      const value = vals[key];
      const el = leaves.find(x => labelOf(x) === norm(label)) ||
        leaves.find(x => labelOf(x).startsWith(norm(label).slice(0, 24))) ||
        leaves[sch.findIndex(s => s.key === key)];
      if (!el) continue;
      const input = el.querySelector('input, textarea, select');
      const kind = input.tagName === 'SELECT' ? 'select' : (input.type || 'text');
      input.setAttribute('data-watch-key', key);
      marked.push(key);
      if (kind === 'checkbox') {
        if (!!input.checked !== !!value) input.click();
        done.push(`${key}=${!!value}`);
      } else if (kind === 'radio') {
        const opts = [...el.querySelectorAll('input[type=radio]')];
        (opts.find(r => r.value === String(value)) || opts[0])?.click();
        done.push(`${key}=${value}`);
      } else if (kind === 'select') {
        input.value = String(value);
        input.dispatchEvent(new Event('change', { bubbles: true }));
        done.push(`${key}=${value}`);
      } else {
        toType.push({ key, value: String(value) });
        done.push(`${key}=${value}`);
      }
    }
    return { done, toType, marked };
  }, schema, values);
}

async function typeInto(page, key, value) {
  const sel = `[data-watch-key="${key}"]`;
  await page.click(sel);
  await page.keyboard.down('Control');
  await page.keyboard.press('KeyA');
  await page.keyboard.up('Control');
  await page.type(sel, value, { delay: 20 });
}

async function readFields(page) {
  return page.evaluate(() => {
    const out = {};
    for (const el of document.querySelectorAll('[data-watch-key]')) {
      out[el.getAttribute('data-watch-key')] =
        el.type === 'checkbox' ? String(!!el.checked) : String(el.value ?? '');
    }
    return out;
  });
}

// ------------------------------------------------------------------- the run
let paused = false;
let stopRequested = false;

async function gate() {
  while (paused && !stopRequested) await sleep(300);
}

/**
 * Centre the diagram on the activity that is running, and zoom it to something
 * readable.
 *
 * Fitted to the window, an eight-lane model 10,000 px wide is a grey smear and the
 * markers cannot be seen - which defeats the point. bpmn-js does not scroll: it
 * positions the whole diagram with an SVG transform, so neither the zoom buttons
 * nor scrollIntoView put the active node where you can see it. Setting that
 * transform directly, from the node's own bounding box, does.
 */
async function focusActivity(page, elementId) {
  return page.evaluate((id) => {
    const host = document.querySelector('.bjs-container') || document.querySelector('.djs-container');
    const el = document.querySelector(`[data-element-id="${id}"]`);
    if (!host || !el) return false;
    const g = host.querySelector('g.viewport') || host.querySelector('svg > g');
    if (!g) return false;

    // Nodes live inside nested <g> elements, so their own getBBox() is in local
    // coordinates and centring on it lands somewhere else entirely. Work in screen
    // coordinates instead: set the scale, measure where the node ended up, then
    // shift the viewport by the difference between it and the middle of the panel.
    const m = g.transform.baseVal.consolidate();
    const cur = m ? { e: m.matrix.e, f: m.matrix.f } : { e: 0, f: 0 };
    const SCALE = 1.0;                       // bpmn-js natural size
    g.setAttribute('transform', `translate(${cur.e}, ${cur.f}) scale(${SCALE})`);

    const er = el.getBoundingClientRect();
    const hr = host.getBoundingClientRect();
    const dx = (hr.left + hr.width / 2) - (er.left + er.width / 2);
    const dy = (hr.top + hr.height / 2) - (er.top + er.height / 2);
    g.setAttribute('transform', `translate(${cur.e + dx}, ${cur.f + dy}) scale(${SCALE})`);
    return { dx: Math.round(dx), dy: Math.round(dy), w: Math.round(er.width) };
  }, elementId);
}

/** Sit on the diagram view so the markers are seen moving. */
async function showDiagram(page, taskKey, label, pace, elementId) {
  try {
    await page.goto(BASE + '/tasklist/' + taskKey, { waitUntil: 'networkidle2', timeout: 60000 });
    await sleep(SETTLE);
    await clickByText(page, '^process$');     // the diagram tab
    await sleep(1400);
    if (elementId) {
      const info = await focusActivity(page, elementId);
      say(`      diagram centred on ${elementId}: ${JSON.stringify(info)}`);
    }
    await page.screenshot({ path: path.join(SHOTS, `step-${label}.png`) });
    await sleep(pace);
    await clickByText(page, '^task$');        // back to the form, ready to fill it
    await sleep(SETTLE);
  } catch { /* the view is a nicety, never a reason to fail the run */ }
}

async function driveProcess(page, definitionId, patientId, started, status) {
  const key = String(started.processInstanceKey);
  const short = definitionId.replace(/^PR_/, '');
  const plan = definitionId === 'PR_Operational_Merged' ? PLAN_OPERATIONAL : null;
  const visits = new Map();
  let n = 0, state = 'ACTIVE';

  for (let step = 0; step < 40; step++) {
    await gate();
    if (stopRequested) break;

    let task = null;
    for (let wait = 0; wait < 90; wait++) {
      const t = await search('user-tasks', {
        filter: { processInstanceKey: key, state: 'CREATED' }, page: { from: 0, limit: 5 }
      });
      task = (t.items || [])[0];
      if (task) break;
      const inst = await search('process-instances', { filter: { processInstanceKey: key } });
      const found = (inst.items || [])[0];
      if (found) { state = found.state; if (state !== 'ACTIVE') break; }
      await sleep(400);
    }
    if (!task) break;

    // show where the process is before touching the form
    await showDiagram(page, task.userTaskKey, `${short}-${String(n + 1).padStart(2, '0')}-before`, PACE, task.elementId);

    let schema = [];
    if (task.formKey) {
      try {
        const f = await api('GET', `/forms/${task.formKey}`);
        const s = typeof f.schema === 'string' ? JSON.parse(f.schema) : f.schema;
        if (s && Array.isArray(s.components)) schema = schemaFields(s);
      } catch { /* no schema, nothing to fill */ }
    }
    const values = {};
    if (plan) {
      // hand-verified path: answer per task, with the visit count for loops
      const v = visits.get(task.elementId) || 0;
      visits.set(task.elementId, v + 1);
      const def = plan[task.elementId] ?? {};
      const chosen = Array.isArray(def) ? (def[Math.min(v, def.length - 1)] ?? {}) : def;
      for (const k of Object.keys(chosen)) values[k] = chosen[k];
    } else {
      for (const f of schema) if (f.key in VALUE) values[f.key] = VALUE[f.key];
    }

    const prepared = await prepareForm(page, schema, values);
    for (const { key: k, value } of prepared.toType) await typeInto(page, k, value);
    await sleep(400);

    n++;
    await page.screenshot({ path: path.join(SHOTS, `step-${short}-${String(n).padStart(2, '0')}-form.png`) });
    status(`running ${short}: form ${n} - ${task.name || task.elementId}`);

    if (!await clickByText(page, '^complete task$|^complete$')) {
      throw new Error(`no Complete button on ${task.elementId}`);
    }
    for (let i = 0; i < 30; i++) {
      await sleep(400);
      const still = await search('user-tasks', { filter: { userTaskKey: String(task.userTaskKey), state: 'CREATED' } });
      if (!(still.items || []).length) break;
      if (i === 8) await clickByText(page, '^complete task$|^complete$');
    }
  }

  const inst = await search('process-instances', { filter: { processInstanceKey: key } });
  const finalState = (inst.items || [])[0]?.state;
  const inc = await search('incidents', { filter: { processInstanceKey: key, state: 'PENDING' } });
  const reached = await search('element-instances', { filter: { processInstanceKey: key }, page: { from: 0, limit: 200 } });
  return {
    definitionId, patientId, processInstanceKey: key, finalState,
    openIncidents: (inc.items || []).length, formsCompleted: n,
    activitiesReached: [...new Set((reached.items || []).map(e => e.elementId))].length
  };
}

async function runFamily(page, list, status) {
  const results = [];
  for (const definitionId of list) {
    await gate();
    if (stopRequested) break;
    const patientId = 'WATCH-' + Date.now().toString().slice(-6);
    status(`starting ${definitionId}`);
    let started;
    try {
      started = await api('POST', '/process-instances', {
        processDefinitionId: definitionId,
        variables: { patientId, ...(definitionId === 'PR_ManagementReporting' ? { reportPeriod: VALUE.reportPeriod } : {}) }
      });
    } catch (e) {
      results.push({ definitionId, started: false, error: e.message });
      continue;
    }
    for (let i = 0; i < 40; i++) {
      const inst = await search('process-instances', { filter: { processInstanceKey: String(started.processInstanceKey) } });
      if ((inst.items || []).length) break;
      await sleep(500);
    }
    try {
      const r = await driveProcess(page, definitionId, patientId, started, status);
      results.push({ ...r, started: true });
      status(`${definitionId}: ${r.formsCompleted} form(s), state=${r.finalState}, incidents=${r.openIncidents}`);
    } catch (e) {
      results.push({ definitionId, started: true, error: e.message });
      status(`${definitionId}: stopped - ${e.message}`);
    }
  }
  return results;
}

// ------------------------------------------------------------------- main
const jar = locateJar();
if (!jar) { console.error('No worker jar. Build it first: mvn -f workers/pom.xml package'); process.exit(2); }

const health = await fetch(API + '/topology', { headers: { Authorization: AUTH } }).catch(() => null);
if (!health || !health.ok) {
  console.error('The cluster is not answering on ' + API + '. Start it: c8run.exe start');
  process.exit(2);
}

const defs = await search('process-definitions', { page: { from: 0, limit: 50 } });
const have = new Set((defs.items || []).map(d => d.processDefinitionId));
if (ALL.some(p => !have.has(p))) {
  say('deploying the models and forms first');
  const dep = spawn(process.execPath, [path.join(HERE, 'deploy-all.mjs')], { stdio: 'ignore', cwd: ROOT });
  await new Promise(r => dep.on('exit', r));
}

const fleetLog = path.join(SHOTS, 'worker-fleet.log');
const fleet = spawn('java', ['--enable-native-access=ALL-UNNAMED', '-jar', jar],
  { cwd: path.dirname(jar), stdio: ['ignore', 'pipe', 'pipe'] });
const stream = fs.createWriteStream(fleetLog);
fleet.stdout.pipe(stream);
fleet.stderr.pipe(stream);
say('starting the worker fleet (the automated activities must be done by something)');
for (let i = 0; i < 60; i++) {
  await sleep(500);
  if (fs.existsSync(fleetLog) && fs.readFileSync(fleetLog, 'utf8').includes('workers subscribed and polling')) break;
}
say('worker fleet: subscribed');

const browser = await puppeteer.launch({
  executablePath: EDGE, headless: false,
  defaultViewport: { width: 1500, height: 1000 },
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--start-maximized'],
  protocolTimeout: 420000
});
const page = await browser.newPage();

// the control panel, injected into Tasklist itself
const PANEL = `
(() => {
  if (document.getElementById('dsh-run-panel')) return;
  const box = document.createElement('div');
  box.id = 'dsh-run-panel';
  box.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:2147483647;background:#161616;color:#fff;' +
    'border:1px solid #393939;border-radius:12px;padding:14px 16px;font:13px/1.5 system-ui,sans-serif;' +
    'box-shadow:0 8px 28px rgba(0,0,0,.35);max-width:320px';
  box.innerHTML =
    '<div style="font-weight:600;font-size:14px;margin-bottom:8px">Process walkthrough</div>' +
    '<div id="dsh-run-status" style="color:#c6c6c6;margin-bottom:10px;min-height:34px">Ready. Pick a run.</div>' +
    '<button id="dsh-run-ops" style="display:block;width:100%;margin-bottom:6px;padding:9px;border:0;border-radius:6px;' +
      'background:#0f62fe;color:#fff;font-weight:600;cursor:pointer">Run the operational process</button>' +
    '<button id="dsh-run-all" style="display:block;width:100%;margin-bottom:6px;padding:9px;border:0;border-radius:6px;' +
      'background:#393939;color:#fff;font-weight:600;cursor:pointer">Run all six processes</button>' +
    '<button id="dsh-run-pause" style="display:block;width:100%;padding:9px;border:1px solid #6f6f6f;border-radius:6px;' +
      'background:transparent;color:#fff;cursor:pointer">Pause</button>';
  document.body.appendChild(box);
  const s = document.getElementById('dsh-run-status');
  window.__dshStatus = (t) => { s.textContent = t; };
  document.getElementById('dsh-run-ops').onclick = () => window.__dshRun && window.__dshRun('ops');
  document.getElementById('dsh-run-all').onclick = () => window.__dshRun && window.__dshRun('all');
  document.getElementById('dsh-run-pause').onclick = (e) => {
    const p = window.__dshPause ? window.__dshPause() : false;
    e.target.textContent = p ? 'Resume' : 'Pause';
  };
})();
`;

// Register the panel before any navigation so it survives every page the run
// visits, then land on the Processes page - the one with a 启动流程 button per
// process - so the control panel appears exactly where a person would look.
await page.evaluateOnNewDocument(PANEL);
page.on('domcontentloaded', () => { page.evaluate(PANEL).catch(() => {}); });

await login(page);
await page.goto(BASE + '/tasklist/processes', { waitUntil: 'networkidle2', timeout: 60000 }).catch(() => {});
await sleep(1500);
await page.evaluate(PANEL).catch(() => {});
say('control panel injected into Tasklist - click a button in the browser');
say(`pacing: ${PACE} ms on the diagram between steps`);

let runDoneResolve = null;
const runDone = new Promise(r => { runDoneResolve = r; });

page.exposeFunction('__dshRun', async (which) => {
  if (which !== 'ops' && which !== 'all') return;
  const list = which === 'ops' ? OPERATIONAL : ALL;
  const status = (t) => {
    say('  ' + t);
    page.evaluate((x) => window.__dshStatus && window.__dshStatus(x), t).catch(() => {});
  };
  try {
    const results = await runFamily(page, list, status);
    const ok = results.filter(r => r.finalState === 'COMPLETED' && r.openIncidents === 0).length;
    status(`done: ${ok} of ${list.length} ran to completion`);
    fs.writeFileSync(path.join(SHOTS, 'watch-run.json'), JSON.stringify({ results, transcript }, null, 2));
    fs.writeFileSync(path.join(SHOTS, 'watch-run.log'), transcript.join('\n') + '\n');
  } catch (e) {
    say('run failed: ' + e.message);
    status('run failed: ' + e.message);
  } finally {
    if (runDoneResolve) runDoneResolve();
  }
});
page.exposeFunction('__dshPause', () => { paused = !paused; return paused; });

// AUTOSTART=ops|all presses the button for you, so the run can be verified without
// a person watching; left unset, the buttons are the only way to start.
const AUTOSTART = process.env.AUTOSTART;
if (AUTOSTART) {
  say(`AUTOSTART=${AUTOSTART}: pressing the button for you`);
  // Click and move on: the run navigates the page repeatedly, so an awaited
  // evaluate would be torn down by the next navigation.
  page.evaluate((w) => { window.__dshRun(w); }, AUTOSTART).catch(() => {});
  await runDone;
  await browser.close();
  fleet.kill();
  await sleep(500);
  process.exit(0);
}

say('');
say('The browser is open on Tasklist. Click "Run the operational process" there.');
say('Press Ctrl+C here to stop.');

process.on('SIGINT', async () => {
  stopRequested = true;
  say('stopping');
  try { await browser.close(); } catch {}
  fleet.kill();
  process.exit(0);
});

// stay alive until the browser is closed
await new Promise(resolve => browser.on('disconnected', resolve));
fleet.kill();
say('browser closed, worker fleet stopped');
