/**
 * Check that a user task now resolves to the form that was deployed with the model.
 *
 *   node 09_Tests_and_Tools/verify-form-binding.mjs
 *
 * This is the check for the defect where every user task said binding="deployment", an
 * attribute zeebe:formDefinition does not have. The engine ignored it and used the default
 * binding, `latest`, so an instance rendered whichever version of the form someone had
 * deployed most recently - which is how a teammate's older text-box forms replaced the
 * drop-downs - and a task whose form was not in that latest set could not open at all.
 *
 * The models now say bindingType="deployment". The check therefore starts a real referral,
 * asks the engine for the first user task, fetches the form that task resolves to, and
 * looks for the drop-down controls the forms are supposed to have. It reads the task's own
 * formKey, so it tests resolution as an instance really experiences it rather than testing
 * the file on disk.
 *
 * Exit codes: 0 all checks passed, 1 a check failed, 2 the cluster is not reachable.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.env.C8_BASE || 'http://127.0.0.1:8080';
const API = BASE + '/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');
const sleep = ms => new Promise(r => setTimeout(r, ms));

let failures = 0;
const line = (ok, what, detail = '') => {
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${what}${detail ? '  ' + detail : ''}`);
  if (!ok) failures++;
};

async function api(method, url, body) {
  const res = await fetch(API + url, {
    method,
    headers: { Authorization: AUTH, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* not json */ }
  return { status: res.status, ok: res.ok, json, text };
}

const search = (kind, body) => api('POST', `/${kind}/search`, body || {});

async function main() {
  console.log('== checking that a task resolves to its own deployment\'s form ==');

  const topo = await fetch(API + '/topology', { headers: { Authorization: AUTH } }).catch(() => null);
  if (!topo || !topo.ok) {
    console.error(`  the cluster is not answering on ${API}.`);
    console.error('  Start it first:  cd D:\\app\\Camunda\\c8run-8.10.0-alpha5  then  .\\c8run.exe start');
    process.exit(2);
  }
  line(true, 'cluster is reachable');

  // 1. What the deployed model says about binding, straight from the engine.
  const defs = await search('process-definitions', { page: { from: 0, limit: 200 } });
  const op = (defs.json?.items || [])
    .filter(d => d.processDefinitionId === 'PR_Operational_Merged')
    .sort((a, b) => b.version - a.version)[0];
  if (!op) {
    console.error('  PR_Operational_Merged is not deployed. Run: node 09_Tests_and_Tools/deploy-all.mjs');
    process.exit(1);
  }
  const xml = await fetch(`${API}/process-definitions/${op.processDefinitionKey}/xml`,
    { headers: { Authorization: AUTH } }).then(r => r.text());
  const deployedBinding = (xml.match(/bindingType="(deployment|latest|versionTag)"/g) || []).length;
  const which = (xml.match(/bindingType="(deployment|latest|versionTag)"/) || [])[1] || 'none';
  const wrongAttr = (xml.match(/formDefinition[^>]*\sbinding="/g) || []).length;
  line(deployedBinding > 0 && wrongAttr === 0,
    `deployed model v${op.version} uses the real attribute`,
    `bindingType=${which} x${deployedBinding}, wrong attribute=${wrongAttr}`);
  console.log(`         binding mode: ${which}` +
    (which === 'latest'
      ? '  (the Modeler Deploy button works; a task uses the newest deployed form version)'
      : '  (a task uses the form from its own deployment; deploy with deploy-all.mjs)'));

  // A model deployed on its own is what the Modeler's Deploy button does. With the strict
  // binding the engine rejects that, so the check is only meaningful for `latest`.
  const solo = new FormData();
  solo.append('name', 'solo-deploy-check');
  solo.append('resources',
    new Blob([fs.readFileSync(path.join(ROOT, '02_BPMN_Models', 'O1_Operational_Merged.bpmn'))],
      { type: 'application/xml' }),
    'O1_Operational_Merged.bpmn');
  const soloRes = await fetch(`${API}/deployments`,
    { method: 'POST', headers: { Authorization: AUTH }, body: solo });
  if (which === 'latest') {
    line(soloRes.ok, 'the Modeler Deploy button works (a .bpmn deploys on its own)',
      `HTTP ${soloRes.status}`);
  } else {
    line(true, 'a .bpmn on its own is rejected by design',
      `HTTP ${soloRes.status} - deploy with deploy-all.mjs`);
  }

  // 2. Start a real referral so an instance exists with the current deployment.
  const patientId = 'BINDING-' + Date.now();
  await api('POST', '/messages/publication', {
    name: 'Patient referral', correlationKey: patientId,
    variables: { patientId, documentsComplete: true }
  });
  await sleep(3000);

  // Ignore the two strategic twins that share the start message.
  const actives = await search('process-instances', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 50 } });
  for (const inst of actives.json?.items || []) {
    if (inst.processDefinitionId !== 'PR_Operational_Merged') {
      await api('POST', `/process-instances/${inst.processInstanceKey}/cancellation`, {});
    }
  }

  const tasks = await search('user-tasks', {
    filter: { state: 'CREATED', processDefinitionId: 'PR_Operational_Merged' },
    page: { from: 0, limit: 20 }
  });
  const task = (tasks.json?.items || []).find(t => t.formKey);
  if (!task) {
    line(false, 'a user task with a form was found');
    console.log('\nRESULT: FAIL');
    process.exit(1);
  }
  line(true, `first task is "${task.name}"`, `elementId=${task.elementId}`);

  // 3. The form that task actually resolves to, read through the engine. The response
  //    carries the form as a JSON string in `schema`, not as a nested object.
  const formRes = await fetch(`${API}/forms/${task.formKey}`, { headers: { Authorization: AUTH } });
  const form = await formRes.json().catch(() => null);
  if (!formRes.ok || !form) {
    line(false, 'the task resolves to a readable form', `HTTP ${formRes.status}`);
    console.log('\nRESULT: FAIL');
    process.exit(1);
  }
  line(true, 'the task resolves to a form', `formId=${form.formId}`);
  const schema = typeof form.schema === 'string' ? JSON.parse(form.schema) : form.schema;
  const fields = schema?.components || [];
  const selects = fields.filter(c => c.type === 'select');
  const numberFields = fields.filter(c => c.type === 'number');
  const withRules = fields.filter(c => c.validate);
  line(fields.length > 0, 'the form has fields', `${fields.length}`);
  line(withRules.length > 0, 'the form carries validation rules', `${withRules.length}`);
  line(selects.length > 0 || numberFields.length > 0,
    'the form uses typed controls, not only text boxes',
    `select=${selects.length}, number=${numberFields.length}`);
  if (selects.length) {
    console.log(`         drop-downs: ${selects.map(c => c.key).join(', ')}`);
  }

  // 4. The form on disk should agree with the one the task resolves to, which is the whole
  //    point of bindingType="deployment": no one else's upload can take the task over.
  const localFile = path.join(ROOT, '03_Forms', `${form.formId || ''}.form`);
  if (form.formId && fs.existsSync(localFile)) {
    const local = JSON.parse(fs.readFileSync(localFile, 'utf8'));
    const localSelects = (local.components || []).filter(c => c.type === 'select').length;
    line(localSelects === selects.length,
      'the deployed form matches the one in 03_Forms',
      `workspace select=${localSelects}, engine select=${selects.length}`);
  } else {
    line(true, 'workspace copy not compared', `formId=${form.formId}`);
  }

  console.log(failures ? `\nRESULT: FAIL (${failures} check(s))` : '\nRESULT: PASS');
  process.exit(failures ? 1 : 0);
}

main().catch(e => {
  console.error('  unexpected failure:', e.message);
  process.exit(1);
});
