# Submission map: which artefact belongs to which assessment

This repository serves **two separate assessments** for module UFCEP4-0-3. They
are marked against different criteria and have different deadlines, so this page
says which is which.

| | Assessment | Weight | Deadline | What it is |
| --- | --- | --- | --- | --- |
| 1 | **Presentation** | 50% of the unit | **28 September 2026** | An operational BPMN model, an acceptance test plan and a justification of the modelling decisions, presented to the client (the tutors) |
| 2 | **Portfolio** | 50% of the unit | **22 October 2026** | Strategic BPMN and i\* models, used to evaluate alignment with requirements and to evaluate the acceptance criteria |

The module team's own wording: *"Coordinate the shared project across
UFCEP4-0-3 and UFCEP6-0-3 while addressing each unit's assessment criteria
separately."* One project, one repository, two sets of criteria.

## Assessment 1 — Presentation (28 September 2026)

| Folder | File | Spec §3 item |
| --- | --- | --- |
| `02_BPMN_Models/` | `O1_Operational_Merged.bpmn` | Operational BPMN, `.bpmn` |
| `02_BPMN_Models/readable_exports/` | `O1_Operational_Merged.{pdf,png,svg}` and the `_crop` set | Operational BPMN, readable export |
| `05_Test_Evidence/` | `Acceptance_Test_Plan.md` | Acceptance test plan |
| `10_Presentation/` | `UFCEP4-0-3_Presentation.pptx` | Presentation slides |

## Assessment 2 — Portfolio (22 October 2026)

| Folder | File | Spec §3 item |
| --- | --- | --- |
| `02_BPMN_Models/` | `S1_Strategic_Landscape.bpmn`, `S2_Strategic_Referral_To_Authorisation.bpmn`, `S3_Strategic_Treatment_To_Aftercare.bpmn` | Strategic BPMN, `.bpmn` |
| `02_BPMN_Models/readable_exports/` | the S1, S2 and S3 exports | Strategic BPMN, readable PDF exports |
| `06_iStar_Models/` | `iStar_SD_Initial_Release.{pdf,png,svg}`, `iStar_SR_Initial_Release.{pdf,png,svg}`, `iStar_models_source.json` | i\* SD and SR models, with editable source |
| `07_Portfolio_Documents/` | `UFCEP4-0-3_02_Task03_Alignment_Evaluation.docx` | Alignment evaluation, with the requirements traceability table |
| `07_Portfolio_Documents/` | `UFCEP4-0-3_03_Task04_Acceptance_Evaluation.docx` | Acceptance criteria evaluation |
| `07_Portfolio_Documents/` | `UFCEP4-0-3_00_Cover_and_Contents.docx`, `_01_Task01_02_Strategic_BPMN_and_iStar.docx`, `_05_References.docx`, `_06_Appendices.docx`, `UFCEP4-0-3_Portfolio.docx` | The portfolio document set |
| `01_Agile_Planning/` | sprint backlogs, work division, version snapshots | Agile delivery record |

## Shared — belongs to both

| Folder | What it holds | Why both units need it |
| --- | --- | --- |
| `01_Agile_Planning/` | Product backlog and the Sprint 1–4 backlogs, work division | Both units mark agile delivery: product backlog, sprint backlogs, first and second owners, estimates, acceptance conditions, status |
| `03_Forms/` | The 68 Camunda Forms | The user tasks in every model bind to these |
| `04_Java_Worker/` | The Java job-worker fleet | Services the automated activities; also carries the cross-pool message publishing |
| `05_Test_Evidence/` | Acceptance run, screenshots, verification logs, worker-driven scenarios | Execution evidence for the acceptance evaluation and the models |
| `08_Repository_Documents/` | Model inventory, defect log, integration decision, assumption register, improvement proposals, strategic-to-operational map, manual run guide | The repository documents both specification sections ask for |
| `09_Tests_and_Tools/` | The verification harness | Reproduces every measurement the documents claim |

## Status of the Sprint 3 and Sprint 4 record

`07_Portfolio_Documents/UFCEP4-0-3_04_Agile_Delivery_Record.docx` is the agile
record for **Sprints 3 and 4**, which are the Portfolio sprints. Its dates are
the module's published ones:

| | Sprint | Marked standup | Marked sprint review |
| --- | --- | --- | --- |
| Sprint 1 | 14–18 September 2026 | SU1 | SR1 |
| Sprint 2 | 21–25 September 2026 | SU2 | SR2 |
| Sprint 3 | 5–19 October 2026 | SU3 — 15 October | SR3 — 19 October |
| Sprint 4 | 20–22 October 2026 | SU4 — 21 October | SR4 — 22 October |

Sprints 3 and 4 are the Portfolio sprints, and the Portfolio deadline is
22 October — so SU3, SR3, SU4 and SR4 all fall **after the Presentation
deadline**. The four sessions are therefore marked in that document as
*scheduled*, and each entry is confirmed at the session itself: a standup table
filled in before the standup is a plan, not a record. The review snapshots
(SR3 and SR4) must likewise be taken from the repository at the time of the
review, not reconstructed afterwards.

**Presentation-side agile evidence is separate.** The Presentation unit marks
SU1, SU2, SR1 and SR2 (10% + 20% of that unit). Those records are not in this
document, which covers Sprints 3 and 4 only.

The portfolio spec is explicit that this matters: *"Review marks assess the
increment available at that review; later improvements do not retrospectively
replace those marks"*, and *"Preserve a version or snapshot for each review."*
