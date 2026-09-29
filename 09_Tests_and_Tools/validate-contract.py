#!/usr/bin/env python3
"""Cross-check what the workers demand against what a human can supply.

The forms are generated from the variables the *gateways* read, so a variable a
worker demands with requireString/requireBool, but which no gateway reads, has no
field on any form - and therefore cannot be supplied by a person at Tasklist. The
worker then rejects the job, and because the models declare no error boundary
events the thrown BPMN error becomes an unhandled-error incident and the instance
stops. That is exactly how T_SendAppointmentLetter stalled a live run.

This checks, for every hard requirement in the worker sources, whether anything
can supply it: a form field, another worker, or the process start.

usage: python validate-contract.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def worker_requirements(worker_dir):
    """variable -> [worker class, ...] for every hard requirement."""
    req = {}
    for path in glob.glob(os.path.join(worker_dir, 'tasks', '*.java')) + \
            glob.glob(os.path.join(worker_dir, '*.java')):
        text = open(path, encoding='utf-8').read()
        cls = os.path.basename(path)[:-5]
        for m in re.finditer(r'require(String|Bool)\(\s*"([^"]+)"', text):
            req.setdefault(m.group(2), set()).add(cls)
    return req


def form_fields(forms_dir):
    """variable -> [form id, ...] for every input component."""
    fields = {}
    for path in glob.glob(os.path.join(forms_dir, '*.form')):
        data = json.load(open(path, encoding='utf-8'))
        fid = data.get('id') or os.path.basename(path)

        def walk(comps):
            for c in comps or []:
                if not isinstance(c, dict):
                    continue
                if c.get('key'):
                    fields.setdefault(c['key'], set()).add(fid)
                walk(c.get('components'))
        walk(data.get('components'))
    return fields


def variables_written_by_workers(worker_dir):
    """variable -> [worker class, ...] for everything a worker writes."""
    written = {}
    for path in glob.glob(os.path.join(worker_dir, 'tasks', '*.java')):
        text = open(path, encoding='utf-8').read()
        cls = os.path.basename(path)[:-5]
        for m in re.finditer(r'\.set\(\s*"([^"]+)"', text):
            written.setdefault(m.group(1), set()).add(cls)
        for m in re.finditer(r'out\.put\(\s*"([^"]+)"', text):
            written.setdefault(m.group(1), set()).add(cls)
    return written


def main():
    worker_dir = None
    for c in [os.path.join(ROOT, 'workers', 'src', 'main', 'java', 'uk', 'ac', 'uwe', 'hospital'),
              os.path.join(ROOT, '04_Java_Worker', 'src', 'main', 'java', 'uk', 'ac', 'uwe', 'hospital')]:
        if os.path.isdir(c):
            worker_dir = c
            break
    forms_dir = None
    for c in [os.path.join(ROOT, 'output', 'forms'), os.path.join(ROOT, '03_Forms')]:
        if os.path.isdir(c):
            forms_dir = c
            break
    if not worker_dir or not forms_dir:
        print('cannot locate the workers and forms')
        return 2

    req = worker_requirements(worker_dir)
    fields = form_fields(forms_dir)
    written = variables_written_by_workers(worker_dir)

    start_vars = {'patientId', 'documentsComplete', 'treatmentCode', 'treatmentCycles',
                  'reportPeriod', 'cycleReference', 'reviewCycleResults'}

    print('=' * 88)
    print('WORKER INPUT CONTRACT')
    print('=' * 88)
    print('  hard requirements in the worker source : %d' % len(req))
    print('  distinct form fields                   : %d' % len(fields))
    print()

    unsupplied = []
    for var in sorted(req):
        sources = []
        if var in fields:
            sources.append('%d form(s)' % len(fields[var]))
        # A worker that both requires and writes a variable is passing it through,
        # not supplying it - SendAppointmentConfirmationLetterWorker does exactly
        # that, and counting it as a source hid a real gap.
        writers = set(written.get(var, set())) - set(req[var])
        if writers:
            sources.append('written by %s' % ', '.join(sorted(writers)))
        if var in start_vars:
            sources.append('process start variable')
        if not sources:
            unsupplied.append(var)
        print('  %-26s %-34s %s' % (var, ', '.join(sorted(req[var])),
                                    ' <- '.join(sources) if sources else 'NOTHING CAN SUPPLY THIS'))

    print()
    if unsupplied:
        print('  -- gaps: %d variable(s) no form and no worker can supply --' % len(unsupplied))
        for u in unsupplied:
            print('   * %s (required by %s)' % (u, ', '.join(sorted(req[u]))))
    print()
    print('SUMMARY {"requirements":%d,"unsupplied":%d}' % (len(req), len(unsupplied)))
    print('RESULT: %s' % ('every worker requirement can be supplied' if not unsupplied
                          else '%d unsupplied requirement(s)' % len(unsupplied)))
    return 0 if not unsupplied else 1


if __name__ == '__main__':
    sys.exit(main())
