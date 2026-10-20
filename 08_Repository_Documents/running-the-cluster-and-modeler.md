# Running the local cluster, and connecting Camunda Modeler to it

Written after the cluster kept stopping a few minutes after it started, and after a
teammate's deployment made every drop-down disappear. Both had concrete causes.

## 1. Start the cluster with --disable-connectors

```powershell
cd D:\app\Camunda\c8run-8.10.0-alpha5
.\c8run.exe start --disable-connectors
```

Leave that window open.

**Why.** c8run normally starts the bundled connectors runtime as well, and waits for it to
report healthy. On this machine it never does, and when the wait runs out c8run **stops the
whole cluster**:

```
INF Waiting for service to start name=Connectors retries_left=10
INF All services have been stopped.
INF All workers have stopped. Application has been gracefully shut down.
```

That is the real explanation for "Camunda keeps stopping after a few minutes", and it is
nothing to do with the models. These processes use Zeebe job workers, not connectors, so
skipping the connectors runtime costs nothing. With the flag, the log reads:

```
INF Skipping bundled connectors startup because --disable-connectors was set
INF All processes are running and healthy, exiting script...
```

and the cluster stays up.

| Endpoint | URL |
| --- | --- |
| Orchestration Cluster API | `http://localhost:8080/v2` |
| Tasklist | `http://localhost:8080/tasklist` |
| Operate | `http://localhost:8080/operate` |
| Zeebe gRPC (what Modeler uses) | `localhost:26500` |
| Login | `demo` / `demo` |

## 2. Deploy: run the script once, then the Modeler's button also works

```powershell
cd D:\camunda-hospital-referral-group\camunda-hospital-referral-group
node 09_Tests_and_Tools\deploy-all.mjs
```

`deploy-all.mjs` sends each model **together with the forms it references**, in one
deployment. Run it once on a fresh cluster. After that the Modeler's own **Deploy** button
works too, which matters because that is what a marker will press.

### The binding, and why there are two modes

Every user task carries `bindingType` on its `zeebe:formDefinition`. The models ship with
**`bindingType="latest"`**, for this reason:

| mode | the Modeler's Deploy button | a task renders | who this suits |
| --- | --- | --- | --- |
| **`latest`** (shipped) | **works** - a `.bpmn` on its own is accepted | the newest deployed version of that form | marking and demonstration |
| `deployment` | **fails** - the engine rejects a model whose forms are not in the same deployment | the form from the instance's own deployment | strict control of what a running process shows |

Switch between them with:

```powershell
pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-form-binding.ps1 show
pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-form-binding.ps1 latest
pwsh -ExecutionPolicy Bypass -File 09_Tests_and_Tools\set-form-binding.ps1 deployment
```

**Neither mode can put the forms on the cluster by itself.** A form is a separate resource,
not part of the `.bpmn`, so a fresh cluster needs `deploy-all.mjs` once. Under `latest` the
first user task otherwise fails with `FORM_NOT_FOUND` rather than at deploy time.

### Why the drop-downs disappeared

The models used to say `binding="deployment"`. `binding` is **not an attribute of
`zeebe:formDefinition`** - the element takes `formId`, `formKey`, `externalReference`,
`bindingType` and `versionTag`, and `bindingType` is an enum of exactly `deployment`,
`latest` and `versionTag`. An unknown attribute is not rejected, so the engine ignored it
and used the **default binding, `latest`** - the same value the models now carry on
purpose. A teammate deploying their own copy of the forms therefore made their older
text-box forms the newest ones, and the drop-downs were gone. That is the hazard `latest`
keeps: **always deploy from this repository's `03_Forms`, never from a personal copy.**

Camunda Modeler had been reporting the misspelling all along: `unknown attribute <binding>`,
29 warnings on O1 alone, which is exactly its formDefinition count. Reopen the models now
and the warning count is 0.

Check it, end to end, with:

```powershell
node 09_Tests_and_Tools\verify-form-binding.mjs
```

It starts a real referral, asks the engine for the first user task, fetches the form that
task resolves to, and confirms the typed controls are there.

## 3. Connecting Camunda Modeler

The Modeler does **not** need a connection to open and show a model - that needs no cluster
at all. A connection is only needed to deploy from the Modeler's own button, and the
recommended path is `deploy-all.mjs` instead, precisely because the forms have to travel
with the model.

In the Modeler, set the target to plain gRPC:

| Field | Value |
| --- | --- |
| Camunda version | 8.10 (alpha) or the version matching the cluster |
| Cluster URL | `localhost:26500` |
| Authentication | **Basic**, user `demo`, password `demo` |
| TLS | off (c8run listens in plaintext) |

**The credentials are required because item 2 of the review list turned authorization on.**
`camunda.security.authorizations.enabled: true` together with
`camunda.security.authentication.unprotected-api: false` means the gateway no longer serves
anonymous callers. The same change is why the worker fleet had to start sending basic
credentials - without them it does not error, it simply receives no jobs.

If the Modeler build offers no basic authentication for gRPC, there are two ways forward:

1. Deploy with `09_Tests_and_Tools/deploy-all.mjs` and use the Modeler only to view and edit
   models. This is the recommended one, and it keeps role-based access control in force.
2. Temporarily set `unprotected-api: true` in
   `c8run-8.10.0-alpha5/configuration/application.yaml` and restart. The Modeler connects
   again, but role separation stops being enforced, so the RBAC evidence has to be shown
   from `05_Test_Evidence/rbac/task-visibility.json`, which was recorded with it on.

## 4. Incidents you may see in Operate, and where they come from

Operate had 68 incidents: 44 from the acceptance runs on 28-29 September and 24 from the
test runs on 15 October. They are debris from runs in which user tasks were completed
through the API without the variables the following worker needs, not evidence that the
model is broken - a fresh instance that is left at its first user task produces none.

They come in two shapes, and both are the same known gap:

* `UNHANDLED_ERROR_EVENT` with codes such as `REFERRAL_DECISION_MISSING` or
  `INVALID_JOB_INPUT` - a worker rejects the job and throws a BPMN error, and the models
  declare **no error boundary events**, so nothing catches it and the instance stops.
* `EXTRACT_VALUE_ERROR` on a gateway such as `G_LetterOnTime` - the expression
  `letterDelayDays <= 7` evaluated to null because the variable was never written on that
  instance, and FEEL cannot compare null with a number.

To avoid the first while demonstrating: start instances **with the variables they need**
(`patientId` and `documentsComplete`, which is what `start-referral.mjs` publishes) rather
than starting an empty instance from Operate, and let the forms supply the rest. The second
disappears once every gateway's variable has a required field on the form that precedes it -
which is what `validate-form-controls.py` checks, and it currently reports 25 of 25
collected.

The durable fix for both is to give the service tasks error boundary events that route to a
handling path instead of leaving an uncaught error. That is a model change, and it is listed
in the review list's item 3 as still open.

## 5. Authorizations decide whether the worker fleet can do anything

This one costs a whole afternoon if it is not known, so it is written down.

The cluster configuration in `c8run-8.10.0-alpha5/configuration/application.yaml` carries two
switches that pull in opposite directions:

```yaml
camunda:
  security:
    authentication:
      method: BASIC
      unprotected-api: true      # the REST API answers without credentials
    authorizations:
      enabled: true              # role-based access is enforced
```

`authorizations.enabled: true` is what the role evidence needs: with it on, a user with no
group sees 0 tasks and a medical secretary sees 785. It is also what makes the **worker fleet
stop working**. The delivered workers use the Zeebe client 8.9 (`zeebe.version` in the worker
`pom.xml`) against a Camunda 8.10 cluster; when authorizations are enabled, its gRPC job
activation is refused, the client retries silently, and every worker sits idle while the
cluster looks healthy and the REST API keeps answering. The symptom is a process that parks on
the first service task for ever, with **no incident and no error message** — verified on
20 October 2026: 13 of 13 workers subscribed, one job waiting, nothing activated.

Measured on 20 October 2026, same cluster, same jar:

| authorizations.enabled | worker fleet | evidence |
| --- | --- | --- |
| `true` (the checked-in configuration) | subscribes, activates nothing; every service task parks | REST `POST /v2/jobs/activation` still returns the job, which is how the harness hides the problem |
| `false` (environment override below) | activates and completes immediately | `query-available-appointment-slots ... -> completed in 617 ms` |

So the cluster is started in one of two modes, and the two evidences are produced separately:

```powershell
# Mode A - role evidence (this is the checked-in configuration; nothing to set)
cd D:\app\Camunda\c8run-8.10.0-alpha5
.\c8run.exe start --disable-connectors
python 09_Tests_and_Tools\verify-rbac.py          # 10 groups, 0 vs 785, 0 failures

# Mode B - run the process end to end, including the worker fleet
$env:CAMUNDA_SECURITY_AUTHORIZATIONS_ENABLED = "false"
$env:CAMUNDA_SECURITY_AUTHENTICATION_UNPROTECTEDAPI = "true"   # both switches: see 5.2
.\c8run.exe start --disable-connectors
java -jar 04_Java_Worker/target/hospital-external-workers-1.0.0.jar
node 09_Tests_and_Tools/run-worker-demo.mjs        # or drive the Tasklist by hand
Remove-Item Env:\CAMUNDA_SECURITY_AUTHORIZATIONS_ENABLED, Env:\CAMUNDA_SECURITY_AUTHENTICATION_UNPROTECTEDAPI
```

Mode B changes no file: the overrides are environment variables, so `git status` stays clean and
the checked-in configuration still documents the role behaviour.

### 5.2 The gRPC gateway authenticates too, so two switches move together

`unprotected-api` is not only about the REST API. With it at `false`, the gRPC gateway on 26500 also
demands credentials, and the worker fleet sends none (`gateway.username` is empty in
`workers.properties`). Measured on 20 October 2026, same cluster, same jar:

| authorizations | unprotected-api | REST | worker fleet | symptom |
| --- | --- | --- | --- | --- |
| `true` (checked in) | `false` (checked in) | works with `demo:demo` | subscribes, activates nothing | role evidence is correct; every service task parks |
| `false` | `false` | works | `UNAUTHENTICATED: Expected authentication information at header with key [authorization], but found nothing` | the fleet logs a stack trace and still activates nothing |
| `false` | `true` | works | activates and completes jobs | the demo path: `T_QueryAvailableSlots` completed by the worker |

So the two modes are two pairs, not one switch:

```
role evidence    unprotected-api=false + authorizations=true     (the checked-in file, no override)
process demo     unprotected-api=true  + authorizations=false    (both overrides above)
```

Why the fleet cannot simply authenticate: the delivered client is Zeebe client 8.9 and it carries
basic credentials over gRPC in a form this 8.10 gateway does not accept. Rebuilding against
`zeebe.version` 8.10 and the current `CamundaClient` is the real fix and the first item of the next
release; until then the demo runs with the API open, which is the state the acceptance evidence was
produced in anyway.

`run-worker-demo.mjs` also needed a page limit. Its `findInstance` asked for process instances with no
`page`, the API answered with the **oldest** 100, and on a cluster that has been run more than a
hundred times the instance it had just started was never in that page - the scenario then failed with
`no PR_Operational_Merged instance was started (HTTP 200)` even though the instance existed. It now
asks for `sort: startDate DESC` with `page: 0..100`.

Two consequences that are worth stating in the demonstration rather than hiding:

* `run-acceptance.mjs` completes service-task jobs **itself** through the REST API
  (`POST /jobs/{key}/completion`). It therefore passes 18 of 18 with the worker fleet stopped, and
  a green acceptance run is not evidence that the fleet works. Only `run-worker-demo.mjs` and a
  hand-driven Tasklist require the fleet.
* A worker that rejects a job for a missing mandatory input throws a named BPMN error
  (`INVALID_JOB_INPUT`). None of the four models declares an error boundary event, so that error
  surfaces as an **incident** and the instance stays where it is. That is the limitation recorded
  in section 1.8 of the portfolio, demonstrated: start `PR_ReferringOrganisation` without
  `patientId` and it stops at `RO_ComposeReferral` with
  `rejected: missing mandatory input 'patientId'`.

One more thing about the start message. `Patient referral` is the message name of a start event in
**three** definitions - `PR_Operational_Merged`, `PR_Landscape` and `PR_ReferralToAuthorisation` -
so publishing it creates one instance in each. Two of them are strategic views and will never be
completed. Drive the operational model from its own start event, or expect three instances in
Operate.

### 5.1 `unprotected-api` has to be false for the role evidence

`camunda.security.authentication.unprotected-api` is the switch that decides whether the REST API
evaluates authorization at all. Measured on 20 October 2026, same cluster, only that key changed:

| `unprotected-api` | `norole.demo` (no role) | `secretary.demo` | verdict |
| --- | --- | --- | --- |
| `true` (what the file contained) | 1340 tasks | 1340 tasks | both roles see everything: `verify-rbac.py` exits 1 |
| `false` (checked in now) | 0 tasks | 1340 tasks | `RBAC in force - membership correct, enforcement active, inboxes routed` |

Two things follow. First, the role evidence only exists in the second state, so the file must keep
`unprotected-api: false`; the demo scripts keep working because every REST call carries `demo:demo`
basic credentials. Second, the absolute count in the second column is **not** an invariant: it is the
number of user tasks in the instance history, so it grows with every acceptance run (785 on
15 October, 1340 on 20 October). The number that does not move is the **0**. Quote the date
whenever the other one appears.

Evidence: `05_Test_Evidence/rbac/task-visibility.json` (the 15 October run quoted in the portfolio),
`task-visibility-2026-10-20.json` (the same checks re-run after the setting was corrected) and
`rbac-visibility-evidence.pdf` (the one-page summary those two numbers come from).
