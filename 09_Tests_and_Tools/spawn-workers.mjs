/**
 * Start the worker fleet detached, so the process outlives the shell that launched it.
 *
 *   node 09_Tests_and_Tools/spawn-workers.mjs [--wait SECONDS]
 *
 * Why not Start-Process or Start-Job: in a confined environment neither reliably produces
 * a running child, and a shell background job keeps the fleet tied to the shell's process
 * tree so it dies with the shell. A detached spawn with stdio ignored works, and its pid is
 * written to 05_Test_Evidence/worker-fleet.pid so a later script can stop it.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const JAR = path.join(ROOT, '04_Java_Worker', 'target', 'hospital-external-workers-1.0.0.jar');
const EVID = path.join(ROOT, '05_Test_Evidence');
const LOG = path.join(EVID, 'acceptance-workers.log');

if (!fs.existsSync(JAR)) {
  console.error('build the workers first: mvn -o -f 04_Java_Worker/pom.xml package');
  process.exit(2);
}
fs.mkdirSync(EVID, { recursive: true });

const java = process.env.JAVA_BIN || 'java';
// stdout is not piped - a piped stdio cannot be opened in a confined environment - so the
// fleet's output goes to a file the caller can read.
const out = fs.openSync(LOG, 'a');
const child = spawn(java, ['-jar', JAR], {
  cwd: ROOT,
  detached: true,
  stdio: ['ignore', out, out],
  env: { ...process.env, HPAS_GATEWAY_USERNAME: 'demo', HPAS_GATEWAY_PASSWORD: 'demo' }
});
child.unref();

fs.writeFileSync(path.join(EVID, 'worker-fleet.pid'), String(child.pid));
console.log(`worker fleet started, pid ${child.pid}, log ${path.relative(ROOT, LOG)}`);

const wait = Number(process.argv[process.argv.indexOf('--wait') + 1]) || 0;
if (wait > 0) {
  const started = Date.now();
  let subscribed = false;
  while (Date.now() - started < wait * 1000 && !subscribed) {
    await new Promise(r => setTimeout(r, 2000));
    const text = fs.existsSync(LOG) ? fs.readFileSync(LOG, 'utf8') : '';
    subscribed = text.includes('subscribed and polling');
  }
  console.log(subscribed
    ? 'the fleet reports its workers subscribed'
    : `the fleet did not report subscribing within ${wait}s; check ${path.relative(ROOT, LOG)}`);
  if (!subscribed) process.exit(1);
}
