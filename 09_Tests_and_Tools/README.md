# Tests and verification

Everything in this folder exists to answer one question: **does the delivered
work actually run, and does it behave the way the documents claim?** None of it
produces deliverable content; all of it checks content that was produced
elsewhere.

## One command

```powershell
powershell -File verify-all.ps1
```

Runs all six steps below in order and prints one summary. Exit code is 0 only if
every step passed, and the full log is written to `05_Test_Evidence/verification/`.

| Step | What runs | What proves it |
| --- | --- | --- |
| 1 | `mvn -f 04_Java_Worker/pom.xml clean package` | 41 unit tests, 0 failures, and the shaded jar is built |
| 2 | `validate-models.py` (and `work/check.mjs` when the workspace is present) | every model is structurally clean: unique ids, every reference resolves, every node reachable, every gateway branch either defaulted or conditioned, every automated activity carrying a job type, every node drawn |
| 3 | `deploy-all.mjs` | 7 process definitions and 68 forms accepted by the engine |
| 4 | `run-acceptance.mjs` | 18 acceptance cases executed against the deployed build, 18 passed, 0 incidents |
| 5 | `run-worker-scenarios.ps1` | 6 worker-driven scenarios, all reaching `COMPLETED` with no incidents |
| 6 | `diag-tables.py` | every table cell in the 8 portfolio documents fits inside its column |
| 7 | `validate-forms.py` | every form is valid JSON with a unique id, every one of the 99 user tasks binds to a form that exists, and no form file is orphaned |
| 8 | `render-forms.mjs` | every form actually **renders** in form-js, the renderer Tasklist uses. Valid JSON and a successful deployment do not prove this |
| 9 | `validate-contract.py` | every variable a worker demands can actually be supplied - by a form field, another worker or the process start. A demand nothing can satisfy stalls the instance with an unhandled-error incident, because the models declare no error boundary events |

## The interactive run

```powershell
node run-form-tasklist.mjs
```

The one to run if you want to *see* the system work. It starts the worker fleet,
starts one referral, opens Tasklist in a **visible** browser, logs in as
`demo`/`demo`, and then fills the real forms one after another - 19 of them on the
operational path - clicking **Complete Task** each time while the workers handle
the automated activities in between. Screenshots of every completed form land in
`05_Test_Evidence/form-demo/`.

Measured: `forms completed by hand: 19`, `final instance state: COMPLETED`,
`open incidents: 0`.

Two things it does that are worth knowing:

* one `Patient referral` message starts **three** process instances, because all
  three models declare the same start message, so it cancels the two strategic
  twins - otherwise every task appears three times;
* it re-sends any field whose value the process already holds. A form submits
  every field it renders, so a field left blank **overwrites** an existing
  variable with an empty string; that is how `appointmentReference` was wiped by
  the next task's form and the run stalled.


Step 4 deliberately stops any running worker fleet first: the acceptance harness
completes the automated jobs itself, so a fleet running at the same time would
race it. Step 5 owns the fleet lifecycle.

### What it needs

| | |
| --- | --- |
| Always | a Camunda 8 cluster on `127.0.0.1:8080` (`c8run.exe start`), Node.js 18+, Python 3.9+ |
| Steps 2, 3, 4, 6 | nothing else - they run from this folder as delivered |
| Steps 1 and 5 | a JDK 17+ and Maven on `PATH`. The package ships the worker **source**; the jar is built from it |

**Measured, honestly:** in the team workspace, which has the whole toolchain, all
six steps pass. From this folder as delivered, the four steps that need no build
tool pass and the two that do are **skipped with their reason printed** - Maven is
not on `PATH`, so the source is not rebuilt, the 41 unit tests are not re-run, and
there is no jar for the scenarios to exercise. A skip is never reported as a pass:
the summary counts passes, skips and failures separately, and the exit code is 0
only when nothing failed.

To turn both skips into passes, install Maven. One is already downloaded in the
team workspace - add `workers\.tools\apache-maven-3.9.9\bin` to `PATH`. If you
would rather not, build the jar once by hand and drop it into
`04_Java_Worker\prebuilt\`; step 5 will use it and only step 1 stays skipped.


## What each script does on its own

| Script | Purpose |
| --- | --- |
| `verify-all.ps1` | The entry point above; also usable as the re-verification step after any change |
| `validate-models.py` | Dependency-free structural validation: unique ids, resolvable references, reachability from a start event (boundary events included, since an event reaches them rather than a flow), gateways either defaulted or fully conditioned, a job type on every automated activity, a form on every user task, a diagram shape for every node, and no empty lane |
| `validate-forms.py` | Dependency-free form validation and wiring: valid JSON, a unique form id, at least one component, a key and a label on every input, no duplicated input key, and — the check deployment cannot make — that every `zeebe:formDefinition formId` in the models resolves to a form file, with no orphan form files. A broken binding is the DEP-04 defect: the task deploys and then raises `FORM_NOT_FOUND` |
| `render-forms.mjs` | Renders all 68 forms with `@bpmn-io/form-js` in a real browser (Edge via puppeteer-core) and reports `TOTAL=n FAILED=n`. A form can be valid JSON, deploy cleanly and still fail to render; only the renderer can tell you that. Needs `cd work && npm install @bpmn-io/form-js`, so it is skipped with a reason when that is absent |
| `validate.js` | The workspace's moddle + structural report. It needs `bpmn-moddle` from the workspace `node_modules`, so it is informative in the team workspace and inert in this folder; `validate-models.py` is the shipped equivalent |
| `run-acceptance.mjs` | 18 acceptance cases against the live cluster. Publishes the start message, drives each case by setting the variables the *following* gateway evaluates, and asserts elements reached, elements skipped, occurrence counts, final state, incidents and variables |
| `run-worker-demo.mjs` | The same idea inverted: plays **only the human tasks**, so every automated activity must be completed by a running worker. Six scenarios plus one documented skip |
| `run-worker-scenarios.ps1` | Restarts the worker fleet with each scenario's environment (capacity unavailable, payment declined, injected transient failure) and runs the case |
| `build-reqtest.py` | Builds the requirement → test-case matrix from the traceability table and the acceptance run JSON. A requirement no executed case covers is reported as uncovered rather than quietly paired with a likely-looking case |
| `check.mjs` (workspace only) | Model validation and structural audit with the real toolchain: connectivity, reachability, gateway defaults, duplicate identifiers, empty lanes, node placement, and the Camunda 8 compatibility lint |
| `audit.ps1` | Wraps the model audit and normalises the output to UTF-8 |
| `check-refs.mjs` | Every `08_Repository_Documents/…`, `models/…` style path cited in the portfolio text must resolve |
| `diag-tables.py` | Re-reads each generated `.docx` and checks every cell's longest unbreakable token against its column width, using Calibri metrics measured from the installed font |
| `tablefit.py` | The font-metric layer `diag-tables.py` uses: reads glyph advances straight out of the TrueType files, no third-party dependency |
| `measure-word.ps1` | Calibrates those metrics against Word's own layout, which is how the model was shown to be 1–3% conservative |
| `probe-tables.ps1` | Asks Word for each table's rendered width, to catch a table wider than the text column |
| `pages.ps1` | Page and word counts per document, from Word |
| `find-page.ps1` | Finds which page a phrase appears on, from Word |

## What is deliberately not here

The model, form, diagram and document **generators** are not in this folder.
They are the build toolchain rather than tests, and they are retained in the team
workspace. Including them would document *how* the artefacts were produced, which
is a different question from whether they work.
