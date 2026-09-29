# Integration decision

## The problem

The group produced three BPMN files in Sprints 1 and 2. They were written at
different times, by different owners, against different execution platforms, and each
covered only part of the pathway. They could not be merged by concatenation.

## The decision

The three fragments are integrated in **two** ways, because the two assessments ask
different questions.

1. **One operational model.** `O1_Operational_Merged.bpmn` merges all three
   fragments into a single detailed operational process (59 flow nodes, 8 lanes,
   8 external participants), targeted at Camunda 8 (Zeebe) 8.10 and deployed as
   `PR_Operational_Merged`.
2. **A strategic model family.** `S1`, `S2` and `S3` present the same business at two
   levels of abstraction, which is what the portfolio's strategic BPMN task requires
   and what makes the abstraction level explainable.

## The seams that had to be closed

| Seam | Problem in the original files | Resolution |
| --- | --- | --- |
| Referral to booking | File 第一 ended at an end event ("Referral accepted"); file 第三 began at a message start event ("Referral approval notification received"). Neither contained the handover | In O1 the accepted branch of the referral decision flows directly into `T_ReceiveBookingRequest` in the Outpatient Bookings Team lane, and both fragments share one process instance |
| Appointment to treatment authorisation | File 第三 ended at "Confirm appointment"; file 第二 began at "Patient Consultation Completed". The consultation, the recorded consent and the creation of the authorised Treatment Booking Request existed in neither | O1 inserts `T_NewPatientConsultation`, `T_RecordPatientConsent` and `T_CreateTreatmentBookingRequest`, and gates the treatment booking on `G_RequestAuthorised` |

## Boundary decisions

- The hospital is one white-box participant. Its internal teams are lanes, not pools,
  because the case study makes them accountable to the same organisation.
- Enquiry handling and management reporting are **separate** processes, not lanes of
  the pathway, because neither is triggered by an individual patient pathway: an
  enquiry may arrive at any time and reporting runs on a monthly cycle.
- External organisations are collapsed black-box participants. Their internal
  behaviour is not described by the case study, and asserting it would be
  unsupported.

## Superseded files

The three original working files are retained in `source/` as evidence of the
Sprint 1 and Sprint 2 increments. They are not deliverable models: their defects are
catalogued in `08_Repository_Documents/defect-log.md`, group A.
