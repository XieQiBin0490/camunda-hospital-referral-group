# Acceptance Test Plan

Operational model `O1_Operational_Merged` and the strategic models, Camunda 8 (self-managed, c8run), executed 2026-09-26T16:17:23.628Z.

**Result of the recorded run: 18 cases executed, 18 passed, 0 failed.**

Every scenario below is a case in that run. The scenario, its data, its expected outcome and its verdict are generated from the run record in `05_Test_Evidence/acceptance-run.json`, so the plan cannot drift from the evidence.


## 1. Test scenarios

| Case | Scenario | Process | Business rule exercised | Result |
| --- | --- | --- | --- | --- |
| TC-01 | Complete referral documentation is accepted for clinical review | `PR_Operational_Merged` | BR-01 Complete referral documentation is accepted for clinical review | PASS |
| TC-02 | Missing documentation triggers a request and a return path | `PR_Operational_Merged` | BR-02 Missing documentation triggers a request and a return path | PASS |
| TC-03 | Rejected referral closes with a notification | `PR_Operational_Merged` | BR-03 Rejected referral closes with a notification | PASS |
| TC-04 | Redirected referral is sent to another specialist service | `PR_Operational_Merged` | BR-04 Redirected referral is sent to another specialist service | PASS |
| TC-05 | No suitable appointment slot is escalated to the pathway coordinator | `PR_Operational_Merged` | BR-05 No suitable appointment slot is escalated to the pathway coordinator | PASS |
| TC-06 | Appointment within 14 days requires a telephone call | `PR_Operational_Merged` | BR-06 Appointment within 14 days requires a telephone call | PASS |
| TC-07 | Appointment more than 14 days away skips the telephone call | `PR_Operational_Merged` | BR-07 Appointment more than 14 days away skips the telephone call | PASS |
| TC-08 | Unsuccessful contact is recorded and a further attempt is made | `PR_Operational_Merged` | BR-08 Unsuccessful contact is recorded and a further attempt is made | PASS |
| TC-09 | Patient refuses consent and the pathway closes | `PR_Operational_Merged` | BR-09 Patient refuses consent and the pathway closes | PASS |
| TC-10 | Unauthorised treatment booking request is returned to the clinical team | `PR_Operational_Merged` | BR-10 Unauthorised treatment booking request is returned to the clinical team | PASS |
| TC-11 | Unavailable external capacity leaves the booking pending and retries | `PR_Operational_Merged` | BR-11 Unavailable external capacity leaves the booking pending and retries | PASS |
| TC-12 | Unapproved funding raises a funding approval request | `PR_Operational_Merged` | BR-12 Unapproved funding raises a funding approval request | PASS |
| TC-13 | Happy path: referral accepted and treatment schedule confirmed | `PR_Operational_Merged` | BR-13 Happy path: referral accepted and treatment schedule confirmed | PASS |
| TC-14 | Advance payment confirmed and recorded | `PR_Operational_Merged` | BR-14 Advance payment confirmed and recorded | PASS |
| TC-15 | Declined payment is handled without creating a duplicate booking | `PR_Operational_Merged` | BR-15 Declined payment is handled without creating a duplicate booking | PASS |
| TC-16 | Payment without a returned confirmation is investigated, not re-requested | `PR_Operational_Merged` | BR-16 Payment without a returned confirmation is investigated, not re-requested | PASS |
| TC-17 | Urgent treatment proceeds without confirmed payment and is referred to Finance | `PR_Operational_Merged` | BR-17 Urgent treatment proceeds without confirmed payment and is referred to Finance | PASS |
| TC-18 | No advance payment required: no payment task is created | `PR_Operational_Merged` | BR-18 No advance payment required: no payment task is created | PASS |

Each scenario is a **complete path** through the model, not a single step: the engine drives the instance from the start event to an end state, and the path taken is asserted against the expected outcome in section 5.


## 2. Preconditions

Common to every scenario:

1. A Camunda 8 cluster is running and reachable at `http://127.0.0.1:8080/v2`.
2. The four models and the 68 Camunda Forms are deployed **together**, one deployment per model, because every form reference carries `binding="deployment"` (`node 09_Tests_and_Tools/deploy-all.mjs`).
3. Seven process definitions are live: `PR_Operational_Merged`, `PR_Landscape`, `PR_ReferralToAuthorisation`, `PR_TreatmentToAftercare`, `PR_EnquiryHandling`, `PR_ManagementReporting`, `PR_ReferringOrganisation`. `PR_ReferringOrganisation` is the collaborating referring-organisation process inside the operational collaboration; it is started only when that pool sends a referral.
4. The external worker service is running, so the automated activities are done: `04_Java_Worker/run-workers.ps1` reports `13 workers subscribed and polling`.
5. No earlier instance of the same scenario is still active under the same `patientId`; each case uses a unique one.
6. Fault injection is set per scenario through `workers.properties` or the environment (`HPAS_FAILURE_MODE`, `HPAS_FAILURE_PREFIX`), never by editing code.

Scenario-specific differences are the start variables in section 3.


## 3. Test data

The data is supplied in two places: the **start variables** that open the instance, and the **decisions** the human role makes at each user task. Everything else is derived by the model or written by the workers.

| Case | Start variables | Human decisions at the user tasks |
| --- | --- | --- |
| TC-01 | `patientId=P-TC-01`, `documentsComplete=True` | (none) |
| TC-02 | `patientId=P-TC-02`, `documentsComplete=False` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-03 | `patientId=P-TC-03`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=rejected` |
| TC-04 | `patientId=P-TC-04`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=redirected` |
| TC-05 | `patientId=P-TC-05`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-06 | `patientId=P-TC-06`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=True`, `contactSuccessful=True`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-07 | `patientId=P-TC-07`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-08 | `patientId=P-TC-08`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=True`, `contactSuccessful=True`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-09 | `patientId=P-TC-09`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=False` |
| TC-10 | `patientId=P-TC-10`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-11 | `patientId=P-TC-11`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-12 | `patientId=P-TC-12`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-13 | `patientId=P-TC-13`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |
| TC-14 | `patientId=P-TC-14`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=True`, `paymentStatus=confirmed` |
| TC-15 | `patientId=P-TC-15`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=True`, `paymentStatus=confirmed` |
| TC-16 | `patientId=P-TC-16`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=True`, `paymentStatus=no response` |
| TC-17 | `patientId=P-TC-17`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=True`, `paymentStatus=urgent clinical need` |
| TC-18 | `patientId=P-TC-18`, `documentsComplete=True` | `documentsComplete=True`, `referralDecision=accepted`, `referralUrgency=routine`, `suitableSlotFound=True`, `appointmentWithin14Days=False`, `consentGiven=True`, `requestAuthorised=True`, `treatmentCapacityConfirmed=True`, `fundingApproved=True`, `advancePaymentRequired=False` |

### Which gateway each decision drives

| Decision variable | Gateway in the model |
| --- | --- |
| `documentsComplete` | G_DocumentsComplete - "All expected supporting documents available?" |
| `referralDecision` | G_ReferralDecision - "Referral decision?" |
| `referralUrgency` | G_UrgentReferral - "Urgent referral requiring expedited booking?" |
| `suitableSlotFound` | G_SlotsAvailable - "Suitable appointment available within the requested period?" |
| `appointmentWithin14Days` | G_WithinFourteenDays - "Appointment due within the next 14 days?" |
| `contactSuccessful` | G_ContactSuccessful - "Patient confirmed the appointment?" |
| `consentGiven` | G_PatientConsent - "Patient consents to proceed with treatment?" |
| `requestAuthorised` | G_RequestAuthorised - "Request completed and authorised by an authorised clinical professional?" |
| `treatmentCapacityConfirmed` | G_CapacityConfirmed - "External treatment capacity confirmed?" |
| `fundingApproved` | G_FundingApproved - "Funding approved or no payment required?" |
| `advancePaymentRequired` | G_AdvancePaymentRequired - "Advance payment required before the appointment is confirmed?" |
| `paymentStatus` | G_PaymentOutcome - "Payment outcome returned by the payment service?" |

## 4. Actions

For each scenario the same sequence is performed, by `09_Tests_and_Tools/run-acceptance.mjs`:

1. Publish the start message (or create the instance directly where the process has a plain start event) with the case's start variables.
2. Wait for the instance to appear and read its state.
3. Whenever a user task is created, complete it through the API with the decisions listed for that case, in the order the instance asks for them.
4. Let the worker service finish every automated activity; if a scenario exercises a failure path, set the fault for that activity first.
5. Repeat steps 3 and 4 until the instance reaches an end state or the case times out.
6. Record the elements reached with their occurrence counts, the end state, the variables, and any incident.
7. Compare the record with the expected outcome and mark the case PASS or FAIL.

## 5. Expected outcomes


**TC-01 — Complete referral documentation is accepted for clinical review**  

Process: `PR_Operational_Merged`
* must reach: `T_ClinicalReviewReferral`, `T_RecordReferralDecision`
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-02 — Missing documentation triggers a request and a return path**  

Process: `PR_Operational_Merged`
* must reach: `T_RequestMissingDocuments`, `T_ClinicalReviewReferral`
* must reach `T_CheckReferralDocuments` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-03 — Rejected referral closes with a notification**  

Process: `PR_Operational_Merged`
* must reach: `T_NotifyReferralOutcome`
* must **not** reach: `T_ForwardAcceptedReferral`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-04 — Redirected referral is sent to another specialist service**  

Process: `PR_Operational_Merged`
* must reach: `T_RedirectReferral`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-05 — No suitable appointment slot is escalated to the pathway coordinator**  

Process: `PR_Operational_Merged`
* must reach: `T_ResolveCapacity`, `T_SelectAndBookSlot`
* must reach `T_QueryAvailableSlots` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-06 — Appointment within 14 days requires a telephone call**  

Process: `PR_Operational_Merged`
* must reach: `T_TelephonePatient`, `T_RecordContactAttempt`
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-07 — Appointment more than 14 days away skips the telephone call**  

Process: `PR_Operational_Merged`
* must reach: `T_NewPatientConsultation`
* must **not** reach: `T_TelephonePatient`
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-08 — Unsuccessful contact is recorded and a further attempt is made**  

Process: `PR_Operational_Merged`
* must reach: `T_TelephonePatient`
* must reach `T_TelephonePatient` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-09 — Patient refuses consent and the pathway closes**  

Process: `PR_Operational_Merged`
* must reach: `T_AdviseNoTreatment`
* must **not** reach: `T_CreateTreatmentBookingRequest`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-10 — Unauthorised treatment booking request is returned to the clinical team**  

Process: `PR_Operational_Merged`
* must reach: `T_ReturnUnauthorisedRequest`
* must reach `T_CreateTreatmentBookingRequest` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-11 — Unavailable external capacity leaves the booking pending and retries**  

Process: `PR_Operational_Merged`
* must reach: `T_KeepPending`
* must reach `T_RequestTreatmentCapacity` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-12 — Unapproved funding raises a funding approval request**  

Process: `PR_Operational_Merged`
* must reach: `T_RequestFundingApproval`, `T_RecordFundingApproval`
* must reach `T_DetermineFundingRoute` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-13 — Happy path: referral accepted and treatment schedule confirmed**  

Process: `PR_Operational_Merged`
* must reach: `T_ConfirmTreatmentSchedule`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-14 — Advance payment confirmed and recorded**  

Process: `PR_Operational_Merged`
* must reach: `T_SendSecurePaymentRequest`, `T_RecordPayment`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-15 — Declined payment is handled without creating a duplicate booking**  

Process: `PR_Operational_Merged`
* must reach: `T_HandlePaymentFailure`, `T_RecordPayment`
* must reach `T_SendSecurePaymentRequest` at least **2 times** (the loop is the point of the case)
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-16 — Payment without a returned confirmation is investigated, not re-requested**  

Process: `PR_Operational_Merged`
* must reach: `T_MarkForInvestigation`, `T_ResolveTransaction`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-17 — Urgent treatment proceeds without confirmed payment and is referred to Finance**  

Process: `PR_Operational_Merged`
* must reach: `T_AuthoriseUrgentTreatment`, `T_ReferUnconfirmedPayment`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

**TC-18 — No advance payment required: no payment task is created**  

Process: `PR_Operational_Merged`
* must reach: `T_ConfirmTreatmentSchedule`
* must **not** reach: `T_SendSecurePaymentRequest`
* must end in state **COMPLETED**
* actual: end state **COMPLETED**, 0 incident(s) — **PASS**

## 6. Pass / Fail conditions

A case passes only when **all** of the following hold:

1. **Every** element in `must reach` appears in the instance history.
2. **No** element in `must not reach` appears — this is what makes the negative branches testable, not just the happy path.
3. Every `minOccurrences` count is met, which is how a loop is proved to have looped.
4. The end state equals the expected end state.
5. **Zero incidents** were raised. An unhandled-error incident means a worker rejected a job or a variable was missing, so the path taken is not evidence of anything.
6. The run completes within the case timeout.

A case fails on the first of these that does not hold, and the failing condition is named in `problems`.


**Recorded result: 18 of 18 cases passed, 0 failed.**


## 7. Environment and how to reproduce

| Item | Value |
| --- | --- |
| Execution | `node 09_Tests_and_Tools/run-acceptance.mjs` |
| Record | `05_Test_Evidence/acceptance-run.json` |
| Log | `05_Test_Evidence/acceptance-run.log` |
| Models executed | PR_EnquiryHandling, PR_Landscape, PR_ManagementReporting, PR_Operational_Merged, PR_ReferralToAuthorisation, PR_TreatmentToAftercare |
| One-command check of everything | `09_Tests_and_Tools/verify-all.ps1` (9 steps, all pass) |