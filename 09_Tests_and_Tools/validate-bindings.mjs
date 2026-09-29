/**
 * Check that every form can actually feed the gateway that follows its task.
 *
 * A user task's form is generated from the variables the *next gateway* tests.
 * If the form ends up without one of those variables - because two models use
 * different names for the same concept, or because two tasks share one form - the
 * operator fills the form, the gateway reads a variable nobody set, FEEL returns
 * null, and the process takes its **default** branch. Nothing errors, nothing is
 * logged, and the wrong branch looks like a normal outcome. That is the defect
 * this check exists to catch.
 *
 * It also reports form ids used by tasks with different names, which is how the
 * mismatch above arises in the first place.
 *
 *   node tools/validate-bindings.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const formsDir = fs.existsSync(path.join(ROOT, 'output', 'forms'))
  ? path.join(ROOT, 'output', 'forms')
  : path.join(ROOT, '03_Forms');

const specs = (await import('../models/index.mjs')).specs;

function nextGateways(proc, taskId) {
  const out = [];
  const seen = new Set();
  const nodes = new Map(proc.nodes.map(n => [n.id, n]));
  const stack = proc.flows.filter(f => f.source === taskId).map(f => f.target);
  while (stack.length) {
    const id = stack.shift();
    if (seen.has(id)) continue;
    seen.add(id);
    const n = nodes.get(id);
    if (!n) continue;
    if (n.type.endsWith('Gateway')) { out.push(id); continue; }
    if (n.type === 'endEvent') continue;
    // A human boundary: if another user task comes first, that task's own form is
    // the one that supplies the decision, not this one.
    if (n.type === 'userTask') continue;
    for (const f of proc.flows.filter(x => x.source === id)) stack.push(f.target);
  }
  return out;
}

function varsOfGateway(proc, gatewayId) {
  const out = new Set();
  for (const f of proc.flows.filter(x => x.source === gatewayId)) {
    if (!f.condition) continue;
    for (const m of f.condition.matchAll(/([A-Za-z_][A-Za-z0-9_]*)\s*(=|!=|<=|>=|<|>)/g)) {
      if (['true', 'false', 'null'].includes(m[1])) continue;
      out.add(m[1]);
    }
  }
  return out;
}

function formFields(formId) {
  for (const name of [formId + '.form', formId]) {
    const p = path.join(formsDir, name);
    if (!fs.existsSync(p)) continue;
    const data = JSON.parse(fs.readFileSync(p, 'utf8'));
    const keys = new Set();
    const walk = (cs) => {
      for (const c of cs || []) {
        if (!c || typeof c !== 'object') continue;
        if (c.key) keys.add(c.key);
        walk(c.components);
      }
    };
    walk(data.components);
    return keys;
  }
  return null;
}

let problems = 0;
let tasks = 0;
let bindings = 0;
const byForm = new Map();

console.log('='.repeat(96));
console.log('FORM TO GATEWAY BINDINGS');
console.log('='.repeat(96));

for (const [modelName, spec] of Object.entries(specs)) {
  for (const pool of spec.pools) {
    const proc = pool.process;
    if (!proc) continue;
    for (const n of proc.nodes) {
      if (!n.formId) continue;
      tasks++;
      const gateways = nextGateways(proc, n.id);
      const wanted = new Set();
      for (const g of gateways) for (const v of varsOfGateway(proc, g)) wanted.add(v);
      if (!wanted.size) continue;
      bindings++;
      const keys = formFields(n.formId);
      if (!keys) {
        console.log(`  MISSING FORM  ${n.formId}  (task ${n.id})`);
        problems++;
        continue;
      }
      const unfeedable = [...wanted].filter(v => !keys.has(v));
      const entry = byForm.get(n.formId) || { names: new Set(), models: new Set() };
      entry.names.add(n.name);
      entry.models.add(modelName);
      byForm.set(n.formId, entry);
      if (unfeedable.length) {
        problems++;
        console.log(`  WRONG BRANCH RISK  ${modelName} / ${n.id}`);
        console.log(`      form ${n.formId} holds : ${[...keys].join(', ')}`);
        console.log(`      gateway needs       : ${[...wanted].join(', ')}`);
        console.log(`      nothing can set     : ${unfeedable.join(', ')}`);
      }
    }
  }
}

console.log('');
console.log('-- form ids used by more than one task name --');
let shared = 0;
for (const [formId, entry] of [...byForm].sort()) {
  if (entry.names.size > 1) {
    shared++;
    console.log(`  ${formId}`);
    for (const nm of entry.names) console.log(`      "${nm}"`);
    console.log(`      models: ${[...entry.models].join(', ')}`);
  }
}
if (!shared) console.log('  none');

console.log('');
console.log(`SUMMARY {"tasksWithForms":${tasks},"checkedBindings":${bindings},"problems":${problems},"sharedForms":${shared}}`);
console.log(`RESULT: ${problems === 0 ? 'every form can feed the gateway that follows its task' : problems + ' binding problem(s)'}`);
process.exit(problems === 0 ? 0 : 1);
