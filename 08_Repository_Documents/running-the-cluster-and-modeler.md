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
