# Second-release improvement proposals

Derived from the gap analysis in the alignment evaluation. Priority uses MoSCoW, and
the ordering is justified in the alignment evaluation, section 5.

| # | Priority | Improvement | Gap addressed | Rationale | Effort | First owner | Second owner | Acceptance condition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Must | Correlation record binding patient, referral, request, appointment, funding decision, payment and refund into one auditable episode | Episode-level traceability | Every audited element exists already; what is missing is the link, so this is the cheapest high-value change | 5 | henry | max | A single query returns the full episode for a patient identifier |
| 2 | Must | Role-based access control and authentication on every task, with candidate groups enforced | RBAC and audit | The models already carry `candidateGroups`; the engine does not yet enforce them | 8 | peter | finn | A user outside the candidate group cannot claim or complete the task |
| 3 | Must | Immutable audit records for referral decisions, authorisations, payment requests, funding decisions and refunds | Audit immutability | Audit records are written but can be altered by an ordinary user | 5 | max | peter | An attempt to edit an audit record is rejected and logged |
| 4 | Should | Urgency classification rules for referrals and enquiries | Unagreed urgency rules | The gateways exist with asserted variables; the rules behind them do not | 3 | henry | finn | A written rule set exists and every urgency gateway evaluates it |
| 5 | Should | Duplicate-detection rule and idempotency key for appointment and payment retries | No duplicate booking or charge | The retry loops currently rely on operator discipline | 5 | finn | peter | Two retries of the same request produce one appointment and one charge |
| 6 | Should | Procedure for recording activity completed during system or external-service unavailability | Availability and downtime | No fallback procedure is implemented | 3 | max | henry | A downtime record can be captured and reconciled afterwards |
| 7 | Should | Patient communication preference, accessible format and translation handling | Communication preferences | Modelled in S3 but not implemented | 3 | peter | henry | A preference is captured and the correspondence path honours it |
| 8 | Could | Clinic-letter reminder de-duplication | Repeated reminders | The non-interrupting timer already cancels on completion; the guarantee is not tested | 2 | henry | max | A completed letter produces no further reminder |
| 9 | Could | Funding-approval expiry rule | Stale funding approvals | An approval with limitations and an amount has no validity period | 2 | max | finn | An expired approval returns the case to the funding step |
| 10 | Could | External-service unavailability log and retry report | Visibility of external failures | Pending bookings are recorded but not reported | 2 | finn | henry | A report lists every pending booking and its retry count |
| 11 | Could | Management reporting as a scheduled deployment, not just a model | Management reporting | The reporting process is modelled but not implemented | 5 | peter | max | The monthly report process produces the required report set |
| 12 | Won't (this release) | Replacement of the external scheduling service with a direct hospital scheduling module | External dependency | The case study treats scheduling as external, and replacing it is out of scope for this module | 13 | - | - | Explicitly out of scope; recorded so the decision is visible |
