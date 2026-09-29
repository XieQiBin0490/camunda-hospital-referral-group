#!/usr/bin/env python3
"""Validate the Camunda Forms and their wiring to the models, with no dependencies.

The engine validates a form when it is deployed, so a malformed form is caught at
deployment. Two things it cannot catch are checked here, and both have bitten this
build before:

  * a user task whose ``zeebe:formDefinition formId`` does not match any deployed
    form. Deployment succeeds and the task raises ``FORM_NOT_FOUND`` the first time
    an instance reaches it - which is exactly the DEP-04 defect in the defect log.
  * a form file that no model references, i.e. dead weight that also inflates the
    form count the portfolio claims.

Plus a light structural pass over each form: valid JSON, a schema version, a
non-empty id, at least one component, a label on every input and a unique key on
every input.

usage: python validate-forms.py [--bpmn-dir DIR] [--forms-dir DIR]
       (with no arguments it finds output/bpmn + output/forms, or the delivered
        02_BPMN_Models + 03_Forms)
"""
import glob
import json
import os
import re
import sys

BPMN = '{http://www.omg.org/spec/BPMN/20100524/MODEL}'
ZEEBE = '{http://camunda.org/schema/zeebe/1.0}'

INPUT_TYPES = {
    'textfield', 'textarea', 'number', 'checkbox', 'radio', 'select', 'taglist',
    'datetime', 'button', 'image', 'table', 'group', 'dynamiclist', 'iframe', 'spacer'
}


def locate(root):
    candidates = [
        (os.path.join(root, 'output', 'bpmn'), os.path.join(root, 'output', 'forms')),
        (os.path.join(root, '02_BPMN_Models'), os.path.join(root, '03_Forms')),
    ]
    for bpmn, forms in candidates:
        if os.path.isdir(bpmn) and os.path.isdir(forms):
            return bpmn, forms
    return None, None


def referenced_form_ids(bpmn_dir):
    """formId -> [model:task, ...], read from the XML directly."""
    refs = {}
    tasks = 0
    for path in sorted(glob.glob(os.path.join(bpmn_dir, '*.bpmn'))):
        text = open(path, encoding='utf-8').read()
        name = os.path.basename(path)
        for m in re.finditer(r'<bpmn:userTask\b[^>]*id="([^"]+)"[^>]*>(.*?)</bpmn:userTask>', text, re.S):
            tasks += 1
            fid = re.search(r'<zeebe:formDefinition[^>]*formId="([^"]+)"', m.group(2))
            refs.setdefault(fid.group(1) if fid else '(none)', []).append('%s:%s' % (name, m.group(1)))
    return refs, tasks


def walk(components):
    for c in components or []:
        yield c
        if isinstance(c, dict):
            yield from walk(c.get('components'))


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bpmn_dir, forms_dir = locate(root)
    for i, a in enumerate(argv):
        if a == '--bpmn-dir' and i + 1 < len(argv):
            bpmn_dir = argv[i + 1]
        if a == '--forms-dir' and i + 1 < len(argv):
            forms_dir = argv[i + 1]
    if not bpmn_dir or not forms_dir:
        print('cannot locate the models and forms; pass --bpmn-dir and --forms-dir')
        return 2

    problems, warnings = [], []
    declared, invalid = {}, 0
    for path in sorted(glob.glob(os.path.join(forms_dir, '*.form'))):
        base = os.path.basename(path)
        try:
            data = json.load(open(path, encoding='utf-8'))
        except json.JSONDecodeError as e:
            invalid += 1
            problems.append('%s is not valid JSON: %s' % (base, e))
            continue
        fid = data.get('id')
        if not fid:
            problems.append('%s declares no form id' % base)
        elif fid in declared:
            problems.append('form id "%s" is declared twice: %s and %s' % (fid, declared[fid], base))
        else:
            declared[fid] = base
        if not data.get('schemaVersion'):
            warnings.append('%s has no schemaVersion' % base)
        comps = list(walk(data.get('components')))
        if not comps:
            problems.append('%s has no components' % base)
        keys = {}
        for c in comps:
            if not isinstance(c, dict):
                continue
            kind = c.get('type')
            if kind in INPUT_TYPES and kind not in ('group', 'spacer', 'image', 'iframe', 'text'):
                if not c.get('key'):
                    problems.append('%s: a <%s> component has no key' % (base, kind))
                else:
                    keys[c['key']] = keys.get(c['key'], 0) + 1
                if not c.get('label'):
                    warnings.append('%s: input "%s" has no label' % (base, c.get('key', kind)))
        for k, n in keys.items():
            if n > 1:
                problems.append('%s: input key "%s" is used %d times' % (base, k, n))
        # naming convention: the file is named after the form id
        if fid and os.path.splitext(base)[0] != fid:
            warnings.append('%s: file name does not match the form id "%s"' % (base, fid))

    refs, tasks = referenced_form_ids(bpmn_dir)
    referenced = {k for k in refs if k != '(none)'}

    missing = sorted(referenced - set(declared))
    orphans = sorted(set(declared) - referenced)
    unbound = refs.get('(none)', [])
    for f in missing:
        problems.append('user task(s) reference form "%s" but no .form file declares it: %s'
                        % (f, ', '.join(refs[f])))
    for o in orphans:
        warnings.append('form "%s" (%s) is not referenced by any user task' % (o, declared[o]))
    for u in unbound:
        problems.append('user task %s has no form reference' % u)

    print('=' * 88)
    print('FORMS: %s' % forms_dir.replace('\\', '/'))
    print('=' * 88)
    print('  form files            : %d' % (len(glob.glob(os.path.join(forms_dir, '*.form')))))
    print('  distinct form ids     : %d' % len(declared))
    print('  user tasks in models  : %d' % tasks)
    print('  user tasks with a form: %d' % (tasks - len(unbound)))
    print('  distinct ids used     : %d' % len(referenced))
    print('  referenced but absent : %d' % len(missing))
    print('  never referenced      : %d' % len(orphans))
    print('  invalid JSON          : %d' % invalid)
    print()
    print('SUMMARY {"forms":%d,"ids":%d,"tasks":%d,"missing":%d,"orphans":%d,"invalid":%d}'
          % (len(glob.glob(os.path.join(forms_dir, '*.form'))), len(declared), tasks,
             len(missing), len(orphans), invalid))
    if warnings:
        print('\n  -- WARNINGS (%d) --' % len(warnings))
        for w in warnings[:20]:
            print('   * %s' % w)
        if len(warnings) > 20:
            print('   * ... and %d more' % (len(warnings) - 20))
    if problems:
        print('\n  -- PROBLEMS (%d) --' % len(problems))
        for p in problems[:30]:
            print('   * %s' % p)
        if len(problems) > 30:
            print('   * ... and %d more' % (len(problems) - 30))
    print('\nRESULT: %s' % ('clean' if not problems else '%d problem(s)' % len(problems)))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
