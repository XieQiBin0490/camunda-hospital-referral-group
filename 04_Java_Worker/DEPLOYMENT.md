# Deployment and configuration

## What you need

| | |
| --- | --- |
| JDK | 17 or later (built and run here on JDK 22) |
| Maven | 3.8 or later. **A copy is already in the team workspace** at `workers\.tools\apache-maven-3.9.9` - add its `bin` folder to `PATH` and nothing needs downloading |
| Engine | Camunda 8 with the Zeebe gRPC gateway reachable. Verified against **Camunda 8 Run 8.10.0-alpha5**, gateway `localhost:26500` |
| Client | `io.camunda:zeebe-client-java` **8.9.0**, pinned in `pom.xml` |

If you would rather not put Maven on `PATH`, either call it by full path
(`workers\.tools\apache-maven-3.9.9\bin\mvn.cmd`) or build once and keep the jar in
`prebuilt\`: `run-workers.ps1` and `run-worker-scenarios.ps1` both fall back to
`prebuilt\hospital-external-workers-1.0.0.jar` when `target\` is empty.

The client version is pinned deliberately. The 8.9.0 client logs

```
ZeebeClient is deprecated and will be removed in version 8.10.
Please migrate to io.camunda.client.CamundaClient.
```

but it works against the 8.10.0-alpha5 gateway, and it is the version this fleet
has been run against end to end. Moving to the unified `CamundaClient` is a
mechanical change to `WorkersApplication` and `AbstractWorker`; it was not made
here because a client that has been proven against the delivered models is worth
more than a client that matches the server's major version.

## Start the engine

```bash
cd camunda8-getting-started-bundle-8.10.0-alpha5-windows-x86_64/c8run-8.10.0-alpha5
./c8run.exe start          # Windows;  ./c8run start on Linux and macOS
```

Useful endpoints once it is up:

| | |
| --- | --- |
| Operate | http://localhost:8080/operate (`demo` / `demo`) |
| Tasklist | http://localhost:8080/tasklist |
| Orchestration Cluster API | http://localhost:8080/v2/ |
| Zeebe gRPC gateway | localhost:26500 |

## Deploy the models and the forms

The workers only subscribe to job types; they do not deploy anything. Deploy the
models and the 68 forms together, because a user task whose form is missing
raises `FORM_NOT_FOUND` the moment the instance reaches it:

```bash
node 09_Tests_and_Tools/deploy-all.mjs
```

## Build and start the fleet

```bash
mvn -f 04_Java_Worker/pom.xml clean package
java --enable-native-access=ALL-UNNAMED -jar workers/target/hospital-external-workers-1.0.0.jar
```

or, with the convenience wrapper:

```powershell
.\workers\run-workers.ps1                 # Windows
REBUILD=1 ./workers/run-workers.sh        # Linux / macOS
```

A healthy start looks like this:

```
hospital external workers starting: gateway=127.0.0.1:26500 plaintext=true maxJobsActive=8 ...
job type coverage verified: 13 of 13 declared types have a subscriber
subscribed request-missing-documentation as 'hospital-external-workers:request-missing-documentation'
...
13 workers subscribed and polling 127.0.0.1:26500
```

If it stops at `no worker subscribes to declared job type(s)`, the fleet and the
models disagree about a job type - fix that before anything else, because the
process will otherwise park silently on that activity.

## Configuration reference

Configuration is read in this order, each layer overriding the one before:

1. built-in defaults,
2. `workers.properties` on the classpath (`src/main/resources/`),
3. `workers.properties` in the working directory,
4. environment variables named `HPAS_<KEY>` - upper case, dots to underscores.

| Key | Default | Meaning |
| --- | --- | --- |
| `gateway.address` | `127.0.0.1:26500` | gRPC gateway. Camunda SaaS: `<cluster-id>.<region>.zeebe.camunda.io:443` |
| `gateway.plaintext` | `true` | `true` for c8run and docker-compose; `false` for SaaS and anything behind TLS |
| `worker.maxJobsActive` | `8` | jobs one worker may hold at once |
| `worker.timeoutSeconds` | `30` | how long a job stays locked before the engine offers it again |
| `worker.pollIntervalMillis` | `200` | how often the workers poll |
| `worker.threads` | `4` | execution threads shared by the fleet |
| `failure.mode` | `off` | `off`, `rules` or `all` - see below |
| `failure.prefix` | *(empty)* | job types that fail once when `failure.mode=rules` |

Environment examples:

```bash
HPAS_GATEWAY_ADDRESS=my-cluster.example.zeebe.camunda.io:443 \
HPAS_GATEWAY_PLAINTEXT=false \
java -jar workers/target/hospital-external-workers-1.0.0.jar
```

## Failure injection

The failure paths are demonstrable rather than described.

| Variable | Effect |
| --- | --- |
| `HPAS_FAILURE_MODE=rules` + `HPAS_FAILURE_PREFIX=<job-type>[,<job-type>]` | each named job type fails **once**; the engine's retry policy recovers it |
| `HPAS_FAILURE_MODE=all` | every automated activity fails once |
| `HPAS_FAILURE_PREFIX=<job-type>:<ERROR_CODE>` | that job type throws the named BPMN error instead of failing |

Business outcomes are forced separately, because they are not faults:

| Variable | Effect |
| --- | --- |
| `HPAS_PAYMENT_OUTCOME` | `CONFIRMED` (default), `DECLINED`, `NO_RESPONSE`, `URGENT_CLINICAL_NEED` |
| `HPAS_PAYMENT_OUTCOMEONCE=false` | apply the forced payment outcome to every attempt, not just the first |
| `HPAS_CAPACITY_UNAVAILABLEONCE=true` | refuse capacity on the first attempt so the pending-and-retry path runs |
| `HPAS_CAPACITY_UNAVAILABLE=true` | refuse capacity on every attempt |
| `HPAS_CAPACITY_BLOCKEDRESOURCES=MRI,PET-CT` | name specific resources as unavailable |
| `HPAS_SCHEDULING_NOSLOTS=true` | the scheduling service answers with no suitable slot |
| `HPAS_SCHEDULING_UNAVAILABLE=true` | the scheduling service does not answer (retryable) |
| `HPAS_CORRESPONDENCE_UNAVAILABLE=true` | the correspondence service rejects the dispatch (retryable) |
| `HPAS_REFUND_REJECTED=true` | the provider rejects the refund |

A forced payment decline applies to the **first** transaction in an episode by
default, so "declined, then the permitted retry succeeds" is the behaviour you
see. Set `HPAS_PAYMENT_OUTCOMEONCE=false` to make it apply to every attempt.

## Running the demonstration

```bash
node 09_Tests_and_Tools/run-worker-demo.mjs happy                  # the fleet must be pre-configured
powershell -File 09_Tests_and_Tools/run-worker-scenarios.ps1       # restarts the fleet per scenario and runs all six
```

`run-worker-scenarios.ps1` is the one to use for a demonstration: it stops any
running fleet, starts it with the scenario's environment, waits for
`workers subscribed and polling`, runs the case, and writes the evidence to
`05_Test_Evidence/worker-run/`. All six scenarios end `COMPLETED` with no incidents.

The seventh scenario, `reporting`, is excluded from the suite on purpose: it
targets `PR_ManagementReporting`, whose only start event is a monthly timer
(`R/P1M`). The engine refuses to create an instance of a process that has no none
start event (`409 Conflict`), so `generate-management-reports` cannot be executed
on demand. It is verified by the start-up coverage check. To drive it, either
wait for the timer or add a none start event to that process.

The engine does expose clock control (`PUT /v2/clock`, with
`POST /v2/clock/reset` working against 8.10.0-alpha5), which is the obvious way
to fire that timer early. The request body for the pin/offset operations was not
accepted in any of the documented shapes
(`Request property [type] cannot be parsed`), so it is recorded here as the
unresolved route rather than presented as a working one.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| The instance sits on a service task forever | no worker is subscribed to that job type: check the coverage line at start-up, then check `gateway.address` |
| `io.grpc.StatusRuntimeException: UNAVAILABLE` | the engine is not running, or the gateway port is wrong. `GET http://127.0.0.1:8080/v2/topology` should answer 200 |
| TLS handshake failures | the gateway needs `HPAS_GATEWAY_PLAINTEXT=false` and a credentials provider (SaaS) |
| `FORM_NOT_FOUND` incident on the first user task | the forms were not deployed - run `node 09_Tests_and_Tools/deploy-all.mjs` |
| A worker completes a job but the gateway branches wrongly | the worker is writing a variable the gateway does not read, or not writing one it does. Compare against the table in `README.md`; the three gating job types are the ones to check first |
| Duplicate-looking tasks after a restart | expected: the in-memory store does not survive a restart, so duplicate detection starts from empty. This is stated in the acceptance evaluation as a limitation |

## What is not production-ready

Stated here as well as in the evaluation, because a deployment guide that hides
this is worse than useless:

* The external providers are **simulated**. No real scheduling, correspondence,
  clinical or payment service is called.
* `HospitalStore` and `OperationsLog` are **in-memory**. Nothing survives a
  restart, so duplicate-payment detection and the audit trail reset with it.
* There is **no authentication** on the gateway; c8run runs plaintext without
  credentials, and this fleet follows it.
* There are **no error boundary events** on the service tasks, so a thrown BPMN
  error surfaces as an incident instead of being caught. See the note in
  `README.md`.
