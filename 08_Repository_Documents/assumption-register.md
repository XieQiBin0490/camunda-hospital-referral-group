# Assumption register

Project-level assumptions, each with its source and the consequence if it proves false.

| ID | Assumption | Source | Consequence if false |
| --- | --- | --- | --- |
| A-01 | The initial release is a modelled and partially implemented increment, and the external services are simulated | Case study and product backlog PB-26 (fake external services) | Acceptance results would need re-running against the real services, and several conclusions in the alignment evaluation would weaken |
| A-02 | The scope of the operational model is the union of the three Sprint 1 / Sprint 2 fragments: referral intake, appointment booking, treatment authorisation, funding and payment | The three working files and the Presentation assessment | Work outside that scope (letters, enquiries, refunds, follow-up) would have to be implemented before the second release |
| A-03 | Only an authorised Consultant may judge clinical suitability | Case study, referral paragraph | Any administrative screening of clinical suitability would be a safety and governance defect |
| A-04 | The 14-day telephone rule applies when the appointment is due to take place within the following two weeks | Case study, appointment paragraph | The contact rule would be wrong for the majority of appointments |
| A-05 | A payment whose confirmation is not returned is investigated rather than re-requested | Case study, payment failure paragraph | Re-requesting would risk charging the patient twice |
| A-06 | Urgent treatment may proceed without confirmed payment if the reason is recorded | Case study, urgent treatment paragraph | Delaying care would create a patient risk |
| A-07 | The hospital has not agreed urgency rules for referrals or enquiries | Case study, enquiries paragraph | Urgency gateways would need replacing with agreed rules |
| A-08 | The Camunda 8 cluster used for acceptance testing is representative of the deployment target | Test environment, Camunda 8 Run 8.10.0-alpha5 | Results would need re-validating on the production cluster |
| A-09 | Process variables set by the test harness represent decisions a competent operator would make | Test plan, section 4.2 | The paths exercised would not reflect real operating behaviour |
