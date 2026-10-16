/**
 * Empty the cluster of test instances and incidents, so a demonstration starts clean.
 *
 *   node 09_Tests_and_Tools/reset-demo-state.mjs
 *
 * The verification and acceptance scripts start real process instances - that is how they
 * check anything - and each one leaves a task in Tasklist and, where a worker rejected a
 * job, an incident in Operate. Useful while testing, confusing in front of an audience.
 *
 * This cancels every running instance and resolves every incident. It touches nothing else:
 * the deployed process definitions and forms stay exactly as they are.
 */
const BASE = process.env.C8_BASE || 'http://127.0.0.1:8080';
const API = BASE + '/v2';
const AUTH = 'Basic ' + Buffer.from('demo:demo').toString('base64');

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
  const topo = await fetch(API + '/topology', { headers: { Authorization: AUTH } }).catch(() => null);
  if (!topo || !topo.ok) {
    console.error(`the cluster is not answering on ${API} - start it first`);
    process.exit(2);
  }

  // 1. Cancel every running instance, paging until none are left.
  let cancelled = 0;
  for (let round = 0; round < 40; round++) {
    const active = await search('process-instances', {
      filter: { state: 'ACTIVE' }, page: { from: 0, limit: 200 }
    });
    const items = active.json?.items || [];
    if (!items.length) break;
    for (const inst of items) {
      const r = await api('POST', `/process-instances/${inst.processInstanceKey}/cancellation`, {});
      if (r.ok || r.status === 204) cancelled++;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  console.log(`  cancelled ${cancelled} running instance(s)`);

  // 2. Resolve the incidents that are still open. The rest are already RESOLVED - the
  //    engine refuses to resolve one twice, and counting them as failures would be noise.
  let resolved = 0;
  for (let round = 0; round < 40; round++) {
    const inc = await search('incidents', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 200 } });
    const items = inc.json?.items || [];
    if (!items.length) break;
    for (const i of items) {
      const r = await api('POST', `/incidents/${i.incidentKey}/resolution`, {});
      if (r.ok || r.status === 204) resolved++;
    }
    await new Promise(r => setTimeout(r, 300));
  }
  console.log(`  resolved ${resolved} open incident(s)`);

  // 3. Report what is left.
  const left = await search('process-instances', { filter: { state: 'ACTIVE' }, page: { from: 0, limit: 1 } });
  const incLeft = await search('incidents', { page: { from: 0, limit: 1 } });
  const tasks = await search('user-tasks', { filter: { state: 'CREATED' }, page: { from: 0, limit: 1 } });
  console.log('');
  console.log(`  running instances now : ${left.json?.page?.totalItems ?? '?'}`);
  console.log(`  incidents now         : ${incLeft.json?.page?.totalItems ?? '?'}`);
  console.log(`  open tasks now        : ${tasks.json?.page?.totalItems ?? '?'}`);

  // 4. Confirm the deployment is untouched.
  const defs = await search('process-definitions', { page: { from: 0, limit: 200 } });
  const byId = {};
  for (const d of defs.json?.items || []) {
    byId[d.processDefinitionId] = Math.max(byId[d.processDefinitionId] || 0, d.version);
  }
  console.log('');
  console.log('  deployed definitions are untouched:');
  for (const [id, v] of Object.entries(byId).sort()) console.log(`    ${id} v${v}`);
}

main().catch(e => { console.error('  unexpected failure:', e.message); process.exit(1); });
