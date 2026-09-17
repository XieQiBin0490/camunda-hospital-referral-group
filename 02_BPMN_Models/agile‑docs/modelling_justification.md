```
# Modelling Justification for Hospital Referral Operational BPMN

## 1. Lane / Pool decisions
We divided lanes according to real‑world team responsibilities from the case study.
Lanes include Medical Secretaries, Consultant / Clinical Team, Hospital Patient Administration, Finance Team and separate lanes for external services.

Assumption: External scheduling, correspondence and payment systems are outside our system boundary, so they are placed in independent lanes and called via Service Tasks.

Alternative considered: We could merge some administrative lanes together. However separate lanes make role responsibilities clearer for readers. We decided not to merge because role separation is an important business rule described in the case study.

## 2. Gateway (decision point) choices
We use Exclusive Gateways (diamond shape) for all yes/no branching logic.
Every outgoing sequence flow has clear condition labels such as Yes, No, Accepted, Rejected.

Alternative considered: We considered using inclusive gateway, but our business rules produce mutually‑exclusive branches. Only one path can be taken at each decision point, so exclusive gateway is more suitable.

## 3. Task type selection (User Task / Service Task)
- **User Task**: Activities that must be manually completed by hospital staff (with person icon). For example checking documents, record rejection reason.
- **Service Task**: Automatic interaction with external third‑party systems, e.g. call external scheduling service, send payment request to payment provider.

Assumption: Service tasks represent calls to outside systems; our system cannot fully control the behaviour of external services.

## 4. System boundary
Our system boundary covers internal hospital workflow.
External services: scheduling service, correspondence service, payment service are outside boundary. Our system sends requests and receives responses but does not implement those external services.

Some business rules are only enforced by human staff and cannot be fully automated in this initial release, for example clinical judgement from consultants.

## 5. Assumptions & Trade‑offs
Assumptions made in this operational model:
1. Every task has correct role‑based access control, enforced outside this BPMN diagram.
2. Audit logging for sensitive actions exists, modelled as background system behaviour rather than explicit visible tasks on the diagram.

Trade‑offs: We did not model every tiny minor edge case in full detail in order to keep the diagram readable. Complex edge cases will be improved in the second release for portfolio phase.
```