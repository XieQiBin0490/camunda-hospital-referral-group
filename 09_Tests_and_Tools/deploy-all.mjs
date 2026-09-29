/** Deploy every form and model to the running Camunda 8 cluster. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const B = process.env.C8_BASE || 'http://127.0.0.1:8080/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');

/**
 * Locate the models and forms in either layout: the team workspace
 * (output/bpmn + output/forms) or the delivered package (02_BPMN_Models +
 * 03_Forms). The first candidate that exists wins.
 */
function locate() {
  const candidates = [
    { bpmn: path.join(ROOT, 'output', 'bpmn'), forms: path.join(ROOT, 'output', 'forms') },
    { bpmn: path.join(ROOT, '02_BPMN_Models'), forms: path.join(ROOT, '03_Forms') }
  ];
  for (const c of candidates) {
    if (fs.existsSync(c.bpmn) && fs.existsSync(c.forms)) {
      return c;
    }
  }
  throw new Error('cannot find the models and forms: looked in '
    + candidates.map(c => c.bpmn).join(' and '));
}

async function deploy(files, name) {
  const fd = new FormData();
  fd.append('name', name);
  for (const f of files) {
    const isForm = f.endsWith('.form');
    fd.append('resources', new Blob([fs.readFileSync(f)], { type: isForm ? 'application/json' : 'application/xml' }), path.basename(f));
  }
  const res = await fetch(B + '/deployments', { method: 'POST', headers: { Authorization: AUTH, Accept: 'application/json' }, body: fd });
  const text = await res.text();
  return { status: res.status, ok: res.ok, text };
}

const dirs = locate();
const formDir = dirs.forms;
const bpmnDir = dirs.bpmn;
const forms = fs.readdirSync(formDir).filter(f => f.endsWith('.form')).map(f => path.join(formDir, f));
const models = fs.readdirSync(bpmnDir).filter(f => f.endsWith('.bpmn')).map(f => path.join(bpmnDir, f));

console.log(`deploying ${forms.length} forms and ${models.length} models ...`);

/**
 * Each model is deployed **together with the forms it references**, in one
 * deployment.
 *
 * The form references carry binding="deployment", which means the engine resolves
 * a task's form from the same deployment as the process. That is what keeps a
 * process from running against a newer form than the one it was tested with - but
 * it also means a model deployed on its own fails with "Expected to find form with
 * id X in current deployment, but not found" for every task. So the forms travel
 * with the model, and the whole set of 68 is still covered because the models
 * between them reference all of them.
 */
const formByName = new Map(forms.map(f => [path.basename(f, '.form'), f]));
let allOk = true;
for (const model of models) {
  const xml = fs.readFileSync(model, 'utf8');
  const ids = [...xml.matchAll(/<zeebe:formDefinition[^>]*formId="([^"]+)"/g)].map(m => m[1]);
  const unique = [...new Set(ids)];
  const want = unique.map(id => formByName.get(id)).filter(Boolean);
  const absent = unique.filter(id => !formByName.has(id));
  const r = await deploy([model, ...want], 'ufcep4-0-3-' + path.basename(model, '.bpmn'));
  console.log(`  ${path.basename(model).padEnd(44)} ${want.length}/${unique.length} form(s)  HTTP ${r.status} ${r.ok ? 'OK' : ''}`);
  if (!r.ok) {
    allOk = false;
    console.log('    ' + r.text.slice(0, 700));
  }
  if (absent.length) {
    allOk = false;
    console.log('    references a form that does not exist locally: ' + absent.join(', '));
  }
}
if (!allOk) process.exit(1);

const res = await fetch(B + '/process-definitions/search', {
  method: 'POST', headers: { Authorization: AUTH, 'Content-Type': 'application/json' },
  // ask for plenty: every deployment adds a version, so a small page fills up with
  // old versions of the same six definitions and hides some of them from the list
  body: JSON.stringify({ page: { from: 0, limit: 500 } })
});
const j = await res.json();
const seen = new Set();
for (const d of j.items || []) {
  if (seen.has(d.processDefinitionId)) continue;
  seen.add(d.processDefinitionId);
  console.log(`  ${String(d.processDefinitionId).padEnd(34)} v${d.version}  ${d.name || ''}`);
}
const fres = await fetch(B + '/decision-definitions/search', {
  method: 'POST', headers: { Authorization: AUTH, 'Content-Type': 'application/json' },
  body: JSON.stringify({ page: { from: 0, limit: 5 } })
});
console.log('(forms are linked to user tasks by form id; form deployments are not listed by the process-definition endpoint)');
