# Hospital external workers

Java job workers for the hospital process definitions delivered in
`02_BPMN_Models/`. One worker per job type the models declare, so every
automated activity in the four `.bpmn` files has a subscriber and nothing parks
waiting for a worker that does not exist.

```
workers/
  pom.xml                          Maven build (shaded jar, Java 17+)
  run-workers.ps1  run-workers.sh  build-if-needed then run
  src/main/java/uk/ac/uwe/hospital/
    WorkersApplication.java        registers the fleet; refuses to start on a coverage gap
    AbstractWorker.java            the one place that decides how a failure reaches the engine
    JobContext.java                validated reads, never-invent writes
    WorkerConfig.java              env-overridable configuration
    BpmnErrorException.java        business error -> BPMN error -> boundary event
    TransientJobException.java     worth retrying -> fail the job
    ValidationException.java       bad input -> named BPMN error
    support/ExternalServices.java  the simulated providers
    support/FailureInjection.java  deterministic fault injection
    support/HospitalStore.java     in-memory business records + episode correlation
    support/OperationsLog.java     append-only audit of automated decisions
    support/Ids.java               reference generators
    tasks/*Worker.java             the thirteen workers
  src/main/resources/
    workers.properties             configuration template
    logback.xml
```

## The thirteen workers

The three job types in **bold** own a variable that a gateway in the model reads.
That is the contract that matters: if one of them fails to write it, the instance
takes the wrong branch or raises a FEEL null.

| Job type | Model element(s) | Reads | Writes |
| --- | --- | --- | --- |
| `request-missing-documentation` | O1 `T_RequestMissingDocuments`; S1 `T_RequestDocs`; S2 `T_RequestMissingDocs` | `patientId`, `referringOrganisation`, `missingDocuments` | `missingDocumentsRequested`, `missingDocumentList`, `documentRequestReference` |
| `send-referral-outcome` | O1 `T_NotifyReferralOutcome`; S1 `T_NotifyOutcome`; S2 `T_NotifyNotAccepted` | `patientId`, `referralDecision` | `outcomeNotified`, `outcomeLetterReference` |
| `redirect-referral` | O1 `T_RedirectReferral`; S2 `T_RedirectReferral` | `patientId`, `redirectDestination` | `redirectSent`, `redirectReference` |
| **`query-available-appointment-slots`** | O1 `T_QueryAvailableSlots`; S2 `T_QuerySlots` | `patientId`, `requestedSpeciality`, `referralUrgency`, `preferredTimeframeDays` | **`suitableSlotFound`**, `availableSlots`, `schedulingReference` |
| `send-appointment-confirmation-letter` | O1 and S2 `T_SendAppointmentLetter` | `patientId`, `appointmentReference`, `communicationPreference` | `appointmentLetterSent`, `appointmentLetterReference` |
| **`request-treatment-capacity`** | O1 `T_RequestTreatmentCapacity`; S3 `T_RequestTreatmentCapacity` | `patientId`, `treatmentCode`, `treatmentCycles`, `requiredResource` | **`treatmentCapacityConfirmed`**, `capacityReference`, `capacityAttemptCount`, `duplicateAppointmentCreated` |
| **`request-secure-payment`** | O1 `T_SendSecurePaymentRequest`; S3 `T_RequestSecurePayment` | `patientId`, `chargeAmount`, `currency`, `fundingApproved` | **`paymentStatus`**, `paymentReference`, `paymentAmount`, `cardDataStored` |
| `distribute-clinical-correspondence` | S1 `T_Correspondence`; S3 `T_DistributeClinicLetter` | `patientId`, `letterApproved`, `suspectedClinicalError` | `correspondenceSent`, `correspondenceReference` |
| `request-blood-test` | S3 `T_RequestBloodTest` | `patientId`, `cycleReference` | `bloodTestRequested`, `bloodTestReference`, `bloodTestDueDate` |
| `request-refund` | S3 `T_RequestRefund` | `patientId`, `refundAmount`, `refundAuthorised`, `paymentReference` | `refundStatus`, `refundReference` |
| `generate-management-reports` | S3 `T_GenerateManagementReports` | `reportPeriod` | `reportGenerated`, `reportReference`, `reportFigures` |
| `referring-org-submit-patient-referral` | O1 `RO_ComposeReferral` (referring organisation pool) | `patientId`, `referringOrganisation` | `referralReference`, `referralStatus = "composed"`, `referralComposedAt` |
| `referring-org-publish-patient-referral` | O1 `RO_SendReferral` - the **message throw event** in the referring organisation pool | `referralReference`, `patientId`, `referringOrganisation` | `referralStatus = "sent"`, `referralMessageKey`, `referralSentAt` |

### The cross-pool message exchange

The last two rows are different in kind from the other eleven: they belong to the
**referring organisation's** pool (`PR_ReferringOrganisation` in
`O1_Operational_Merged.bpmn`), not to the hospital. They are what makes the
collaboration executable rather than drawn.

In Camunda 8 a message flow on the diagram is documentation; nothing crosses a
pool boundary unless a job worker publishes a message. A message intermediate
throw event is itself executed as a job, so `RO_SendReferral` needs the
`referring-org-publish-patient-referral` worker to do the publishing. That worker
publishes `Patient referral` with `correlationKey = referralReference`, which
starts a `PR_Operational_Merged` instance at its message start event. The
hospital answers from `T_NotifyReferralOutcome` (`send-referral-outcome`), which
publishes `Referral outcome notification` on the same correlation key, and the
referring pool's message catch event `RO_AwaitOutcome` completes the round trip.

`support/MessagePublisher.java` is the shared publishing helper. It never throws
and never sends a blank correlation key: a pool that is not deployed must not
turn a working job into an incident, and an empty key would create a duplicate
instance instead of correlating to the waiting one. Every publish is recorded on
the instance (`referralMessageKey`, `outcomeMessageKey`) so the exchange can be
evidenced from the instance rather than from the log.

## Failures: the decision that matters

Every worker returns through one place, `AbstractWorker.onJob`, so the fleet
cannot disagree with itself about what a failure means.

| Situation | What the worker does | Why |
| --- | --- | --- |
| Provider **declines** (payment declined, no capacity, no slot) | writes the outcome variable and completes | These are business outcomes the model already branches on: no capacity is the pending-and-retry path REQ-16 asks for, a decline is the further-attempt path REQ-22 asks for |
| Provider **does not answer** | `TransientJobException` -> fail the job with one fewer retry | "no capacity" and "no answer" are different facts; reporting a network fault as no capacity sends a patient to escalation for the wrong reason |
| **Invalid input** (a mandatory variable is missing or malformed) | `ValidationException` -> BPMN error `INVALID_JOB_INPUT` | A defect in the data or the form, not an outage. It should be visible, not retried |
| Injected **business error** | `BpmnErrorException` with a named code -> BPMN error | Demonstrable failure handling; the code is what a boundary event catches |
| Anything **unexpected** | fail with no retries left -> incident | An incident is the correct signal for a defect somebody must read |

> **Known gap, stated rather than hidden.** The four delivered models declare no
> `bpmn:error` definitions and carry no error boundary events (only S3 has two
> timer boundaries), so a thrown BPMN error has nothing to catch it and surfaces
> as an incident. Business failures are therefore handled through the outcome
> variables and the branches the models already have, which is why the three
> gating workers own their variables so carefully. Adding named error codes with
> boundary events on the service tasks is the next modelling step, not something
> the worker layer can fix on its own.

## Requirements the workers carry

| Requirement | Where it is honoured |
| --- | --- |
| REQ-16 unanswered external service leaves the booking pending and records retries | `RequestTreatmentCapacityWorker` writes `treatmentCapacityConfirmed = false` with an attempt count and a next-attempt date; `duplicateAppointmentCreated` stays `false` |
| REQ-20 the provider returns status, reference, date and amount | `RequestSecurePaymentWorker` writes exactly those four facts |
| REQ-21 complete card data must never be stored | The worker never reads a card field, never writes one, and discards card-like keys before completion. Verified against the instance, not the code: the acceptance run asserts no card-shaped variable exists |
| REQ-22 a declined payment permits a further attempt without a duplicate charge | The worker checks the episode for an existing transaction of the same amount before sending anything |
| REQ-24 urgent treatment may proceed without confirmed payment | `paymentStatus = "urgent clinical need"` is carried through to the gateway rather than forced to a yes/no |
| REQ-37 audit records identify actor, date, time and action | Every completion, retry and rejection is appended to `OperationsLog` with the worker name, instant, action and episode. The log exposes no update or delete. Persistence and access control are still missing, and the evaluation says so |
| REQ-44 an auditable relationship across referral, treatment, appointment and payment | Every record is filed under one `episodeId`; the reporting worker aggregates it. A full correlation view still does not exist |

## Build and run

```bash
# build (Java 17 or later)
mvn -f 04_Java_Worker/pom.xml clean package          # or: .\run-workers.ps1 / ./run-workers.sh

# run against a local Camunda 8 Run cluster (plaintext gRPC on 127.0.0.1:26500)
java --enable-native-access=ALL-UNNAMED -jar 04_Java_Worker/target/hospital-external-workers-1.0.0.jar
```

The fleet prints its subscriptions and refuses to start if a declared job type
has no subscriber:

```
job type coverage verified: 13 of 13 declared types have a subscriber
13 workers subscribed and polling 127.0.0.1:26500
```

## Tests

```bash
mvn -f 04_Java_Worker/pom.xml test        # 41 tests; no engine and no network needed
```

| Suite | Tests | What it pins down |
| --- | --- | --- |
| `WorkerContractTest` | 16 | one test per worker, and the three gating workers hardest: that `suitableSlotFound`, `treatmentCapacityConfirmed` and `paymentStatus` really are written, with the values the gateways test. Also that no card-shaped variable reaches the process, that a second payment of the same amount is suppressed rather than sent, and that the blood-test worker does **not** decide fitness |
| `ExternalServicesTest` | 10 | provider outcomes, and the distinction the design rests on: a provider that answers "no" is a business outcome, a provider that does not answer is a retry. Also that a forced decline applies to the first attempt only, so the retry REQ-22 requires can succeed |
| `JobContextTest` | 8 | a missing or malformed variable is rejected **by name**. A FEEL null on a gateway takes a branch nobody chose, so it fails loudly instead |
| `SupportTest` | 7 | episode correlation, duplicate-payment detection, attempt counting, and that the audit log carries actor, time and action (REQ-37) with no update or delete |

These are the tests that earn their keep: a model review and a lint run both pass
happily on a worker that writes the wrong variable name. The same contract is
then re-checked against the live engine by the scenario suite below.

## Proven against the running engine

`09_Tests_and_Tools/run-worker-demo.mjs` plays **only the human roles** - it completes user
tasks and nothing else - so every service task and send task must be completed by
a running worker. If the fleet is not up, the case hangs and the run fails. All
six scenarios end `COMPLETED` with no incidents:

| Scenario | What it proves | Instance |
| --- | --- | --- |
| `happy` | the workers drive the whole pathway; `suitableSlotFound`, `treatmentCapacityConfirmed` and `paymentStatus` all set | 2251799813729686 |
| `capacity-unavailable` | the pending-and-retry path: capacity refused on attempt 1, `T_KeepPending` reached, confirmed on attempt 2, no duplicate booking | 2251799813729956 |
| `payment-declined` | the decline is handled, a further attempt is permitted and succeeds; no card data reaches the process | 2251799813730254 |
| `transient-retry` | an injected provider failure is retried by the engine and recovered, not escalated | 2251799813730539 |
| `aftercare-cycles` | two treatment cycles, then the clinic letter, then a cancellation: exercises `request-blood-test`, `distribute-clinical-correspondence` and `request-refund`, and reaches `E_PathwayReviewed` | 2251799813730803 |
| `enquiry` | `PR_EnquiryHandling` runs to `E_EnquiryClosed` | 2251799813731069 |

The last two matter beyond the workers: the acceptance evaluation lists
`PR_EnquiryHandling` and `PR_ManagementReporting` as *deployed but not driven*,
and the aftercare and enquiry scenarios now drive the first two of those three
processes end to end, so that limitation is partly closed rather than only
stated.

**Coverage: 10 of the 11 job types have been executed against the engine.**
`generate-management-reports` is the exception, and the reason is structural
rather than an omission: it is bound only inside `PR_ManagementReporting`, whose
sole start event is a monthly timer (`R/P1M`). A process with no none start event
cannot be created on demand - the API answers `409 Conflict` - so there is
nothing to subscribe to until the timer fires. It is verified by the start-up
coverage check instead, and the attempt and its reason are recorded in
`09_Tests_and_Tools/run-worker-demo.mjs` (scenario `reporting`, marked `skip`). Driving it
needs either a month of patience or a none start event on that process.

```bash
node 09_Tests_and_Tools/run-worker-demo.mjs happy      # one scenario
node 09_Tests_and_Tools/run-worker-demo.mjs all        # all six (restart the fleet per scenario)
powershell -File 09_Tests_and_Tools/run-worker-scenarios.ps1   # does the restarts for you
```

Logs and per-instance evidence are written to `05_Test_Evidence/worker-run/`. The
`workers-<scenario>.log` files are the evidence that a path was taken rather than
described: they contain lines such as `no capacity on attempt 1` followed by
`capacity confirmed on attempt 2`, and `provider declined` followed by
`a further attempt is permitted`.

## Configuration

See [DEPLOYMENT.md](DEPLOYMENT.md). Every key has a default that works against a
local Camunda 8 Run cluster, so nothing has to be configured to run it.
