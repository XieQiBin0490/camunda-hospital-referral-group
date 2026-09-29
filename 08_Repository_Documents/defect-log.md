# Defect log

Every defect found in the project is recorded here with its source, its status and
the evidence that closes it. Defects are grouped by where they were found.

## A. Defects in the Sprint 1 and Sprint 2 working files

Found by parsing `source/bpmn1.bpmn`, `source/bpmn2_dup.bpmn` and
`source/bpmn3.bpmn` with the same moddle schema Camunda Modeler uses on open, and by
running the Camunda Modeler lint engine headlessly. 48 individual
findings in total, grouped into the sixteen categories below. Full raw output:
`extract/audit_originals_raw.txt` (reproduced in Appendix C).

| ID | Defect | Files affected | Status | Resolution | Evidence |
| --- | --- | --- | --- | --- | --- |
| DEF-01 | Mixed execution platforms: Zeebe (Camunda 8) in two files, Camunda 7 `camunda:*` attributes and ${} expressions in the third; no execution platform declared in that file | 第二, 第三 vs 第一 | Fixed | All delivered models targeted at Camunda 8 (Zeebe) 8.10; every expression converted to FEEL; job workers declared with `zeebe:taskDefinition` | Appendix B validation; successful deployment |
| DEF-02 | Duplicate element identifiers across files (`Participant_0xulon7`, `Participant_1dfajvw`, `Process_0fl9bxn`, `Process_0rkzkrk`, `Participant_1aq3lho` reused with different meanings) | 第二, 第三 | Fixed | Single naming convention: `P_` / `L_` / `T_` / `G_` / `E_` / `F_` / `MF_` / `Msg_` | Duplicate-ID check in the structural audit: 0 findings |
| DEF-03 | Participant labelled "External Payment Service Provider" pointed at the hospital's own process | 第二 | Fixed | One participant per organisation, each name matched to its own process | Structural audit: 0 mislabelled participants |
| DEF-04 | Two participants both named "External Payment Service Provider"; two both named "External Scheduling Service" | 第二, 第三 | Fixed | Each external organisation appears exactly once per collaboration | Duplicate participant-name check: 0 findings |
| DEF-05 | Empty processes and empty lanes: 7 empty processes and 5 empty lanes in 第二, 6 black-box participants with no work in 第三, 6 empty lanes in 第一 | all three | Fixed | Only lanes and participants that carry work are declared | Empty-lane and empty-process checks: 0 findings |
| DEF-06 | Dangling and unreachable elements: "Record missing document list" had no outgoing flow; "Send referral rejection letter" and "Send referral redirect notice" had no incoming flow; the GP pool's "Submit referral documentation" was a dead end; 第二's "Process Payment" had neither | 第一, 第二 | Fixed | The missing-documentation request returns to the completeness check; rejection and redirect terminate in named end events; every node is reachable and every path reaches an end event | Reachability and dead-end checks: 0 findings |
| DEF-07 | A rejected or redirected referral was forwarded to the booking team | 第一 | Fixed | The decision gateway has four labelled branches; only the accepted branch reaches the Outpatient Bookings Team | TC-03 and TC-04 executed against the deployed model |
| DEF-08 | Exclusive gateways with no default flow (5 occurrences), which fail at runtime with "no outgoing sequence flow could be selected" | 第二, 第三 | Fixed | Every diverging exclusive gateway declares an explicit default flow, and every non-default branch carries a condition | Gateway-default check: 0 findings; all 18 test cases traverse gateways without a no-flow incident |
| DEF-09 | Inconsistent decision values: `"reject"`, `"redirect"`, `"Request more info"` and `"Accept"` used for the same variable | 第一 | Fixed | One controlled value set (`accepted`, `rejected`, `information required`, `redirected`) used consistently | TC-03 and TC-04 reach the correct end events |
| DEF-10 | Roles confused between lanes: the Medical Secretaries lane held slot querying, slot selection and slot locking; the Outpatient Bookings Team lane held referral validation; the telephone task sat in the Call Handling lane but was assigned to `outpatient_booking_team` | 第三 | Fixed | Work attributed to the team the case study makes accountable | Lane attribution verified by the model inventory |
| DEF-11 | Non-canonical XML: no `<bpmn:incoming>` or `<bpmn:outgoing>` child elements on any flow node | 第三 | Fixed | Every flow node declares its incoming and outgoing sequence flows | Generated models include both on every node |
| DEF-12 | Invalid extension elements: `zeebe:taskDefinition` on end events, combined with a `messageEventDefinition` on the same event | 第三 | Fixed | Outbound messages are `sendTask` elements with a job type; message events carry only a message event definition; the correlation key is declared on the `bpmn:message` element | Camunda 8 lint: 0 reports |
| DEF-13 | Unknown attribute `camunda:gatewayDirection`, silently ignored | 第二 | Fixed | Removed; gateway direction is implied by the flow structure | Moddle parse: 0 warnings |
| DEF-14 | The 14-day telephone rule was missing, and contact attempts were not recorded | 第三 | Fixed | The 14-day rule is an explicit gateway; the attempt and its outcome are recorded | TC-06, TC-07 and TC-08 executed against the deployed model |
| DEF-15 | A 14-day timer that does not exist in the case study terminated the process | 第三 | Fixed | Replaced by the case-study rule that the patient is telephoned when the appointment is due within 14 days | TC-07 confirms no telephone task is created outside the window |
| DEF-16 | No coverage of refunds, non-attendance, delayed-letter escalation, enquiries, treatment modification or follow-up appointments | all three | Superseded | Modelled in S3 (strategic scope); recorded as not implemented in the initial release where relevant | S3 model inventory and the alignment evaluation |

## B. Defects found while deploying the delivered models

These were found only because the models were deployed to a real Camunda 8 cluster
rather than merely opened in the Modeler. They are the strongest available evidence
that the validation was genuine.

| ID | Defect | How it was found | Status | Resolution |
| --- | --- | --- | --- | --- |
| DEP-01 | `<bpmn:documentation>` emitted as a child of `<bpmn:definitions>`, which the BPMN 2.0 XSD does not allow | Deployment rejected: `cvc-complex-type.2.4.a` at line 3 | Fixed | The element was removed; the model name is carried by the collaboration element |
| DEP-02 | Event definitions emitted before `<bpmn:incoming>`/`<bpmn:outgoing>`; the XSD requires them after | Deployment rejected: `cvc-complex-type.2.4.a` on the event elements | Fixed | node serialisation reordered to documentation, extensionElements, incoming, outgoing, event definitions |
| DEP-03 | `textAnnotation` and `association` (artifacts) emitted before the last `sequenceFlow` (a flow element) | Deployment rejected: `cvc-complex-type.2.4.a` on the sequence flows | Fixed | Process serialisation reordered to laneSet, flow nodes, sequence flows, artifacts |
| DEP-04 | 68 user tasks raised `FORM_NOT_FOUND` incidents at runtime because the referenced Camunda forms were not deployed | Live execution: incident `FORM_NOT_FOUND` on the first user task of every instance | Fixed | 68 Camunda Forms generated from the models themselves and deployed with them; the incident no longer occurs |

Defects DEP-01 to DEP-03 would not have been found by opening the files in Camunda
Modeler, because the Modeler's parser is lenient where the engine's XSD validator is
strict. DEF-04 is a runtime defect that only appears once an instance is started.

## C. Status summary

| Group | Count | Fixed | Superseded | Open |
| --- | --- | --- | --- | --- |
| Sprint 1 / Sprint 2 working files (categories) | 16 | 15 | 1 | 0 |
| Deployment and runtime | 4 | 4 | 0 | 0 |
