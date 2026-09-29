// Validate .bpmn files using the SAME moddle stack that ships inside Camunda Modeler 5.51.0.
// Reports: moddle warnings/errors (unknown elements/attrs), and a set of structural checks
// equivalent to the Camunda Modeler "Problems" panel + BPMN execution semantics.
const fs = require('fs');
const path = require('path');

const BpmnModdle = require('../vendor/node_modules/bpmn-moddle/dist/index.cjs');
const zeebeModdle = require('../vendor/node_modules/zeebe-bpmn-moddle/resources/zeebe.json');

async function main() {
  const moddle = new (BpmnModdle.default || BpmnModdle)({ zeebe: zeebeModdle });
  for (const file of process.argv.slice(2)) {
    const xml = fs.readFileSync(file, 'utf8');
    const report = { file: path.basename(file), warnings: [], errors: [], structural: [] };
    let root;
    try {
      const res = await moddle.fromXML(xml);
      root = res.rootElement;
      report.warnings = res.warnings.map(w => String(w.message || w));
    } catch (e) {
      report.errors.push(String(e.message || e));
      print(report);
      continue;
    }

    const all = root.rootElements || [];
    const procs = all.filter(e => e.$type === 'bpmn:Process');
    const collabs = all.filter(e => e.$type === 'bpmn:Collaboration');

    // ---- structural checks ----
    const S = report.structural;
    const ids = new Map();
    const dupIds = [];
    (function walk(el) {
      if (el.id) {
        if (ids.has(el.id)) dupIds.push(el.id);
        ids.set(el.id, el);
      }
      for (const k of Object.keys(el.$model.getType(el.$type).properties)) {
        const v = el.get(k);
        if (Array.isArray(v)) v.forEach(c => c && c.$type && walk(c));
        else if (v && v.$type) walk(v);
      }
    })(root);
    if (dupIds.length) S.push('DUPLICATE IDs: ' + [...new Set(dupIds)].join(', '));

    const platforms = new Set();
    const xmlns = (xml.match(/modeler:executionPlatform="([^"]+)"/) || [])[1];
    if (xmlns) platforms.add(xmlns + ' ' + ((xml.match(/modeler:executionPlatformVersion="([^"]+)"/) || [])[1] || '?'));
    // detect Camunda 7 constructs
    const c7 = [...xml.matchAll(/\bcamunda:(\w+)=/g)].map(m => m[1]);
    const c8zeebe = [...xml.matchAll(/\bzeebe:(\w+)/g)].map(m => m[1]);

    for (const p of procs) {
      const nodes = [];
      (function walk(el) {
        if (el.$type && el.$type.startsWith('bpmn:') && el.$instanceOf && el.$instanceOf('bpmn:FlowNode')) nodes.push(el);
        for (const k of Object.keys(el.$model.getType(el.$type).properties)) {
          const v = el.get(k);
          if (Array.isArray(v)) v.forEach(c => c && c.$type && walk(c));
          else if (v && v.$type) walk(v);
        }
      })(p);
      const starts = nodes.filter(n => n.$type === 'bpmn:StartEvent');
      const ends = nodes.filter(n => n.$type === 'bpmn:EndEvent');
      if (nodes.length === 0) { S.push(`[${p.id}] process is EMPTY (no flow nodes) - renders as a blank black-box pool`); continue; }
      if (starts.length === 0) S.push(`[${p.id}] no start event`);
      if (ends.length === 0) S.push(`[${p.id}] no end event`);
      for (const n of nodes) {
        const inb = (n.incoming || []).length, out = (n.outgoing || []).length;
        const isStart = n.$type === 'bpmn:StartEvent';
        const isEnd = n.$type === 'bpmn:EndEvent';
        const isBoundary = n.$type === 'bpmn:BoundaryEvent';
        const isAttached = n.$type === 'bpmn:BoundaryEvent';
        if (!isStart && !isAttached && inb === 0) S.push(`[${p.id}] DANGLING (no incoming): ${n.id} "${n.name || ''}"`);
        if (!isEnd && !isBoundary && out === 0) S.push(`[${p.id}] DEAD END (no outgoing): ${n.id} "${n.name || ''}"`);
        if (n.$type === 'bpmn:ExclusiveGateway' || n.$type === 'bpmn:InclusiveGateway') {
          const flows = n.outgoing || [];
          const hasDefault = !!n.default;
          const conditional = flows.filter(f => f.conditionExpression).length;
          if (flows.length > 1 && !hasDefault && conditional < flows.length) {
            S.push(`[${p.id}] GATEWAY NO-DEFAULT: ${n.id} "${n.name || ''}" has ${flows.length} outgoing, ${conditional} conditional, no default flow -> runtime "no outgoing sequence flow could be selected"`);
          }
        }
        if (n.$instanceOf && n.$instanceOf('bpmn:UserTask')) {
          const ext = n.extensionElements;
          const ad = ext && (ext.values || []).find(v => v.$type === 'zeebe:AssignmentDefinition');
          if (ad && ad.assignee && /team|group|role/i.test(ad.assignee)) S.push(`[${p.id}] ${n.id}: assignee="${ad.assignee}" looks like a GROUP/role - should be zeebe:candidateGroups`);
        }
      }
    }

    for (const c of collabs) {
      for (const part of c.participants || []) {
        if (!part.processRef) S.push(`[${c.id}] black-box participant "${part.name}" (no processRef) - ok only if intentional collapse`);
      }
      for (const mf of (c.messageFlows || [])) {
        if (!mf.sourceRef || !mf.targetRef) S.push(`[${c.id}] message flow ${mf.id} missing source/target`);
      }
    }

    // unused lanes
    for (const p of procs) {
      const ls = p.laneSets && p.laneSets[0];
      if (ls) for (const lane of ls.lanes) {
        if (!lane.flowNodeRef || lane.flowNodeRef.length === 0) S.push(`[${p.id}] EMPTY LANE: "${lane.name}" (${lane.id})`);
      }
    }

    report.platform = [...platforms].join(', ') || '(none declared)';
    report.camunda7Attrs = [...new Set(c7)];
    report.zeebeRefs = [...new Set(c8zeebe)];
    report.processes = procs.map(p => ({ id: p.id, name: p.name, executable: p.isExecutable, nodes: countNodes(p) }));
    report.participants = collabs.flatMap(c => (c.participants || []).map(p => ({ id: p.id, name: p.name, ref: p.processRef && p.processRef.id })));
    print(report);
  }
}

function countNodes(p) {
  let n = 0;
  (function walk(el) {
    if (el.$type && el.$instanceOf && el.$instanceOf('bpmn:FlowNode')) n++;
    for (const k of Object.keys(el.$model.getType(el.$type).properties)) {
      const v = el.get(k);
      if (Array.isArray(v)) v.forEach(c => c && c.$type && walk(c));
      else if (v && v.$type) walk(v);
    }
  })(p);
  return n;
}

function print(r) {
  console.log('='.repeat(88));
  console.log('FILE:', r.file);
  console.log('='.repeat(88));
  if (r.platform) console.log('  executionPlatform :', r.platform);
  if (r.camunda7Attrs && r.camunda7Attrs.length) console.log('  camunda:7 attrs   :', r.camunda7Attrs.join(', '));
  if (r.zeebeRefs) console.log('  zeebe (C8) attrs  :', r.zeebeRefs.join(', '));
  if (r.processes) for (const p of r.processes) console.log(`  process ${p.id} "${p.name || ''}" executable=${p.executable} nodes=${p.nodes}`);
  if (r.participants) for (const p of r.participants) console.log(`  participant ${p.id} "${p.name}" -> ${p.ref || 'BLACK BOX'}`);
  if (r.errors.length) { console.log('\n  -- PARSE ERRORS --'); r.errors.forEach(e => console.log('   *', e)); }
  if (r.warnings.length) { console.log('\n  -- MODDLE WARNINGS --'); r.warnings.forEach(w => console.log('   *', w)); }
  if (r.structural && r.structural.length) { console.log('\n  -- STRUCTURAL --'); r.structural.forEach(w => console.log('   *', w)); }
  console.log('');
}

main().catch(e => { console.error(e); process.exit(1); });
