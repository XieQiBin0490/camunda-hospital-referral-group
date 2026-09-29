/**
 * Render every Camunda Form with form-js, the renderer Tasklist uses.
 *
 * A form can be valid JSON, pass the engine's deployment validation, and still
 * fail to render - a component the renderer does not know, a field type mismatch,
 * a malformed nested group. Deployment cannot tell you that; only the renderer
 * can. The other team's package ran this check and ours did not, which is why it
 * exists.
 *
 * The form is rendered in a real browser (Edge via puppeteer-core, because
 * headless Chrome does not start reliably on this machine), not in a simulated
 * DOM, so the result is the renderer's own verdict.
 *
 *   node 09_Tests_and_Tools/render-forms.mjs                 # workspace: output/forms
 *   node 09_Tests_and_Tools/render-forms.mjs 03_Forms
 *
 * Writes evidence/worker-run/form-render.txt (or 05_Test_Evidence/... in
 * the delivered package) and exits non-zero if any form fails to render.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

function locateForms() {
  const arg = process.argv[2];
  const candidates = arg
    ? [path.resolve(arg)]
    : [path.join(ROOT, 'output', 'forms'), path.join(ROOT, '03_Forms')];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  throw new Error('no forms directory found; looked in ' + candidates.join(', '));
}

function locateFormJs() {
  const candidates = [
    path.join(ROOT, 'work', 'node_modules', '@bpmn-io', 'form-js', 'dist'),
    path.join(ROOT, 'node_modules', '@bpmn-io', 'form-js', 'dist'),
    path.join(ROOT, '..', 'work', 'node_modules', '@bpmn-io', 'form-js', 'dist')
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, 'form-viewer.umd.js'))) return c;
  }
  return null;
}

function evidencePath(file) {
  const dir = fs.existsSync(path.join(ROOT, '05_Test_Evidence'))
    ? path.join(ROOT, '05_Test_Evidence', 'worker-run')
    : path.join(ROOT, 'evidence', 'worker-run');
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, file);
}

const EDGE = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe'
].find(p => fs.existsSync(p));

const formsDir = locateForms();
const dist = locateFormJs();
if (!dist) {
  console.error('form-js is not installed. Run: cd work && npm install @bpmn-io/form-js');
  process.exit(2);
}
if (!EDGE) {
  console.error('Microsoft Edge not found; this check needs a real browser engine.');
  process.exit(2);
}

const files = fs.readdirSync(formsDir).filter(f => f.endsWith('.form')).sort();
console.log('rendering %d form(s) from %s', files.length, path.relative(ROOT, formsDir));
console.log('renderer: form-js (%s)', path.relative(ROOT, dist));

const lines = [];
const say = (s) => { console.log(s); lines.push(s); };

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: 'new',
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--allow-file-access-from-files'],
  protocolTimeout: 120000
});

let failed = 0;
const failures = [];
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });

  const viewerJs = fs.readFileSync(path.join(dist, 'form-viewer.umd.js'), 'utf8');
  const viewerCss = fs.readFileSync(path.join(dist, 'assets', 'form-js.css'), 'utf8');

  await page.setContent(
    '<!doctype html><html><head><meta charset="utf-8"><style>' + viewerCss + '</style></head>'
    + '<body><div id="host" style="width:1100px"></div>'
    + '<script>' + viewerJs + '</script></body></html>',
    { waitUntil: 'load' });

  const hasViewer = await page.evaluate(() => typeof window.FormViewer !== 'undefined');
  if (!hasViewer) {
    throw new Error('form-js viewer bundle did not expose window.FormViewer');
  }
  // the UMD bundle exposes the module namespace; the viewer class is .Form
  const hasForm = await page.evaluate(() => typeof window.FormViewer.Form === 'function');
  if (!hasForm) {
    throw new Error('window.FormViewer.Form is not a constructor in this bundle');
  }

  for (const file of files) {
    const schema = JSON.parse(fs.readFileSync(path.join(formsDir, file), 'utf8'));
    const result = await page.evaluate(async (s) => {
      const host = document.getElementById('host');
      host.innerHTML = '';
      try {
        const form = new window.FormViewer.Form({ container: host });
        await form.importSchema(s);
        const elements = host.querySelectorAll('.fjs-element').length;
        const inputs = host.querySelectorAll('input, select, textarea').length;
        const groups = host.querySelectorAll('.fjs-form-field-group, .fjs-form-field-dynamiclist').length;
        return { ok: true, elements, inputs, groups };
      } catch (e) {
        return { ok: false, error: String((e && e.message) || e) };
      }
    }, schema);

    const label = file.padEnd(52);
    if (result.ok && result.elements > 0) {
      say(`  PASS  ${label} ${result.elements} element(s), ${result.inputs} input(s)`);
    } else if (result.ok) {
      failed++;
      failures.push(`${file}: rendered nothing`);
      say(`  FAIL  ${label} rendered nothing`);
    } else {
      failed++;
      failures.push(`${file}: ${result.error}`);
      say(`  FAIL  ${label} ${result.error}`);
    }
  }
} catch (e) {
  failed++;
  failures.push('harness: ' + e.message);
  say('  FAIL  harness: ' + e.message);
} finally {
  await browser.close();
}

say('');
say(`TOTAL=${files.length} FAILED=${failed}`);
say(new Date().toISOString());
fs.writeFileSync(evidencePath('form-render.txt'), lines.join('\n') + '\n');
console.log('\nevidence: %s', path.relative(process.cwd(), evidencePath('form-render.txt')));
process.exit(failed === 0 ? 0 : 1);
