# Strategic to operational mapping

This is the mapping used by the "LINK TO THE DETAILED OPERATIONAL MODEL" note on the
S2 and S3 diagrams, and by the traceability table in the alignment evaluation.

The strategic models are `S1_Strategic_Landscape.bpmn` (level 1),
`S2_Strategic_Referral_To_Authorisation.bpmn` and
`S3_Strategic_Treatment_To_Aftercare.bpmn` (level 2). The detailed operational model
is `O1_Operational_Merged.bpmn` (level 3), which is the merge of the group's three
Sprint 1 / Sprint 2 fragments and is deployed on the Camunda 8 cluster as
`PR_Operational_Merged`.

| Strategic activity | Model and task id | Operational realisation (O1) | Verified by |
| --- | --- | --- | --- |
| Check referral documentation completeness | S2 `T_CheckDocumentation` | `T_CheckReferralDocuments` | TC-01, TC-02 |
| Request the missing documentation | S2 `T_RequestMissingDocs` | `T_RequestMissingDocuments` (job `request-missing-documentation`) | TC-02 |
| Perform the clinical review of the referral | S2 `T_ClinicalReview` | `T_ClinicalReviewReferral` | TC-01 |
| Record the referral decision, rationale and responsible clinician | S2 `T_RecordDecision` | `T_RecordReferralDecision` | TC-01, TC-03, TC-04 |
| Request available appointment slots | S2 `T_QuerySlots` | `T_QueryAvailableSlots` (job `query-available-appointment-slots`) | TC-05 |
| Highlight the case and resolve the capacity constraint | S2 `T_ResolveCapacity` | `T_ResolveCapacity` | TC-05 |
| Select and book the appointment | S2 `T_SelectBook` | `T_SelectAndBookSlot`, `T_ConfirmBooking` | TC-05, TC-13 |
| Telephone the patient to confirm attendance | S2 `T_TelephonePatient` | `T_TelephonePatient` | TC-06, TC-07, TC-08 |
| Record the contact attempt and its outcome | S2 `T_RecordContactOutcome` | `T_RecordContactAttempt` | TC-08 |
| Record the patient consent to treatment | S2 `T_RecordConsent` | `T_RecordPatientConsent` | TC-09, TC-13 |
| Create the authorised Treatment Booking Request | S2 `T_CreateAuthRequest` | `T_CreateTreatmentBookingRequest` | TC-10, TC-13 |
| Return the unauthorised request to the clinical team | S2 `T_ReturnRequest` | `T_ReturnUnauthorisedRequest` | TC-10 |
| Request treatment appointments from external clinical services | S3 `T_RequestTreatmentCapacity` | `T_RequestTreatmentCapacity` (job `request-treatment-capacity`) | TC-11 |
| Keep the booking pending and record the retry | S3 `T_KeepPending` | `T_KeepPending` | TC-11 |
| Determine the funding route | S3 `T_DetermineFunding` | `T_DetermineFundingRoute` | TC-12, TC-13 |
| Record the funding organisation, reference, amount and limitations | S3 `T_RecordFundingApproval` | `T_RecordFundingApproval` | TC-12 |
| Send the secure payment request | S3 `T_RequestSecurePayment` | `T_SendSecurePaymentRequest` (job `request-secure-payment`) | TC-14 |
| Record the payment reference, amount and date | S3 `T_RecordPayment` | `T_RecordPayment` | TC-14 |
| Notify the patient and the responsible team, allow a further attempt | S3 `T_HandlePaymentFailure` | `T_HandlePaymentFailure` | TC-15 |
| Mark the transaction for investigation | S3 `T_MarkForInvestigation` | `T_MarkForInvestigation` | TC-16 |
| Authorise urgent treatment without confirmed payment | S3 `T_AuthoriseUrgentTreatment` | `T_AuthoriseUrgentTreatment` | TC-17 |
| Refer the unconfirmed payment to the Finance Team | S3 `T_ReferUnconfirmedPayment` | `T_ReferUnconfirmedPayment` | TC-17 |
| Confirm the treatment schedule | S3 `T_ConfirmTreatmentSchedule` | `T_ConfirmTreatmentSchedule` | TC-13, TC-18 |
| Raise and authorise a Treatment Modification Request | S3 `T_ModifyTreatment` | not implemented in the initial release | gap |
| Prepare and approve the clinic letter | S3 `T_PrepareClinicLetter`, `T_ApproveClinicLetter` | not implemented in the initial release | gap |
| Issue a weekly reminder; escalate at one and three months | S3 `T_WeeklyReminder`, `T_EscalateToManager` | not implemented in the initial release | gap |
| Determine whether a payment is retained, transferred or refunded | S3 `T_RefundDecision` | not implemented in the initial release | gap |
| Classify and route a patient enquiry | S3 `T_ClassifyEnquiry` | not implemented in the initial release | gap |
| Generate management reports | S3 `T_GenerateManagementReports` | not implemented in the initial release | gap |

Activities that map to an O1 task are implemented in the initial release. Activities
that do not are the gap between the wider business process and the built solution, and
they are carried into the second-release backlog.
