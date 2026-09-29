# Hospital Patient Referral, Treatment and Administration System

Camunda BPMN group project — hospital referral workflow.

| | |
| --- | --- |
| Module | UFCEP4-0-3 Business Process Modelling and Enterprise Architecture |
| Case study | Hospital Patient Referral, Treatment and Administration System |
| Group | max, finn, henry, peter |
| Assessment 1 — Presentation | 28 September 2026 |
| Assessment 2 — Portfolio | 22 October 2026 |
| Identifier of the delivered version | **build 1.0** (`Review-SR4-*`) |
| Repository | https://github.com/XieQiBin0490/camunda-hospital-referral-group |
| Automated verification | `09_Tests_and_Tools/verify-all.ps1` |

> **The repository must be readable by the tutor.** Both assessment
> specifications require the deliverables to be submitted "with accessible
> repository links". If the repository is private, either make it public or add
> the module team as a collaborator with read access; otherwise the link
> resolves to 404 for the marker and that requirement is unmet.

This repository serves two assessments and marks them separately, as the module
requires. Which artefact belongs to which assessment, and which folders are
shared, is set out in [`SUBMISSION_MAP.md`](SUBMISSION_MAP.md).

## What is in this repository

| Folder | Contents |
| --- | --- |
| `01_Agile_Planning/` | Product backlog and sprint backlogs (all four sprints), work division, review version snapshots |
| `02_BPMN_Models/` | The four `.bpmn` models. `readable_exports/` holds the PDF, PNG and SVG export of each |
| `03_Forms/` | The 68 Camunda Forms the user tasks bind to |
| `04_Java_Worker/` | The Java job-worker fleet: source, `pom.xml`, `workers.properties`, run scripts, `README.md`, `DEPLOYMENT.md` |
| `05_Test_Evidence/` | Acceptance test plan, acceptance run output, screenshots, verification logs, worker-driven scenario runs |
| `06_iStar_Models/` | i* Strategic Dependency and Strategic Rationale models: PDF, PNG, editable SVG and the JSON source |
| `07_Portfolio_Documents/` | The portfolio itself: cover and contents, Task 01/02, Task 03, Task 04, agile delivery record, references, appendices |
| `08_Repository_Documents/` | Model inventory, defect log, integration decision, i* assumptions, assumption register, improvement proposals, strategic-to-operational map, manual run guide, test evidence |
| `09_Tests_and_Tools/` | The verification harness and the scripts that reproduce every measurement the documents claim |
| `10_Presentation/` | The September presentation deck for the operational model and acceptance test plan |

The four models are:

| File | Abstraction | Role |
| --- | --- | --- |
| `S1_Strategic_Landscape.bpmn` | Level 1 | Strategic process landscape: the system boundary and the external dependencies on one page, no internal roles |
| `S2_Strategic_Referral_To_Authorisation.bpmn` | Level 2 | Referral intake through to authorised treatment |
| `S3_Strategic_Treatment_To_Aftercare.bpmn` | Level 2 | Funding, payment, treatment delivery, correspondence, enquiries and aftercare |
| `O1_Operational_Merged.bpmn` | Operational | The merged, executable process: referral, appointment, authorisation and payment |

## Cross-pool message interaction

The operational model is a BPMN **collaboration**, not a single process. It
contains the hospital pool and eight external participants, and every
cross-pool exchange is a real `bpmn:messageFlow` tied to a declared
`bpmn:message` — 15 of them, and no message is declared without being used.

Two of those pools are **executable**, so the collaboration is not just drawn,
it runs:

* `P_Hospital` → process `PR_Operational_Merged`
* `P_ReferringOrganisation` → process `PR_ReferringOrganisation`

The round trip is:

1. `PR_ReferringOrganisation` composes the referral (`RO_ComposeReferral`,
   job type `referring-org-submit-patient-referral`).
2. An **intermediate message throw event** `RO_SendReferral` publishes the
   message `Patient referral` (job type
   `referring-org-publish-patient-referral`). That message starts a
   `PR_Operational_Merged` instance at the message start event
   `E_ReferralReceived`.
3. The hospital works the referral and, in `T_NotifyReferralOutcome`,
   publishes the message `Referral outcome notification` with
   `correlationKey = referralReference`.
4. The referring pool is waiting at the **intermediate message catch event**
   `RO_AwaitOutcome` (`correlationKey = referralReference`) and completes.

In Camunda 8 a message throw event is executed as a **job**, so both directions
need job workers; they are in
`04_Java_Worker/src/main/java/uk/ac/uwe/hospital/tasks/`, and the shared
publishing helper is
`04_Java_Worker/src/main/java/uk/ac/uwe/hospital/support/MessagePublisher.java`.
A message that nothing is listening for is logged and ignored, never turned
into an incident.

The strategic models deliberately keep their external participants as collapsed
black-box pools: `S1` states in the model itself that it is a level-1 view that
shows the system boundary rather than who does what, so an executable external
process there would contradict the abstraction the model claims.

## How to open the models

Install **Camunda Modeler 5.51.0** and open any file in `02_BPMN_Models/`. Each
file declares `modeler:executionPlatform="Camunda Cloud"`, platform version
`8.10.0`.

## How to run the workers

```bash
cd 04_Java_Worker
mvn clean package
java --enable-native-access=ALL-UNNAMED -jar target/hospital-external-workers-1.0.0.jar
```

The fleet prints its job-type coverage line and then polls the gateway at
`127.0.0.1:26500`. See `04_Java_Worker/DEPLOYMENT.md` for configuration,
endpoints and deterministic fault injection.

## How to verify the claims

```powershell
powershell -File 09_Tests_and_Tools/verify-all.ps1
```

Runs every check in order and prints one summary; each step asserts a positive
signal, and a step that cannot run is reported as **skipped with its reason**,
never as a pass. The log is written to `05_Test_Evidence/verification/`.

Steps 1 and 5 need a JDK 17+ and Maven on `PATH`. The package ships the worker
**source**, not a jar, so without Maven those two steps skip. To turn them into
passes either install Maven, or build the jar once and drop it into
`04_Java_Worker/prebuilt/`.

Those four `.bpmn` files, the 68 forms and the worker fleet are the whole
system; nothing else needs to be present for it to run.

## Modelling and delivery record

* Model inventory, every defect found and how it was closed, and the
  strategic-to-operational mapping: `08_Repository_Documents/`
* Product and sprint backlogs with first owner, second owner, estimate,
  acceptance conditions, dependencies and status: `01_Agile_Planning/`
* Requirements traceability table and the alignment evaluation:
  `07_Portfolio_Documents/UFCEP4-0-3_02_Task03_Alignment_Evaluation.docx`
* Acceptance criteria, original and revised, with the execution record:
  `07_Portfolio_Documents/UFCEP4-0-3_03_Task04_Acceptance_Evaluation.docx`

## Known limitations

These are stated rather than hidden, and several are already recorded in the
portfolio documents:

* The external services are **simulated** by the worker fleet. There is no real
  scheduling system, payment provider or insurer behind the pools.
* Stores are in-memory, the gateway runs without authentication, and the models
  declare no error boundary events; a worker failure is not compensated.
* `validation.txt` records Camunda **7** lint reports alongside the Camunda 8
  result. The models target Camunda 8, and the Camunda 8 lint is clean (0
  reports for every model), so the Camunda 7 counts are not defects — they are
  what a Camunda 7 parser says about an 8.10 model.
* The generator scripts named in `06_iStar_Models/iStar_models_source.json` and
  in parts of `09_Tests_and_Tools/README.md` are not part of this repository;
  the generated artefacts are.
* The `readable_exports/` images of `O1_Operational_Merged` must be re-exported
  from Camunda Modeler after the cross-pool message interaction was added to
  that model. The `.bpmn` file is authoritative.
