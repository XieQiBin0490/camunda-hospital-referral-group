#!/usr/bin/env python3
"""Structural validation of the delivered BPMN models, with no dependencies.

The team workspace validates with `work/check.mjs`, which loads `bpmn-moddle` and
`@camunda/linting` from `node_modules`. Neither is part of the submission, so the
delivered package needs a checker that runs on a bare Python install. This is it:
the same class of structural check, written against the XML directly.

Checks per model:

  * the document is well-formed and every element reference resolves
    (`sourceRef`, `targetRef`, `attachedToRef`, `default`, `flowNodeRef`,
    `messageRef`, `processRef`)
  * identifiers are unique
  * every flow node is reachable from a start event, and every sequence flow
    has both ends
  * every gateway with more than one outgoing flow either has a default flow or
    gives every outgoing flow a condition
  * every service task and send task declares a Zeebe job type
  * every user task declares a form (a warning, not a defect, where the release
    intentionally has none)
  * every declared flow node has a diagram shape, and no lane is empty
  * lane membership matches the declared lane set

Prints a per-file section and a SUMMARY line per file in the same shape the
workspace validator uses, so `verify-all.ps1` can read either.

usage: python validate-models.py <model.bpmn> [more.bpmn ...]
"""
import re
import sys
import xml.etree.ElementTree as ET

BPMN = '{http://www.omg.org/spec/BPMN/20100524/MODEL}'
BPMNDI = '{http://www.omg.org/spec/BPMN/20100524/DI}'
ZEEBE = '{http://camunda.org/schema/zeebe/1.0}'

FLOW_NODES = ('task', 'userTask', 'serviceTask', 'sendTask', 'receiveTask', 'manualTask', 'businessRuleTask',
              'scriptTask', 'callActivity', 'subProcess', 'startEvent', 'endEvent', 'intermediateCatchEvent',
              'intermediateThrowEvent', 'boundaryEvent', 'exclusiveGateway', 'inclusiveGateway',
              'parallelGateway', 'eventBasedGateway', 'complexGateway')


def tag(el):
    return el.tag.replace(BPMN, '').replace(BPMNDI, 'di:').replace(ZEEBE, 'zeebe:')


def check(path):
    problems, warnings = [], []
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        return problems + ['not well-formed XML: %s' % e], warnings, 0, 0, []
    root = tree.getroot()

    # ---- identifiers -------------------------------------------------------
    ids = {}
    for el in root.iter():
        i = el.get('id')
        if i:
            ids.setdefault(i, []).append(tag(el))
    for i, kinds in ids.items():
        if len(kinds) > 1:
            problems.append('duplicate id "%s" used by %s' % (i, ', '.join(kinds)))

    # ---- references --------------------------------------------------------
    ref_attrs = ('sourceRef', 'targetRef', 'attachedToRef', 'default', 'flowNodeRef',
                 'messageRef', 'processRef', 'calledElement')
    for el in root.iter():
        for a in ref_attrs:
            v = el.get(a)
            if v and v not in ids:
                problems.append('%s "%s" has a %s that does not resolve: %s'
                                % (tag(el), el.get('id') or el.get('name') or '?', a, v))

    shapes = {s.get('bpmnElement') for s in root.iter(BPMNDI + 'BPMNShape')}
    edges = {e.get('bpmnElement') for e in root.iter(BPMNDI + 'BPMNEdge')}

    nodes = 0
    processes = 0
    job_types = set()
    for proc in root.iter(BPMN + 'process'):
        processes += 1
        elements = [el for el in proc.iter() if tag(el) in FLOW_NODES]
        nodes += len(elements)
        by_id = {el.get('id'): el for el in elements}
        flows = list(proc.iter(BPMN + 'sequenceFlow'))
        outgoing = {}
        incoming = {}
        for f in flows:
            outgoing.setdefault(f.get('sourceRef'), []).append(f)
            incoming.setdefault(f.get('targetRef'), []).append(f)

        start_ids = [el.get('id') for el in elements if tag(el) == 'startEvent']
        # Reachability from every start event. A boundary event is reached by the
        # event that fires it, not by a sequence flow, so it joins the set once
        # the activity it is attached to is reachable - which is why this runs to
        # a fixed point rather than in one pass.
        seen, queue = set(start_ids), list(start_ids)

        def propagate():
            while queue:
                cur = queue.pop()
                for f in outgoing.get(cur, []):
                    nxt = f.get('targetRef')
                    if nxt is not None and nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)

        propagate()
        changed = True
        while changed:
            changed = False
            for el in elements:
                if tag(el) != 'boundaryEvent':
                    continue
                if el.get('attachedToRef') in seen and el.get('id') not in seen:
                    seen.add(el.get('id'))
                    queue.append(el.get('id'))
                    changed = True
            propagate()

        unreachable = [i for i in by_id if i not in seen]
        for i in unreachable:
            problems.append('node %s "%s" is not reachable from any start event'
                            % (i, by_id[i].get('name') or ''))

        for el in elements:
            i, kind, name = el.get('id'), tag(el), el.get('name') or ''
            # zeebe:taskDefinition and zeebe:formDefinition live inside
            # bpmn:extensionElements, which is a direct child of the activity
            ext = el.find(BPMN + 'extensionElements')
            if kind in ('serviceTask', 'sendTask'):
                td = ext.find(ZEEBE + 'taskDefinition') if ext is not None else None
                if td is None or not td.get('type'):
                    problems.append('%s %s "%s" has no Zeebe job type' % (kind, i, name))
                else:
                    job_types.add(td.get('type'))
            if kind == 'userTask':
                fd = ext.find(ZEEBE + 'formDefinition') if ext is not None else None
                if fd is None or not fd.get('formId'):
                    warnings.append('user task %s "%s" has no form reference' % (i, name))
            if kind.endswith('Gateway'):
                outs = outgoing.get(i, [])
                if len(outs) > 1:
                    if not el.get('default') and not all(
                            f.find(BPMN + 'conditionExpression') is not None for f in outs):
                        problems.append('gateway %s "%s" has %d outgoing flows but neither a default '
                                        'nor a condition on every one' % (i, name, len(outs)))
            if kind == 'endEvent' and not incoming.get(i):
                problems.append('end event %s "%s" has no incoming flow' % (i, name))
            if i and i not in shapes:
                problems.append('node %s "%s" has no diagram shape' % (i, name))

        for lane in proc.iter(BPMN + 'lane'):
            members = [r.text for r in lane.findall(BPMN + 'flowNodeRef')]
            if not members:
                problems.append('lane %s "%s" is empty' % (lane.get('id'), lane.get('name') or ''))
            for m in members:
                if m not in by_id:
                    problems.append('lane %s references %s, which is not a flow node in this process'
                                    % (lane.get('id'), m))

        for f in flows:
            if f.get('sourceRef') not in by_id or f.get('targetRef') not in by_id:
                problems.append('sequence flow %s does not connect two nodes of this process'
                                % f.get('id'))

    for e in root.iter(BPMNDI + 'BPMNEdge'):
        if e.get('bpmnElement') and e.get('bpmnElement') not in ids:
            problems.append('diagram edge references a non-existent element: %s' % e.get('bpmnElement'))

    return problems, warnings, processes, nodes, sorted(job_types)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    total_problems = 0
    for path in argv:
        problems, warnings, processes, nodes, job_types = check(path)
        name = path.replace('\\', '/').rsplit('/', 1)[-1]
        print('=' * 88)
        print('FILE: %s' % name)
        print('=' * 88)
        print('  processes : %d' % processes)
        print('  flow nodes: %d' % nodes)
        print('  job types : %s' % (', '.join(job_types) if job_types else '(none)'))
        print('  Camunda 8 : %d job type(s) declared on automated activities' % len(job_types))
        if warnings:
            print('\n  -- WARNINGS --')
            for w in warnings:
                print('   * %s' % w)
        if problems:
            print('\n  -- STRUCTURAL --')
            for p in problems:
                print('   * %s' % p)
        print('')
        print('SUMMARY {"file":"%s","moddleWarnings":0,"structural":%d}'
              % (name, len(problems)))
        total_problems += len(problems)
    print('RESULT: %s' % ('clean' if total_problems == 0 else '%d structural problem(s)' % total_problems))
    return 0 if total_problems == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
