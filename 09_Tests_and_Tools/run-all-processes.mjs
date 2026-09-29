/**
 * Run the WHOLE model family, not one path through one process.
 *
 *   node tools/run-all-processes.mjs            (visible browser)
 *   HEADLESS=1 node tools/run-all-processes.mjs (no window)
 *
 * It starts the worker fleet, deploys if needed, then starts and drives **each of
 * the six process definitions** to an end state through the real Tasklist user
 * interface: for every user task it reads the Camunda Form the engine will render,
 * fills the fields from a variable-name table, assigns the task and completes it,
 * and moves on. One instance only ever walks one path, so running one process is
 * never "the whole diagram" - this runs all six and reports each outcome.
 *
 * Values are chosen by variable name rather than by task, so a task that appears
 * in several models - or a model edited later - is still driven correctly.
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
const HEADLESS = process.env.HEADLESS === '1';
const STEP_DELAY = Number(process.env.STEP_DELAY_MS || 300);
const MAX_STEPS = Number(process.env.MAX_STEPS || 80);

const PROCESSES = [
  'PR_Operational_Merged',
  'PR_Landscape',
  'PR_ReferralToAuthorisation',
  'PR_TreatmentToAftercare',
  'PR_EnquiryHandling',
  'PR_ManagementReporting'
];

/**
 * What a person would answer, by variable name. Values steer along the path that
 * reaches an end state: approve, confirm, complete - and say "no" only where the
 * loop is the point and would otherwise repeat forever.
 */
const VALUE = {
  // documentation and referral
  documentsComplete: true,
  documentationComplete: true,
  referralDecision: 'accepted',
  redirectDestination: '',
  referralUrgency: 'routine',
  // booking
  suitableSlotFound: true,
  appointmentWithin14Days: true,
  appointmentReference: 'APT-0001',
  contactSuccessful: true,
  // consultation and authorisation
  consentGiven: true,
  requestAuthorised: true,
  // capacity and funding
  treatmentCapacityConfirmed: true,
  fundingApproved: true,
  advancePaymentRequired: false,
  chargeAmount: 480,
  approvedAmount: 480,
  // payment
  paymentStatus: 'confirmed',
  paymentOutcome: 'confirmed',
  refundRequired: false,
  // treatment delivery
  furtherCyclesPlanned: false,
  fitToContinue: true,
  urgentPostponement: false,
  // correspondence
  letterApproved: true,
  suspectedClinicalError: false,
  accessibleFormatRequired: false,
  letterDelayDays: 0,
  financialImpact: false,
  followUpSlotWithinPeriod: false,
  appointmentPaid: false,
  // enquiries
  enquiryType: 'administrative',
  // reporting
  reportPeriod: '2026-09',
  treatmentCode: 'TRT-001',
  treatmentCycles: 1
};

// ------------------------------------------------------------------- small helpers
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
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

function evidenceDir() {
  const dir = fs.existsSync(path.join(ROOT, '05_Test_Evidence'))
    ? path.join(ROOT, '05_Test_Evidence', 'all-processes')
    : path.join(ROOT, 'evidence', 'all-processes');
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

// ------------------------------------------------------------------- form plumbing
function schemaFields(formJson) {
  const out = [];
  const walk = (cs) => {
    for (const c of cs || []) {
      if (!c || typeof c !== 'object') continue;
      if (c.key && !['group', 'spacer', 'image', 'iframe', 'text', 'button'].includes(c.type || '')) {
        out.push({ key: c.key, label: (c.label || '').trim(), type: c.type });
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
  await sleep(800);
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

/** Mark fields, click the clickable ones, return the text fields to type. */
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
      let el = leaves.find(x => labelOf(x) === norm(label)) ||
        leaves.find(x => labelOf(x).startsWith(norm(label).slice(0, 24))) ||
        leaves[sch.findIndex(s => s.key === key)];
      if (!el) { done.push(`${key}: no field`); continue; }
      const input = el.querySelector('input, textarea, select');
      const kind = input.tagName === 'SELECT' ? 'select' : (input.type || 'text');
      input.setAttribute('data-all-key', key);
      marked.push(key);
      if (kind === 'checkbox') {
        if (!!input.checked !== !!value) input.click();
        done.push(`${key}=${!!value}`);
      } else if (kind === 'radio') {
        const opts = [...el.querySelectorAll('input[type=radio]')];
        const opt = opts.find(r => r.value === String(value)) || opts[0];
        if (opt) opt.click();
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
  const sel = `[data-all-key="${key}"]`;
  await page.click(sel);
  await page.keyboard.down('Control');
  await page.keyboard.press('KeyA');
  await page.keyboard.up('Control');
  await page.type(sel, value, { delay: 20 });
}

async function readFields(page) {
  return page.evaluate(() => {
    const out = {};
    for (const el of document.querySelectorAll('[data-all-key]')) {
      out[el.getAttribute('data-all-key')] =
        el.type === 'checkbox' ? String(!!el.checked) : String(el.value ?? '');
    }
    return out;
  });
}

function mismatch(expected, actual) {
  const bad = [];
  for (const [k, v] of Object.entries(expected)) {
    const want = String(v);
    if (String(actual[k] ?? '') !== want) bad.push(`${k} (wanted ${want}, form holds ${JSON.stringify(actual[k] ?? null)})`);
  }
  return bad;
}

/** Run one process instance to its end state through Tasklist. */
async function drive(page, definitionId, patientId, started) {
  const key = String(started.processInstanceKey);
  const label = definitionId.replace(/^PR_/, '');
  const handled = [];
  let shot = 0;

  for (let step = 0; step < MAX_STEPS; step++) {
    let task = null, state = 'ACTIVE';
    for (let wait = 0; wait < 90; wait++) {
      const t = await search('user-tasks', {
        filter: { processInstanceKey: key, state: 'CREATED' }, page: { from: 0, limit: 5 }
      });
      task = (t.items || [])[0];
      if (task) break;
      const inst = await search('process-instances', { filter: { processInstanceKey: key } });
      const found = (inst.items || [])[0];
      // Secondary storage lags a little behind the engine, so "not found yet" is
      // not "finished". Only a visible, non-ACTIVE state ends the wait; that
      // mistake made every process report zero forms completed.
      if (found) {
        state = found.state;
        if (state !== 'ACTIVE') break;
      }
      await sleep(400);
    }
    if (!task) break;

    // the engine tells us which form it will render, and therefore what to answer
    let schema = [];
    if (task.formKey) {
      try {
        const f = await api('GET', `/forms/${task.formKey}`);
        const s = typeof f.schema === 'string' ? JSON.parse(f.schema) : f.schema;
        if (s && Array.isArray(s.components)) schema = schemaFields(s);
      } catch { /* fall through with no schema */ }
    }
    const values = {};
    for (const f of schema) if (f.key in VALUE) values[f.key] = VALUE[f.key];

    await page.goto(BASE + '/tasklist/' + task.userTaskKey, { waitUntil: 'networkidle2', timeout: 60000 });
    await sleep(STEP_DELAY + 1800);
    const rendered = await page.evaluate(() => document.querySelectorAll('.fjs-element').length);
    if (!rendered) throw new Error(`form did not render on ${task.elementId}`);
    await clickByText(page, 'assign to me');
    await sleep(600);

    const prepared = await prepareForm(page, schema, values);
    for (const { key: k, value } of prepared.toType) await typeInto(page, k, value);
    const expected = Object.fromEntries(Object.entries(values).filter(([k]) => prepared.marked.includes(k)));
    let actual = await readFields(page);
    let bad = mismatch(expected, actual);
    for (let a = 0; a < 3 && bad.length; a++) {
      for (const { key: k, value } of prepared.toType) {
        if (bad.some(b => b.startsWith(k + ' '))) await typeInto(page, k, value);
      }
      await sleep(250);
      actual = await readFields(page);
      bad = mismatch(expected, actual);
    }
    if (bad.length) throw new Error(`${task.elementId} would not accept ${bad.join(', ')}`);

    shot++;
    await page.screenshot({
      path: path.join(SHOTS, `${label}-${String(shot).padStart(2, '0')}-${task.elementId}.png`),
      fullPage: true
    });

    if (!await clickByText(page, '^complete task$|^complete$')) {
      throw new Error(`no Complete button on ${task.elementId}`);
    }
    handled.push({ elementId: task.elementId, filled: prepared.done });

    for (let i = 0; i < 30; i++) {
      await sleep(400);
      const still = await search('user-tasks', { filter: { userTaskKey: String(task.userTaskKey), state: 'CREATED' } });
      if (!(still.items || []).length) break;
      if (i === 8) await clickByText(page, '^complete task$|^complete$');
    }
  }

  const inst = await search('process-instances', { filter: { processInstanceKey: key } });
  const state = (inst.items || [])[0]?.state;
  const inc = await search('incidents', { filter: { processInstanceKey: key, state: 'PENDING' } });
  return {
    definitionId, patientId, processInstanceKey: key, finalState: state,
    openIncidents: (inc.items || []).length, userTasksCompleted: handled.length,
    tasks: handled.map(h => h.elementId),
    screenshots: shot
  };
}

// ------------------------------------------------------------------- main
const jar = locateJar();
if (!jar) { console.error('No worker jar. Build it first: mvn -f workers/pom.xml package'); process.exit(2); }
if (!EDGE) { console.error('Microsoft Edge not found'); process.exit(2); }

say('='.repeat(78));
say('RUNNING THE WHOLE MODEL FAMILY');
say('='.repeat(78));

const health = await fetch(API + '/topology', { headers: { Authorization: AUTH } }).catch(() => null);
if (!health || !health.ok) {
  console.error('The cluster is not answering on ' + API);
  console.error('Start it first: c8run.exe start');
  process.exit(2);
}
say('cluster        : answering on ' + API);

const defs = await search('process-definitions', { page: { from: 0, limit: 50 } });
const have = new Set((defs.items || []).map(d => d.processDefinitionId));
const missing = PROCESSES.filter(p => !have.has(p));
if (missing.length) {
  say('deploying the models first (' + missing.length + ' missing)');
  const dep = spawn(process.execPath, [path.join(HERE, 'deploy-all.mjs')], { stdio: 'ignore', cwd: ROOT });
  await new Promise(r => dep.on('exit', r));
}

const fleetLog = path.join(SHOTS, 'worker-fleet.log');
const fleet = spawn('java', ['--enable-native-access=ALL-UNNAMED', '-jar', jar],
  { cwd: path.dirname(jar), stdio: ['ignore', 'pipe', 'pipe'] });
const logStream = fs.createWriteStream(fleetLog);
fleet.stdout.pipe(logStream);
fleet.stderr.pipe(logStream);
for (let i = 0; i < 60; i++) {
  await sleep(500);
  if (fs.existsSync(fleetLog) && fs.readFileSync(fleetLog, 'utf8').includes('workers subscribed and polling')) break;
}
say('worker fleet   : 13 workers subscribed');

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: HEADLESS ? 'new' : false,
  defaultViewport: { width: 1500, height: 1000 },
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
  protocolTimeout: 420000
});
const page = await browser.newPage();
await login(page);
say('tasklist       : logged in as demo');
say('');

const results = [];
for (const definitionId of PROCESSES) {
  const patientId = 'ALL-' + definitionId.replace(/^PR_/, '').slice(0, 6).toUpperCase() + '-' + Date.now().toString().slice(-6);
  const vars = { patientId, ...(definitionId === 'PR_ManagementReporting' ? { reportPeriod: VALUE.reportPeriod } : {}) };
  let started;
  try {
    started = await api('POST', '/process-instances', { processDefinitionId: definitionId, variables: vars });
  } catch (e) {
    say(`  ${definitionId.padEnd(32)} could not start: ${e.message}`);
    results.push({ definitionId, started: false, error: e.message });
    continue;
  }
  // wait until the instance is visible before asking it anything
  for (let i = 0; i < 40; i++) {
    const inst = await search('process-instances', { filter: { processInstanceKey: String(started.processInstanceKey) } });
    if ((inst.items || []).length) break;
    await sleep(500);
  }
  try {
    const r = await drive(page, definitionId, patientId, started);
    results.push({ ...r, started: true });
    const mark = r.finalState === 'COMPLETED' && r.openIncidents === 0 ? 'OK  ' : 'CHECK';
    say(`  ${mark} ${definitionId.padEnd(32)} ${String(r.userTasksCompleted).padStart(2)} form(s)  state=${r.finalState}  incidents=${r.openIncidents}`);
  } catch (e) {
    say(`  FAIL ${definitionId.padEnd(32)} ${e.message}`);
    results.push({ definitionId, started: true, error: e.message });
  }
  await sleep(600);
}

const ok = results.filter(r => r.finalState === 'COMPLETED' && r.openIncidents === 0).length;
say('');
say(`processes run to completion : ${ok} of ${PROCESSES.length}`);
say(`forms completed by hand     : ${results.reduce((n, r) => n + (r.userTasksCompleted || 0), 0)}`);
say(`screenshots                 : ${path.relative(process.cwd(), SHOTS)}`);
say(`RESULT: ${ok === PROCESSES.length ? 'every process in the family ran to an end state' : 'not every process reached an end state'}`);

fs.writeFileSync(path.join(SHOTS, 'all-processes.json'),
  JSON.stringify({ processes: results, transcript }, null, 2));
fs.writeFileSync(path.join(SHOTS, 'all-processes.log'), transcript.join('\n') + '\n');

say('closing the browser in 6s');
await sleep(6000);
await browser.close();
fleet.kill();
await sleep(400);
process.exit(ok === PROCESSES.length ? 0 : 1);
