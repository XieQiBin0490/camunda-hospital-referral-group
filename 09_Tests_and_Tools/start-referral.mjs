/**
 * Start one referral so a person can work the forms by hand in Tasklist.
 *
 *   node tools/start-referral.mjs
 *
 * It publishes the start message, cancels the two strategic twin instances (all
 * three models declare the same start message, so one referral wakes three
 * processes), waits until the first task exists, and prints the patient id and
 * the Tasklist URL to open. From there every form is filled by hand.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = 'http://127.0.0.1:8080';
const API = BASE + '/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');
const PROCESS = 'PR_Operational_Merged';
const TWINS = ['PR_Landscape', 'PR_ReferralToAuthorisation'];

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

const patientId = process.argv[2] || 'HAND-' + Date.now();

const topo = await fetch(API + '/topology', { headers: { Authorization: AUTH } });
if (!topo.ok) {
  console.error('the cluster is not answering on ' + API + ' - start it with c8run.exe start');
  process.exit(2);
}

const defs = await search('process-definitions', { page: { from: 0, limit: 20 } });
if (!(defs.items || []).some(d => d.processDefinitionId === PROCESS)) {
  console.error('the models are not deployed. Run:  node 09_Tests_and_Tools/deploy-all.mjs');
  process.exit(2);
}

await api('POST', '/messages/publication', {
  name: 'Patient referral', correlationKey: patientId,
  variables: { patientId, documentsComplete: true }
});
console.log('referral started for patient %s', patientId);

await sleep(2500);
let instance = null;
for (let i = 0; i < 20 && !instance; i++) {
  const r = await search('process-instances', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 50 } });
  for (const inst of r.items || []) {
    if (inst.processDefinitionId !== PROCESS) continue;
    const vars = await search('variables', { filter: { processInstanceKey: String(inst.processInstanceKey) } });
    if ((vars.items || []).some(v => v.name === 'patientId' && String(v.value).includes(patientId))) {
      instance = inst;
      break;
    }
  }
  if (!instance) await sleep(500);
}
if (!instance) {
  console.error('no operational instance appeared');
  process.exit(1);
}

const actives = await search('process-instances', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 50 } });
let cancelled = 0;
for (const i of actives.items || []) {
  if (TWINS.includes(i.processDefinitionId)) {
    await api('POST', `/process-instances/${i.processInstanceKey}/cancellation`, {});
    cancelled++;
  }
}

const tasks = await search('user-tasks', {
  filter: { processInstanceKey: String(instance.processInstanceKey), state: 'CREATED' },
  page: { from: 0, limit: 5 }
});
const first = (tasks.items || [])[0];

console.log('');
console.log('  patient id      : %s', patientId);
console.log('  instance key    : %s', instance.processInstanceKey);
console.log('  strategic twins : %d cancelled (they share the start message)', cancelled);
console.log('  first task      : %s  %s', first?.name || '(none yet)', first?.userTaskKey || '');
console.log('');
console.log('  Open Tasklist and log in as demo / demo:');
console.log('    %s/tasklist', BASE);
if (first) {
  console.log('    %s/tasklist/%s', BASE, first.userTaskKey);
}
console.log('');
console.log('  The worker fleet must be running, or the flow will stop at the first');
console.log('  automated activity:  %s', 'workers\\run-workers.ps1');
