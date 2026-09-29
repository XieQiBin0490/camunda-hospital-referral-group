import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Check every repository path quoted in the Markdown documents of this
 * repository against the files that actually exist.
 *
 *   node 09_Tests_and_Tools/check-refs.mjs
 *
 * It resolves the repository root from its own location, so it runs from a
 * clone without editing. A quoted path that does not resolve is printed under
 * "unresolved" - which is the whole point: a document that points at a file the
 * marker cannot open is worse than a document that says nothing.
 *
 * Quoted paths that describe the *team workspace* rather than this repository
 * (output/, work/, workers/) are reported separately as "workspace-only" so
 * they do not mask a real breakage.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

const WORKSPACE_PREFIXES = ['output/', 'work/', 'workers/', 'content/', 'node_modules/'];

const SKIP_DIRS = new Set(['.git', 'node_modules', 'target', '.idea']);

function markdownFiles(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      markdownFiles(full, out);
    } else if (entry.name.endsWith('.md')) {
      out.push(full);
    }
  }
  return out;
}

const PATTERN = /(?:^|[\s`(])((?:[0-9]{2}_[A-Za-z_]+|docs|evidence|exports|istar|models|source|output|tools|workers)\/[A-Za-z0-9_./-]+)/g;

const refs = new Map(); // path -> Set of files that quote it
for (const file of markdownFiles(ROOT)) {
  const text = fs.readFileSync(file, 'utf8');
  for (const m of text.matchAll(PATTERN)) {
    const ref = m[1].replace(/[.,;:)]+$/, '');
    if (!refs.has(ref)) refs.set(ref, new Set());
    refs.get(ref).add(path.relative(ROOT, file).replace(/\\/g, '/'));
  }
}

const present = [];
const workspaceOnly = [];
const missing = [];

for (const ref of [...refs.keys()].sort()) {
  if (WORKSPACE_PREFIXES.some((p) => ref.startsWith(p))) {
    workspaceOnly.push(ref);
    continue;
  }
  const bare = ref.replace(/\/$/, '');
  const ok =
    fs.existsSync(path.join(ROOT, ref)) ||
    fs.existsSync(path.join(ROOT, bare)) ||
    fs.existsSync(path.join(ROOT, bare + '.md')) ||
    fs.existsSync(path.join(ROOT, bare + '.json')) ||
    fs.existsSync(path.join(ROOT, bare + '.bpmn')) ||
    fs.existsSync(path.join(ROOT, bare + '.form'));
  (ok ? present : missing).push([ref, [...refs.get(ref)].join(', ')]);
}

console.log('repository references quoted in Markdown : ' + refs.size);
console.log('resolved                                 : ' + present.length);
console.log('workspace-only (not expected to exist)   : ' + workspaceOnly.length);
for (const r of workspaceOnly) console.log('   ~    ' + r);
console.log('unresolved                               : ' + missing.length);
for (const [r, where] of missing) console.log('   ??   ' + r + '   (quoted in ' + where + ')');

process.exit(missing.length === 0 ? 0 : 1);
