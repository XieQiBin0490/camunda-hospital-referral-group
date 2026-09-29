# Model inventory

Generated from the model specifications in `models/`. Every model is a single
BPMN 2.0 collaboration targeted at **Camunda 8 (Zeebe) 8.10**, validated with the
Camunda Modeler lint engine (`@camunda/linting` 3.57.0).

## O1_Operational_Merged

* File: `02_BPMN_Models/O1_Operational_Merged.bpmn`
* Collaboration: O1 | Operational model: merged patient referral, appointment and treatment payment process
* Execution platform: Camunda Cloud 8.10.0
* White-box participants (2): Specialist Hospital Service (Hospital Patient Administration System); Referring Organisation (GP or another hospital)
* Black-box participants (7): Patient / Authorised Representative (upstream); External Scheduling Service (external service); External Correspondence Service (external service); Other Specialist Service (external service); External Clinical Services (treatment, laboratory, imaging) (external service); Funding Organisation / Insurer (external service); External Payment Service Provider (external service)

### Process `PR_Operational_Merged` — Referral, appointment, treatment authorisation and payment

Lanes (8): Medical Secretaries | Consultant / Clinical Team | Outpatient Bookings Team | Call Handling Team | Treatment & Chemotherapy Bookings Team | Finance Team | Clinical Nurse Specialist Team | Patient Pathway Coordinators

| Lane | Type | Name | ID | Form / job type |
| --- | --- | --- | --- | --- |
| Medical Secretaries | startEvent | Patient referral received | `E_ReferralReceived` |  |
| Medical Secretaries | startEvent | Referral received (manual start) | `E_ReferralReceivedManual` |  |
| Medical Secretaries | userTask | Receive and register the referral | `T_ReceiveReferral` | form form-receive-referral |
| Medical Secretaries | userTask | Check referral documentation completeness | `T_CheckReferralDocuments` | form form-check-referral-documents |
| Medical Secretaries | exclusiveGateway | All expected supporting documents available? | `G_DocumentsComplete` |  |
| Medical Secretaries | sendTask | Request missing documentation from the referring organisation | `T_RequestMissingDocuments` | job request-missing-documentation |
| Medical Secretaries | sendTask | Notify the referring organisation of the referral decision | `T_NotifyReferralOutcome` | job send-referral-outcome |
| Medical Secretaries | sendTask | Redirect the referral to another specialist service | `T_RedirectReferral` | job redirect-referral |
| Medical Secretaries | endEvent | Referral closed: not accepted | `E_ReferralClosed` |  |
| Medical Secretaries | endEvent | Referral redirected | `E_ReferralRedirected` |  |
| Consultant / Clinical Team | userTask | Perform the clinical review of the referral | `T_ClinicalReviewReferral` | form form-clinical-review-referral |
| Consultant / Clinical Team | userTask | Record the referral decision, rationale and responsible clinician | `T_RecordReferralDecision` | form form-record-referral-decision |
| Consultant / Clinical Team | exclusiveGateway | Referral decision? | `G_ReferralDecision` |  |
| Consultant / Clinical Team | userTask | Forward the accepted referral to the Outpatient Bookings Team | `T_ForwardAcceptedReferral` | form form-forward-accepted-referral |
| Consultant / Clinical Team | userTask | Deliver the new patient consultation and discuss treatment options | `T_NewPatientConsultation` | form form-new-patient-consultation |
| Consultant / Clinical Team | exclusiveGateway | Patient consents to proceed with treatment? | `G_PatientConsent` |  |
| Consultant / Clinical Team | userTask | Record the patient consent to treatment | `T_RecordPatientConsent` | form form-record-patient-consent |
| Consultant / Clinical Team | userTask | Create the authorised Treatment Booking Request | `T_CreateTreatmentBookingRequest` | form form-treatment-booking-request |
| Consultant / Clinical Team | exclusiveGateway | Request completed and authorised by an authorised clinical professional? | `G_RequestAuthorised` |  |
| Consultant / Clinical Team | userTask | Authorise urgent treatment without confirmed payment and record the reason | `T_AuthoriseUrgentTreatment` | form form-authorise-urgent-treatment |
| Outpatient Bookings Team | userTask | Receive and validate the booking request | `T_ReceiveBookingRequest` | form form-validate-booking-request |
| Outpatient Bookings Team | exclusiveGateway | Urgent referral requiring expedited booking? | `G_UrgentReferral` |  |
| Outpatient Bookings Team | userTask | Escalate the booking as urgent and agree the clinical timescale | `T_ExpediteUrgentBooking` | form form-expedite-urgent-booking |
| Outpatient Bookings Team | serviceTask | Request available appointment slots from the external scheduling service | `T_QueryAvailableSlots` | job query-available-appointment-slots |
| Outpatient Bookings Team | exclusiveGateway | Suitable appointment available within the requested period? | `G_SlotsAvailable` |  |
| Outpatient Bookings Team | userTask | Select and book the new patient appointment | `T_SelectAndBookSlot` | form form-select-book-appointment |
| Outpatient Bookings Team | userTask | Confirm the booking and record the appointment reference | `T_ConfirmBooking` | form form-confirm-appointment |
| Outpatient Bookings Team | sendTask | Issue the appointment confirmation letter | `T_SendAppointmentLetter` | job send-appointment-confirmation-letter |
| Outpatient Bookings Team | exclusiveGateway | Appointment due within the next 14 days? | `G_WithinFourteenDays` |  |
| Call Handling Team | userTask | Telephone the patient to confirm attendance | `T_TelephonePatient` | form form-telephone-patient |
| Call Handling Team | userTask | Record the contact attempt and its outcome | `T_RecordContactAttempt` | form form-record-contact-outcome |
| Call Handling Team | exclusiveGateway | Patient confirmed the appointment? | `G_ContactSuccessful` |  |
| Treatment & Chemotherapy Bookings Team | userTask | Return the unauthorised request to the clinical team | `T_ReturnUnauthorisedRequest` | form form-return-unauthorised-request |
| Treatment & Chemotherapy Bookings Team | userTask | Validate the authorised request and confirm resource requirements | `T_ValidateTreatmentRequest` | form form-validate-treatment-request |
| Treatment & Chemotherapy Bookings Team | serviceTask | Request treatment appointments from external clinical services | `T_RequestTreatmentCapacity` | job request-treatment-capacity |
| Treatment & Chemotherapy Bookings Team | exclusiveGateway | External treatment capacity confirmed? | `G_CapacityConfirmed` |  |
| Treatment & Chemotherapy Bookings Team | userTask | Keep the booking pending, notify the responsible team and record the retry | `T_KeepPending` | form form-record-pending-booking |
| Treatment & Chemotherapy Bookings Team | userTask | Confirm the treatment schedule and issue the patient instructions | `T_ConfirmTreatmentSchedule` | form form-confirm-treatment-schedule |
| Treatment & Chemotherapy Bookings Team | endEvent | Treatment schedule confirmed | `E_TreatmentScheduled` |  |
| Finance Team | userTask | Determine the funding route for the treatment | `T_DetermineFundingRoute` | form form-determine-funding-route |
| Finance Team | exclusiveGateway | Funding approved or no payment required? | `G_FundingApproved` |  |
| Finance Team | userTask | Record the funding organisation, authorisation reference, amount and limitations | `T_RecordFundingApproval` | form form-record-funding-approval |
| Finance Team | userTask | Request funding approval or an additional payment | `T_RequestFundingApproval` | form form-request-funding-approval |
| Finance Team | exclusiveGateway | Advance payment required before the appointment is confirmed? | `G_AdvancePaymentRequired` |  |
| Finance Team | serviceTask | Send the secure payment request to the external payment service provider | `T_SendSecurePaymentRequest` | job request-secure-payment |
| Finance Team | exclusiveGateway | Payment outcome returned by the payment service? | `G_PaymentOutcome` |  |
| Finance Team | userTask | Record the payment reference, amount and date against the patient account | `T_RecordPayment` | form form-record-payment |
| Finance Team | userTask | Notify the patient and the responsible team and allow a further attempt | `T_HandlePaymentFailure` | form form-handle-payment-failure |
| Finance Team | userTask | Mark the transaction for investigation and do not raise a second payment | `T_MarkForInvestigation` | form form-mark-payment-investigation |
| Finance Team | userTask | Resolve the outstanding transaction with the provider | `T_ResolveTransaction` | form form-resolve-payment-transaction |
| Finance Team | userTask | Refer the unconfirmed payment to the Finance Team for resolution | `T_ReferUnconfirmedPayment` | form form-refer-unconfirmed-payment |
| Clinical Nurse Specialist Team | userTask | Provide clinical advice and record the decision not to proceed | `T_AdviseNoTreatment` | form form-advise-no-treatment |
| Clinical Nurse Specialist Team | endEvent | Pathway closed: treatment declined | `E_TreatmentDeclined` |  |
| Patient Pathway Coordinators | userTask | Highlight the case and resolve the capacity constraint | `T_ResolveCapacity` | form form-resolve-capacity-constraint |

Events:
* `E_ReferralReceived` — startEvent / message -> Msg_Referral

External interactions (message flows):

| ID | Message | From | To |
| --- | --- | --- | --- |
| `MF_01` | Patient referral | `P_ReferringOrganisation` | `E_ReferralReceived` |
| `MF_02` | Missing documentation request | `T_RequestMissingDocuments` | `P_ReferringOrganisation` |
| `MF_03` | Referral outcome notification | `T_NotifyReferralOutcome` | `P_ReferringOrganisation` |
| `MF_04` | Referral redirect | `T_RedirectReferral` | `P_OtherSpecialist` |
| `MF_05` | Appointment slot request | `T_QueryAvailableSlots` | `P_Scheduling` |
| `MF_06` | Appointment slot response | `P_Scheduling` | `T_QueryAvailableSlots` |
| `MF_07` | Appointment confirmation letter | `T_SendAppointmentLetter` | `P_Correspondence` |
| `MF_08` | Telephone contact attempt | `T_TelephonePatient` | `P_Patient` |
| `MF_09` | Patient contact outcome | `P_Patient` | `T_RecordContactAttempt` |
| `MF_10` | Treatment capacity request | `T_RequestTreatmentCapacity` | `P_ClinicalServices` |
| `MF_11` | Treatment capacity response | `P_ClinicalServices` | `T_RequestTreatmentCapacity` |
| `MF_12` | Funding approval request | `T_RequestFundingApproval` | `P_FundingOrganisation` |
| `MF_13` | Funding approval response | `P_FundingOrganisation` | `T_RequestFundingApproval` |
| `MF_14` | Secure payment request | `T_SendSecurePaymentRequest` | `P_PaymentProvider` |
| `MF_15` | Payment status | `P_PaymentProvider` | `T_SendSecurePaymentRequest` |

## S1_Strategic_Landscape

* File: `02_BPMN_Models/S1_Strategic_Landscape.bpmn`
* Collaboration: S1 | Strategic process landscape: specialist hospital patient pathway
* Execution platform: Camunda Cloud 8.10.0
* White-box participants (2): Specialist Hospital Service (Hospital Patient Administration System); Referring Organisation (GP or another hospital)
* Black-box participants (7): Referring Organisation (GP or another hospital) (upstream); Patient / Authorised Representative (upstream); External Scheduling Service (external service); External Correspondence Service (external service); External Payment Service Provider (external service); External Clinical Services (treatment, laboratory, imaging) (external service); Funding Organisation / Insurer (external service)

### Process `PR_Landscape` — Specialist hospital patient pathway (strategic view)

| Order | Type | Name | ID |
| --- | --- | --- | --- |
| 1 | startEvent | Patient referral received | `E_ReferralReceived` |
| 2 | startEvent | Referral received (manual start) | `E_ReferralReceivedManual` |
| 3 | userTask | Register and validate the patient referral | `T_Register` |
| 4 | exclusiveGateway | Referral documentation complete? | `G_Documentation` |
| 5 | sendTask | Request missing documentation | `T_RequestDocs` |
| 6 | exclusiveGateway | Referral accepted for specialist care? | `G_Accepted` |
| 7 | sendTask | Notify the referral outcome | `T_NotifyOutcome` |
| 8 | userTask | Book the new patient appointment | `T_BookAppointment` |
| 9 | endEvent | Referral not accepted | `E_NotAccepted` |
| 10 | userTask | Deliver the consultation and record consent | `T_Consultation` |
| 11 | exclusiveGateway | Patient consents to treatment? | `G_Consent` |
| 12 | userTask | Provide clinical advice and close the episode | `T_Advice` |
| 13 | userTask | Authorise treatment and confirm funding | `T_Authorise` |
| 14 | endEvent | No treatment required or declined | `E_Declined` |
| 15 | exclusiveGateway | Treatment authorised and funded? | `G_Funded` |
| 16 | userTask | Resolve the authorisation or funding issue | `T_ResolveFunding` |
| 17 | userTask | Schedule and deliver the treatment cycles | `T_DeliverTreatment` |
| 18 | userTask | Deliver follow-up care and clinical review | `T_FollowUp` |
| 19 | sendTask | Produce and distribute clinical correspondence | `T_Correspondence` |
| 20 | exclusiveGateway | Correspondence completed within seven days? | `G_LetterOnTime` |
| 21 | userTask | Escalate delayed correspondence | `T_Escalate` |
| 22 | userTask | Handle the patient enquiry | `T_Enquiry` |
| 23 | endEvent | Delayed correspondence escalated | `E_Escalated` |
| 24 | userTask | Complete the pathway and discharge the patient | `T_Complete` |
| 25 | endEvent | Patient pathway completed | `E_Complete` |

Events:
* `E_ReferralReceived` — startEvent / message -> M_Referral

External interactions (message flows):

| ID | Message | From | To |
| --- | --- | --- | --- |
| `MF_1` | Patient referral | `P_ReferringOrganisation` | `E_ReferralReceived` |
| `MF_2` | Missing documentation request | `T_RequestDocs` | `P_ReferringOrganisation` |
| `MF_3` | Referral outcome notification | `T_NotifyOutcome` | `P_ReferringOrganisation` |
| `MF_4` | Appointment slot request | `T_BookAppointment` | `P_Scheduling` |
| `MF_5` | Appointment slot response | `P_Scheduling` | `T_BookAppointment` |
| `MF_6` | Appointment confirmation letter | `T_BookAppointment` | `P_Correspondence` |
| `MF_7` | Funding approval request | `T_Authorise` | `P_Funding` |
| `MF_8` | Funding approval response | `P_Funding` | `T_Authorise` |
| `MF_9` | Secure payment request | `T_Authorise` | `P_PaymentProvider` |
| `MF_10` | Payment status | `P_PaymentProvider` | `T_Authorise` |
| `MF_11` | Treatment or investigation request | `T_DeliverTreatment` | `P_ClinicalServices` |
| `MF_12` | Treatment or investigation response | `P_ClinicalServices` | `T_DeliverTreatment` |
| `MF_13` | Clinical correspondence | `T_Correspondence` | `P_Correspondence` |
| `MF_14` | Patient enquiry | `P_Patient` | `T_Enquiry` |
| `MF_15` | Enquiry response | `T_Enquiry` | `P_Patient` |

## S2_Strategic_Referral_To_Authorisation

* File: `02_BPMN_Models/S2_Strategic_Referral_To_Authorisation.bpmn`
* Collaboration: S2 | Strategic collaboration: from referral to authorised treatment
* Execution platform: Camunda Cloud 8.10.0
* White-box participants (2): Specialist Hospital Service (Hospital Patient Administration System); Referring Organisation (GP or another hospital)
* Black-box participants (5): Referring Organisation (GP or another hospital) (upstream); Patient / Authorised Representative (upstream); External Scheduling Service (external service); External Correspondence Service (external service); Other Specialist Service (external service)

### Process `PR_ReferralToAuthorisation` — Referral intake, appointment booking and treatment authorisation

Lanes (7): Medical Secretaries | Consultant / Clinical Team | Outpatient Bookings Team | Patient Pathway Coordinators | Call Handling Team | Treatment & Chemotherapy Bookings Team | Clinical Nurse Specialist Team

| Lane | Type | Name | ID | Form / job type |
| --- | --- | --- | --- | --- |
| Medical Secretaries | startEvent | Patient referral received | `E_ReferralReceived` |  |
| Medical Secretaries | startEvent | Referral received (manual start) | `E_ReferralReceivedManual` |  |
| Medical Secretaries | userTask | Register the referral and confirm patient identification | `T_RegisterReferral` | form form-register-referral |
| Medical Secretaries | userTask | Check referral documentation completeness | `T_CheckDocumentation` | form form-check-referral-documents |
| Medical Secretaries | exclusiveGateway | All expected supporting documents available? | `G_DocumentationComplete` |  |
| Medical Secretaries | sendTask | Request the missing documentation from the referring organisation | `T_RequestMissingDocs` | job request-missing-documentation |
| Medical Secretaries | sendTask | Notify the referring organisation of the referral decision | `T_NotifyNotAccepted` | job send-referral-outcome |
| Medical Secretaries | sendTask | Redirect the referral to another specialist service | `T_RedirectReferral` | job redirect-referral |
| Medical Secretaries | endEvent | Referral closed: not accepted | `E_NotAccepted` |  |
| Medical Secretaries | endEvent | Referral redirected | `E_Redirected` |  |
| Consultant / Clinical Team | userTask | Perform the clinical review of the referral | `T_ClinicalReview` | form form-clinical-review-referral |
| Consultant / Clinical Team | userTask | Record the referral decision, rationale and responsible clinician | `T_RecordDecision` | form form-record-referral-decision |
| Consultant / Clinical Team | exclusiveGateway | Referral decision? | `G_ReferralDecision` |  |
| Consultant / Clinical Team | userTask | Forward the accepted referral to the Outpatient Bookings Team | `T_ForwardAccepted` | form form-forward-accepted-referral |
| Consultant / Clinical Team | userTask | Deliver the new patient consultation and discuss treatment options | `T_NewPatientConsultation` | form form-new-patient-consultation |
| Consultant / Clinical Team | exclusiveGateway | Patient consents to proceed with treatment? | `G_PatientConsent` |  |
| Consultant / Clinical Team | userTask | Record the patient consent to treatment | `T_RecordConsent` | form form-record-patient-consent |
| Consultant / Clinical Team | userTask | Create the authorised Treatment Booking Request | `T_CreateAuthorisedRequest` | form form-treatment-booking-request |
| Consultant / Clinical Team | exclusiveGateway | Request completed and authorised by an authorised clinical professional? | `G_RequestAuthorised` |  |
| Consultant / Clinical Team | endEvent | Treatment booking request authorised | `E_TreatmentAuthorised` |  |
| Outpatient Bookings Team | userTask | Receive and validate the new patient booking request | `T_ReceiveBookingRequest` | form form-validate-booking-request |
| Outpatient Bookings Team | exclusiveGateway | Urgent referral requiring expedited booking? | `G_UrgentReferral` |  |
| Outpatient Bookings Team | userTask | Escalate the booking as urgent and agree the clinical timescale | `T_ExpediteBooking` | form form-expedite-urgent-booking |
| Outpatient Bookings Team | serviceTask | Request available appointment slots from the External Scheduling Service | `T_QuerySlots` | job query-available-appointment-slots |
| Outpatient Bookings Team | exclusiveGateway | Suitable appointment available within the requested period? | `G_SlotsAvailable` |  |
| Outpatient Bookings Team | userTask | Select and book the new patient appointment | `T_SelectBookAppointment` | form form-select-book-appointment |
| Outpatient Bookings Team | userTask | Confirm the appointment and record the booking reference | `T_ConfirmAppointment` | form form-confirm-appointment |
| Outpatient Bookings Team | sendTask | Issue the appointment confirmation through the External Correspondence Service | `T_SendAppointmentLetter` | job send-appointment-confirmation-letter |
| Outpatient Bookings Team | exclusiveGateway | Appointment due within the next 14 days? | `G_WithinFourteenDays` |  |
| Patient Pathway Coordinators | userTask | Highlight the case and resolve the capacity constraint | `T_ResolveCapacity` | form form-resolve-capacity-constraint |
| Call Handling Team | userTask | Telephone the patient to confirm attendance | `T_TelephonePatient` | form form-telephone-patient |
| Call Handling Team | userTask | Record the contact attempt and its outcome | `T_RecordContactOutcome` | form form-record-contact-outcome |
| Call Handling Team | exclusiveGateway | Patient confirmed the appointment? | `G_ContactSuccessful` |  |
| Treatment & Chemotherapy Bookings Team | userTask | Return the unauthorised request to the clinical team | `T_ReturnUnauthorisedRequest` | form form-return-unauthorised-request |
| Clinical Nurse Specialist Team | userTask | Provide the patient with Clinical Nurse Specialist contact details | `T_ProvideCnsContactDetails` | form form-provide-cns-contact-details |
| Clinical Nurse Specialist Team | userTask | Provide clinical advice and record the decision not to proceed | `T_AdviseAndClose` | form form-advise-no-treatment |
| Clinical Nurse Specialist Team | endEvent | Pathway closed: treatment declined | `E_Declined` |  |

Events:
* `E_ReferralReceived` — startEvent / message -> Msg_Referral

External interactions (message flows):

| ID | Message | From | To |
| --- | --- | --- | --- |
| `MF_S1` | Patient referral | `P_ReferringOrganisation` | `E_ReferralReceived` |
| `MF_S2` | Missing documentation request | `T_RequestMissingDocs` | `P_ReferringOrganisation` |
| `MF_S3` | Referral outcome notification | `T_NotifyNotAccepted` | `P_ReferringOrganisation` |
| `MF_S4` | Referral redirect | `T_RedirectReferral` | `P_OtherSpecialist` |
| `MF_S5` | Appointment slot request | `T_QuerySlots` | `P_Scheduling` |
| `MF_S6` | Appointment slot response | `P_Scheduling` | `T_QuerySlots` |
| `MF_S7` | Appointment confirmation letter | `T_SendAppointmentLetter` | `P_Correspondence` |
| `MF_S8` | Telephone contact attempt | `T_TelephonePatient` | `P_Patient` |
| `MF_S9` | Patient contact outcome | `P_Patient` | `T_RecordContactOutcome` |

## S3_Strategic_Treatment_To_Aftercare

* File: `02_BPMN_Models/S3_Strategic_Treatment_To_Aftercare.bpmn`
* Collaboration: S3 | Strategic collaboration: treatment, correspondence, enquiries and aftercare
* Execution platform: Camunda Cloud 8.10.0
* White-box participants (3): Specialist Hospital Service (Hospital Patient Administration System); Hospital Patient Administration System - patient enquiry handling; Hospital Patient Administration System - management reporting
* Black-box participants (6): Patient / Authorised Representative (upstream); External Clinical Services (treatment, laboratory, imaging) (external service); Funding Organisation / Insurer (external service); External Payment Service Provider (external service); External Correspondence Service (external service); External Scheduling Service (external service)

### Process `PR_TreatmentToAftercare` — Treatment funding, delivery, correspondence and aftercare

Lanes (7): Treatment & Chemotherapy Bookings Team | Finance Team | Consultant / Clinical Team | Medical Secretaries | Outpatient Bookings Team | Patient Pathway Coordinators | Administrative Management

| Lane | Type | Name | ID | Form / job type |
| --- | --- | --- | --- | --- |
| Treatment & Chemotherapy Bookings Team | startEvent | Authorised treatment booking request received | `E_AuthorisedRequestReceived` |  |
| Treatment & Chemotherapy Bookings Team | startEvent | Treatment request received (manual start) | `E_TreatmentRequestManual` |  |
| Treatment & Chemotherapy Bookings Team | userTask | Validate the authorised request and confirm resource requirements | `T_ValidateRequest` | form form-validate-treatment-request |
| Treatment & Chemotherapy Bookings Team | serviceTask | Request treatment appointments from external clinical services | `T_RequestTreatmentCapacity` | job request-treatment-capacity |
| Treatment & Chemotherapy Bookings Team | exclusiveGateway | External treatment capacity confirmed? | `G_CapacityConfirmed` |  |
| Treatment & Chemotherapy Bookings Team | userTask | Keep the booking pending, notify the responsible team and record the retry | `T_KeepPending` | form form-record-pending-booking |
| Treatment & Chemotherapy Bookings Team | userTask | Confirm the treatment schedule and issue the patient instructions | `T_ConfirmTreatmentSchedule` | form form-confirm-treatment-schedule |
| Finance Team | userTask | Determine the funding route: hospital funded, approved insurer or patient payable | `T_DetermineFunding` | form form-determine-funding-route |
| Finance Team | exclusiveGateway | Funding approved or no payment required? | `G_FundingApproved` |  |
| Finance Team | userTask | Record the funding organisation, authorisation reference, approved amount and limitations | `T_RecordFundingApproval` | form form-record-funding-approval |
| Finance Team | userTask | Request funding approval or additional payment | `T_RequestFundingApproval` | form form-request-funding-approval |
| Finance Team | exclusiveGateway | Advance payment required before confirmation? | `G_AdvancePaymentRequired` |  |
| Finance Team | serviceTask | Send the secure payment request to the External Payment Service Provider | `T_RequestSecurePayment` | job request-secure-payment |
| Finance Team | exclusiveGateway | Payment outcome returned by the payment service? | `G_PaymentOutcome` |  |
| Finance Team | userTask | Record the payment reference, amount and date against the patient account | `T_RecordPayment` | form form-record-payment |
| Finance Team | userTask | Notify the patient and the responsible team and allow a further attempt without a duplicate booking | `T_HandlePaymentFailure` | form form-handle-payment-failure |
| Finance Team | userTask | Mark the transaction for investigation and do not raise a second payment | `T_MarkForInvestigation` | form form-mark-payment-investigation |
| Finance Team | userTask | Resolve the outstanding transaction with the payment provider or funding organisation | `T_ResolveTransaction` | form form-resolve-payment-transaction |
| Finance Team | userTask | Refer the unconfirmed payment to the Finance Team for later resolution | `T_ReferUnconfirmedPayment` | form form-refer-unconfirmed-payment |
| Finance Team | exclusiveGateway | Modification affects an existing charge, funding approval or payment? | `G_FinancialImpact` |  |
| Finance Team | userTask | Review the financial implications and update the funding or payment record | `T_ReviewFinancialImpact` | form form-review-financial-impact |
| Finance Team | userTask | Determine whether the payment should be retained, transferred or refunded | `T_RefundDecision` | form form-refund-decision |
| Finance Team | serviceTask | Send the approved refund request to the External Payment Service Provider | `T_RequestRefund` | job request-refund |
| Finance Team | userTask | Record the refund result against the patient account | `T_RecordRefund` | form form-record-refund |
| Consultant / Clinical Team | userTask | Authorise urgent treatment without confirmed payment and record the reason | `T_AuthoriseUrgentTreatment` | form form-authorise-urgent-treatment |
| Consultant / Clinical Team | userTask | Deliver the treatment cycle and record clinical administration | `T_DeliverTreatmentCycle` | form form-deliver-treatment-cycle |
| Consultant / Clinical Team | exclusiveGateway | Further treatment cycles planned? | `G_FurtherCycles` |  |
| Consultant / Clinical Team | serviceTask | Request the pre-cycle blood test and clinical assessment | `T_RequestBloodTest` | job request-blood-test |
| Consultant / Clinical Team | userTask | Review the results and confirm whether the patient is fit to continue | `T_ReviewCycleResults` | form form-review-cycle-results |
| Consultant / Clinical Team | exclusiveGateway | Patient fit to continue as planned? | `G_FitnessToContinue` |  |
| Consultant / Clinical Team | userTask | Raise and authorise a Treatment Modification Request | `T_ModifyTreatment` | form form-treatment-modification-request |
| Consultant / Clinical Team | userTask | Record the urgent postponement for patient safety and obtain retrospective authorisation | `T_UrgentPostponement` | form form-urgent-postponement |
| Consultant / Clinical Team | userTask | Apply the authorised change and update the treatment schedule | `T_ApplyTreatmentChange` | form form-apply-treatment-change |
| Consultant / Clinical Team | userTask | Prepare the clinic letter | `T_PrepareClinicLetter` | form form-prepare-clinic-letter |
| Consultant / Clinical Team | boundaryEvent | Clinic letter not approved within seven days | `B_LetterDelayed` |  |
| Consultant / Clinical Team | userTask | Approve the clinical content of the clinic letter | `T_ApproveClinicLetter` | form form-approve-clinic-letter |
| Consultant / Clinical Team | exclusiveGateway | Clinical content approved? | `G_LetterApproved` |  |
| Consultant / Clinical Team | userTask | Request a follow-up appointment within the clinically specified period | `T_RequestFollowUp` | form form-request-follow-up |
| Consultant / Clinical Team | userTask | Complete the pathway and discharge the patient | `T_CompletePathway` | form form-complete-pathway |
| Consultant / Clinical Team | endEvent | Patient pathway completed | `E_PathwayComplete` |  |
| Medical Secretaries | userTask | Perform the administrative checks and confirm the intended recipients | `T_AdministrativeCheck` | form form-clinic-letter-admin-check |
| Medical Secretaries | exclusiveGateway | Suspected clinical error in the letter? | `G_ClinicalError` |  |
| Medical Secretaries | exclusiveGateway | Does the patient require an accessible format, translation or a representative? | `G_CommunicationPreference` |  |
| Medical Secretaries | userTask | Produce the correspondence in the required accessible format or language | `T_PrepareAccessibleFormat` | form form-prepare-accessible-format |
| Medical Secretaries | sendTask | Distribute the clinic letter through the approved communication channels | `T_DistributeClinicLetter` | job distribute-clinical-correspondence |
| Outpatient Bookings Team | userTask | Arrange the follow-up appointment using the External Scheduling Service | `T_ArrangeFollowUp` | form form-arrange-follow-up |
| Outpatient Bookings Team | exclusiveGateway | Appointment found within the requested period? | `G_FollowUpWithinPeriod` |  |
| Outpatient Bookings Team | userTask | Confirm the follow-up appointment and notify the patient | `T_ConfirmFollowUp` | form form-confirm-follow-up |
| Outpatient Bookings Team | boundaryEvent | Patient cancels, declines or does not attend | `B_NotAttending` |  |
| Outpatient Bookings Team | userTask | Record the cancellation or non-attendance and determine the next step | `T_RecordNonAttendance` | form form-record-non-attendance |
| Outpatient Bookings Team | exclusiveGateway | Does the cancelled appointment carry a payment? | `G_PaymentOnAppointment` |  |
| Outpatient Bookings Team | userTask | Offer a further appointment or refer the pathway for clinical review | `T_OfferAnotherAppointment` | form form-offer-another-appointment |
| Outpatient Bookings Team | endEvent | Appointment not attended: pathway reviewed | `E_PathwayReviewed` |  |
| Patient Pathway Coordinators | userTask | Issue a weekly reminder to the responsible consultant | `T_WeeklyReminder` | form form-issue-letter-reminder |
| Patient Pathway Coordinators | intermediateCatchEvent | Wait one week before the next reminder | `T_ReminderInterval` |  |
| Patient Pathway Coordinators | exclusiveGateway | Letter outstanding for more than one month? | `G_LetterAge` |  |
| Patient Pathway Coordinators | userTask | Highlight the case and refer it to the relevant pathway team | `T_HighlightFollowUp` | form form-highlight-follow-up |
| Patient Pathway Coordinators | endEvent | Follow-up outside the clinical timescale escalated | `E_FollowUpEscalated` |  |
| Administrative Management | userTask | Escalate to the Administrative Manager, who contacts the consultant | `T_EscalateToManager` | form form-escalate-to-manager |
| Administrative Management | exclusiveGateway | Letter outstanding for more than three months? | `G_LetterAgeExtended` |  |
| Administrative Management | userTask | Escalate to the higher management team | `T_EscalateToHigherManagement` | form form-escalate-higher-management |
| Administrative Management | endEvent | Delayed correspondence escalated | `E_DelayedCorrespondence` |  |

Events:
* `E_AuthorisedRequestReceived` — startEvent / message -> Msg_AuthorisedTreatmentRequest
* `B_LetterDelayed` — boundaryEvent / timer (P7D) attached to T_PrepareClinicLetter (non-interrupting)
* `T_ReminderInterval` — intermediateCatchEvent / timer (P7D)
* `B_NotAttending` — boundaryEvent / message -> Msg_PatientNotAttending attached to T_ConfirmFollowUp

### Process `PR_EnquiryHandling` — Patient enquiry handling

Lanes (3): Call Handling Team | Clinical Nurse Specialist Team | Finance Team

| Lane | Type | Name | ID | Form / job type |
| --- | --- | --- | --- | --- |
| Call Handling Team | startEvent | Patient or representative enquiry received | `E_EnquiryReceived` |  |
| Call Handling Team | startEvent | Enquiry received (manual start) | `E_EnquiryManual` |  |
| Call Handling Team | userTask | Record, classify and prioritise the enquiry | `T_ClassifyEnquiry` | form form-classify-enquiry |
| Call Handling Team | exclusiveGateway | What type of enquiry is it? | `G_EnquiryType` |  |
| Call Handling Team | userTask | Answer or transfer the administrative enquiry to the responsible team | `T_AnswerAdministrative` | form form-answer-administrative-enquiry |
| Call Handling Team | userTask | Record the response, responsible team and resolution status | `T_RecordEnquiryOutcome` | form form-record-enquiry-outcome |
| Call Handling Team | endEvent | Enquiry resolved and closed | `E_EnquiryClosed` |  |
| Clinical Nurse Specialist Team | userTask | Provide clinical advice through an authorised clinical professional | `T_AnswerClinical` | form form-answer-clinical-enquiry |
| Clinical Nurse Specialist Team | userTask | Highlight and escalate the urgent clinical concern immediately | `T_HandleUrgentConcern` | form form-urgent-clinical-concern |
| Finance Team | userTask | Answer the payment or funding enquiry using authorised information | `T_AnswerFinancial` | form form-answer-financial-enquiry |

Events:
* `E_EnquiryReceived` — startEvent / message -> Msg_PatientEnquiry

### Process `PR_ManagementReporting` — Management reporting

Lanes (1): Hospital Management

| Lane | Type | Name | ID | Form / job type |
| --- | --- | --- | --- | --- |
| Hospital Management | startEvent | Monthly reporting period reached | `E_ReportingPeriodReached` |  |
| Hospital Management | startEvent | Report requested (manual start) | `E_ReportingManual` |  |
| Hospital Management | serviceTask | Generate referral, waiting time, correspondence, funding, payment and pathway reports | `T_GenerateManagementReports` | job generate-management-reports |
| Hospital Management | userTask | Review performance reports and agree corrective action | `T_ReviewManagementReports` | form form-review-management-reports |
| Hospital Management | endEvent | Reports published and corrective action agreed | `E_ReportsPublished` |  |

Events:
* `E_ReportingPeriodReached` — startEvent / timer (R/P1M)

External interactions (message flows):

| ID | Message | From | To |
| --- | --- | --- | --- |
| `MF_1` | Treatment capacity request | `T_RequestTreatmentCapacity` | `P_ClinicalServices` |
| `MF_2` | Treatment capacity response | `P_ClinicalServices` | `T_RequestTreatmentCapacity` |
| `MF_3` | Blood test and assessment request | `T_RequestBloodTest` | `P_ClinicalServices` |
| `MF_4` | Funding approval request | `T_RequestFundingApproval` | `P_FundingOrganisation` |
| `MF_5` | Funding approval response | `P_FundingOrganisation` | `T_RequestFundingApproval` |
| `MF_6` | Secure payment request | `T_RequestSecurePayment` | `P_PaymentProvider` |
| `MF_7` | Payment status | `P_PaymentProvider` | `T_RequestSecurePayment` |
| `MF_8` | Refund request | `T_RequestRefund` | `P_PaymentProvider` |
| `MF_9` | Clinical correspondence | `T_DistributeClinicLetter` | `P_Correspondence` |
| `MF_10` | Follow-up appointment request | `T_ArrangeFollowUp` | `P_Scheduling` |
| `MF_11` | Follow-up appointment response | `P_Scheduling` | `T_ArrangeFollowUp` |
| `MF_12` | Patient cancellation or non-attendance | `P_Patient` | `B_NotAttending` |
| `MF_13` | Patient enquiry | `P_Patient` | `E_EnquiryReceived` |
