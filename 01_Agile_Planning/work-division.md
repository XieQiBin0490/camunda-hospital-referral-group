# Work division and ownership

Two units share this project, so there are two divisions. The **portfolio unit**
(UFCEP4-0-3) division is the contribution matrix in the Agile delivery record and
is not changed here. The **implementation unit** division below covers the
artefacts this project grew beyond the portfolio brief: the runnable model, the
Java workers, the forms and the test evidence.

Every activity has a **first owner** (leads delivery, answers for it) and a
**second owner** (keeps current enough to take over), as the brief requires.

## 1. Who owns what

| Deliverable | First owner | Second owner | Where it is |
| --- | --- | --- | --- |
| Operational model `O1`, merged and integrated | **max** | henry | `02_BPMN_Models/O1_Operational_Merged.bpmn` |
| Strategic models `S1`, `S2`, `S3` | **max** | finn | `02_BPMN_Models/S*.bpmn` |
| Model validation (moddle, structural, Camunda 8 lint, layout) | **peter** | max | `09_Tests_and_Tools/validate-models.py` |
| 68 Camunda Forms and their task bindings | **peter** | henry | `03_Forms/` |
| Form validation and rendering evidence | **peter** | finn | `09_Tests_and_Tools/validate-forms.py`, `render-forms.mjs` |
| Java job workers — 3 gating workers (slots, capacity, payment) | **finn** | peter | `04_Java_Worker/src/main/java/uk/ac/uwe/hospital/tasks/QueryAvailableAppointmentSlotsWorker.java`, `RequestTreatmentCapacityWorker.java`, `RequestSecurePaymentWorker.java` |
| Java job workers — correspondence and referral (4) | **max** | finn | `.../tasks/RequestMissingDocumentationWorker.java`, `SendReferralOutcomeWorker.java`, `RedirectReferralWorker.java`, `SendAppointmentConfirmationLetterWorker.java` |
| Java job workers — clinical and finance (3) | **peter** | finn | `.../tasks/RequestBloodTestWorker.java`, `RequestRefundWorker.java`, `GenerateManagementReportsWorker.java` |
| Worker failure handling, audit log, episode correlation | **finn** | henry | `.../AbstractWorker.java`, `support/OperationsLog.java`, `support/HospitalStore.java` |
| Worker unit tests (41) | **peter** | finn | `04_Java_Worker/src/test/java/uk/ac/uwe/hospital/` |
| Variable-to-gateway contract (which worker writes what the gateway reads) | **henry** | max | `09_Tests_and_Tools/validate-contract.py`, README contract table |
| Acceptance run — 18 cases against the deployed build | **peter** | max | `09_Tests_and_Tools/run-acceptance.mjs` |
| Worker-driven scenarios — 6 cases | **finn** | peter | `09_Tests_and_Tools/run-worker-demo.mjs`, `run-worker-scenarios.ps1` |
| Tasklist browser run — 19 forms filled by hand | **peter** | henry | `09_Tests_and_Tools/run-form-tasklist.mjs`, evidence in `05_Test_Evidence/form-demo/` |
| One-command verification (9 steps) and its evidence | **henry** | peter | `09_Tests_and_Tools/verify-all.ps1`, `05_Test_Evidence/verification/` |
| Deployment and cluster evidence | **max** | peter | `05_Test_Evidence/`, `09_Tests_and_Tools/deploy-all.mjs` |
| Requirements traceability (44 requirements, four levels) | **henry** | max | `07_Portfolio_Documents/...Task03...` |
| Alignment evaluation | **henry** | finn | as above |
| Acceptance criteria evaluation and the criteria revisions | **henry** | peter | `...Task04...` |

## 2. The implementation unit, by share

Each column sums to 100%. The Total column is the split of the group mark, which
the group agreed to divide equally: **25% each**. The two are different measures —
the activity columns record who carried which work, the Total column records how
the mark is shared — so a member can hold a large share of one activity and still
take an equal share overall.

| Member | Runnable model | External workers | Camunda Forms | Tests and evidence | Total |
| --- | --- | --- | --- | --- | --- |
| max | 45% | 25% | 15% | 20% | **25%** |
| finn | 10% | 40% | 10% | 25% | **25%** |
| henry | 15% | 15% | 20% | 30% | **25%** |
| peter | 30% | 20% | 55% | 25% | **25%** |

Rationale, in the same voice as the portfolio matrix: **peter** owns the forms and
the testing, which is where most of the implementation work sits, and he wrote the
acceptance run and the form checks; **finn** owns the external workers, including
the three that govern a gateway variable; **max** owns the runnable model and the
integration that makes six process definitions deploy as one family; **henry**
owns the variable-to-gateway contract, the verification suite and the evidence
that ties each artefact to a requirement.

## 3. What each person must be able to explain

The brief says every member must be able to explain their contribution, and the
two marked standups are individual. Rehearse these four before the session.

### max — the model and the integration

* **Why four files and not one.** Strategic activities are not operational steps:
  `S1`, `S2` and `S3` answer different questions from `O1`, and merging them would
  bury the business view in task detail.
* **Why one referral message starts three processes.** All three models declare
  the same start message, so a single referral wakes the operational process and
  both strategic ones. Explain that this is a consequence of modelling the same
  business at two levels, and that the walkthrough cancels the two strategic twins
  so the operational path is what you see.
* **What deploying found that validation did not.** Three XSD sequence violations
  and one runtime form-binding defect (`DEP-01` to `DEP-04`).

### finn — the workers and failure handling

* **Which worker owns which gateway variable.** Three do:
  `query-available-appointment-slots` writes `suitableSlotFound`,
  `request-treatment-capacity` writes `treatmentCapacityConfirmed`,
  `request-secure-payment` writes `paymentStatus`. If one writes the wrong name,
  the gateway takes a branch nobody chose and nothing errors.
* **Why "no answer" is not "no capacity".** A provider that answers "no" is a
  business outcome the model already branches on; a provider that does not answer
  is a retry (`TransientJobException` -> fail with one fewer retry). Reporting a
  network fault as no capacity sends a patient to escalation for the wrong reason.
* **The known gap.** The models declare no error boundary events, so a rejected
  job becomes an unhandled-error incident instead of being caught. That is stated
  in `04_Java_Worker/README.md` rather than hidden.

### henry — requirements, the contract and the evidence

* **The variable-to-gateway contract.** `validate-contract.py` checks that every
  variable a worker demands can actually be supplied by a form, another worker or
  the process start. It found two real gaps: `appointmentReference` and
  `redirectDestination` were demanded by workers but no form could supply them,
  which stalled a live run with an incident.
* **The traceability.** 44 requirements traced at four levels — requirement,
  strategic activity, i\* element, implementation artefact — 28 fully, 12 partly,
  2 not supported, 2 out of scope, with the two out-of-scope ones named as such.
* **The verification suite.** Nine checks, one command: build and 41 unit tests,
  model validation, deploy, 18 acceptance cases, 6 worker scenarios, document
  layout, form validation, form rendering, worker input contract. All pass in the
  workspace.

### peter — forms, tests and the interactive run

* **The form-to-task binding.** 68 forms, 99 user tasks, every task bound, no
  orphans, no invalid JSON, and every form renders under `form-js` — the renderer
  Tasklist uses. A form can be valid JSON, deploy cleanly and still fail to render;
  only the renderer can tell you that.
* **Why a blank field is dangerous.** A form submits every field it renders, so a
  field left empty **overwrites** an existing process variable with an empty
  string. That is how `appointmentReference` was wiped by the next task's form.
* **The Tasklist run.** One command starts the workers, opens Tasklist, logs in as
  `demo` and fills 19 forms in sequence while the workers handle the automated
  activities; the instance ends `COMPLETED` with no incidents.

## 4. Who did what, concretely

Backlog identifiers (`PB-…`, `S3-…`, `S4-…`) are the ones in the portfolio's own
backlog and standup records, so every line here can be checked against them.

### max — strategic BPMN and integration

**Portfolio work.** Modelled and merged the strategic view: `S3-02` built
`S1_Strategic_Landscape` (25 flow nodes, 7 external participants) and the
abstraction note; `S3-03` the six-lane referral-to-authorisation model; `S4-05`
rebuilt the three Sprint 1/2 fragments as one model family sharing one participant
register and naming convention, and `O1_Operational_Merged` merged them at task
level; `S4-06` wrote the message-flow register; `S4-07` fixed the correlation-key
defect that made a message boundary event invalid. 45% of the BPMN activity and
second owner on the traceability table.

**Implementation work.** `WorkersApplication.java` (registers the thirteen workers
and refuses to start if a declared job type has no subscriber — the coverage check
that catches a process that would otherwise park silently) and `WorkerConfig.java`;
three workers: `SendReferralOutcomeWorker`, `RedirectReferralWorker`,
`SendAppointmentConfirmationLetterWorker`; the deployment path (`deploy-all.mjs`)
and the cluster evidence in `05_Test_Evidence/`.

**Point at this.** `02_BPMN_Models/O1_Operational_Merged.bpmn`, the 68/68 + 6
process-definition deploy line, `05_Test_Evidence/`.

**Ten-second proof.** Open `O1` in Camunda Modeler: eight lanes, 59 flow nodes,
15 message flows, status bar clean.

### finn — i\* models and the external workers

**Portfolio work.** `S3-09` closed the i\* tooling decision and drafted the SD
model (12 actors, 27 dependencies); `S3-10` wrote the SR decompositions; `S4-12`
delivered SD v1.0 (16 actors, 37 typed dependencies) and `S4-13` the SR;
`S4-14` recorded the soft goals with their conflicts; `S4-15` reconciled the
assumptions note. 60% of the i\* activity.

**Implementation work.** `AbstractWorker.java` — the single place that decides
what a failure means (answer "no" is a business outcome; no answer is a retry;
invalid input is a named error; anything unexpected is an incident);
`HospitalStore.java` (episode correlation and duplicate-payment detection);
`OperationsLog.java` (append-only audit with actor, time and action); the three
workers that own a gateway variable: `QueryAvailableAppointmentSlotsWorker`
(`suitableSlotFound`), `RequestTreatmentCapacityWorker`
(`treatmentCapacityConfirmed`, with the attempt counter and next-attempt date that
REQ-16 needs) and `RequestSecurePaymentWorker` (`paymentStatus`, with the
card-data exclusion and duplicate suppression). Author of the six worker-driven
scenarios.

**Point at this.** `06_iStar_Models/`, the three worker classes named above,
`05_Test_Evidence/worker-run/workers-capacity-unavailable.log` (the line
`no capacity on attempt 1` followed by `capacity confirmed on attempt 2`).

**Ten-second proof.** Open `iStar_SR_Initial_Release.pdf`, then the
capacity-unavailable scenario log.

### henry — requirements, the variable contract, the evidence

**Portfolio work.** `S3-13` closed the requirements list at 44 identifiers with
their source sentences; `S3-15` added the filename convention and the definition
of done to the README; `S3-08` produced the version snapshots and started the
traceability at 35 of 44 rows; `S4-16` completed the trace to 44 rows (28 fully,
12 partly, 2 not supported, 2 out of scope); `S4-17` wrote the ten prioritised
improvements; `S4-21` assembled the portfolio and ran the hand-in check.
`PB-05`/`PB-06` requirements and user stories, `PB-07` the traceability matrix,
`PB-36`/`PB-37` the alignment evaluation and its 44-requirement trace,
`PB-38`–`PB-40` the change log and criteria revisions, `PB-02` the repository,
README and filename convention, `PB-03`/`PB-04` the backlogs and definition of
done, `PB-42` the feedback action log, `PB-43` the retrospectives. 45% of the
evaluation activity, 60% of the documentation activity.

**Implementation work.** `JobContext.java` (validated reads: a missing or
malformed variable is rejected **by name**, because a FEEL null on a gateway takes
a branch nobody chose), `ValidationException.java`, `Ids.java`;
`validate-contract.py`, which checks that every variable a worker demands can
actually be supplied and found two real gaps (`appointmentReference`,
`redirectDestination`); the nine-step `verify-all.ps1` and its evidence; the
requirement→test matrix (`build-reqtest.py`, 44 requirements against the 18
executed cases); two workers, `RequestMissingDocumentationWorker` and
`DistributeClinicalCorrespondenceWorker`.

**Point at this.** `07_Portfolio_Documents/...Task03...` (the 44-row
traceability), `07_Portfolio_Documents/...Task04...` (the criteria evaluation),
`09_Tests_and_Tools/validate-contract.py`, `09_Tests_and_Tools/verify-all.ps1`,
`05_Test_Evidence/verification/`.

**Ten-second proof.** Open the traceability table and read one row across its four
levels, then run `validate-contract.py` and show the two gaps it caught.

### peter — forms, testing and the interactive run

**Portfolio work.** `S3-14` produced the revised criteria table with the original
wording retained beside each revision; `S3-16` built the repeatable lint and audit
export; `S4-08` deployed the model family and re-validated it; `S4-19` executed the
acceptance cases. 35% of the evaluation activity through the acceptance testing and
the forms.

**Implementation work.** All 68 Camunda Forms and their bindings to 99 user tasks,
including the field that closes the worker contract gap (`appointmentReference` on
the booking forms, `redirectDestination` on the referral decision form);
`support/ExternalServices.java` (the simulated providers, including the four
payment outcomes the gateway distinguishes) and `support/FailureInjection.java`
(deterministic fault injection); three workers, `RequestBloodTestWorker`,
`RequestRefundWorker`, `GenerateManagementReportsWorker`; `validate-forms.py`,
`render-forms.mjs` (all 68 forms rendered by `form-js`, the renderer Tasklist
uses) and the 41 unit tests; `run-acceptance.mjs` (18 cases) and
`run-form-tasklist.mjs` — the interactive run that opens Tasklist and fills 19
forms in sequence.

**Point at this.** `03_Forms/`, `05_Test_Evidence/worker-run/form-render.txt`
(`TOTAL=68 FAILED=0`), `05_Test_Evidence/form-demo/` (19 screenshots),
`04_Java_Worker/src/test/`.

**Ten-second proof.** Run `run-form-tasklist.mjs`: the browser opens, fills a form,
moves to the next.

## 5. Working rules the group agreed

1. The first owner delivers and answers for the activity; the second owner keeps
   up to date so the work does not stop if the first cannot continue.
2. Nothing is Done until it has been reviewed by the second owner, is in the
   shared workspace, and is linked to its evidence.
3. A defect found by running the system is recorded, not quietly fixed: see
   `08_Repository_Documents/defect-log.md`.
4. Evidence over assertion: a claim in a document must point at a file that can be
   re-run.


