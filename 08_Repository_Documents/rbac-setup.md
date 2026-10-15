# Role-based access control

Item 2 of the review list: implement Camunda RBAC so that different roles see different
tasks. This records what was configured, why the shipped configuration was not enough, and
how to reproduce and re-verify it.

## Why the delivered configuration did not satisfy the item

Two settings in the shipped Camunda 8 Run configuration mean RBAC is not in force at all:

| Setting | Shipped value | Effect |
| --- | --- | --- |
| `camunda.security.authorizations.enabled` | `false` | authorization is never evaluated |
| `camunda.security.authentication.unprotected-api` | `true` | the REST API skips permission checks entirely |

With those values every authenticated user sees every task, which is why the earlier
attempt to demonstrate role separation showed all ten roles with an identical inbox. Both
are now `true` and `false` respectively in
`c8run-8.10.0-alpha5/configuration/application.yaml` (a backup of the shipped file is kept
beside it as `application.yaml.bak-before-rbac`).

The models were already correct: every user task carries a `candidateGroups` attribute,
**99 references covering 10 groups**. What was missing was the identity half - the groups
did not exist, no user belonged to them, and no authorization had been granted.

## What was configured

`09_Tests_and_Tools/setup-rbac.py` reads the candidate groups out of the deployed models,
so the identity data cannot drift from the process models, and then:

1. creates the ten groups;
2. creates one demonstration user per group and puts it in that group, and no other;
3. grants each group `PROCESS_DEFINITION` and `USER_TASK` permissions.

The grants are deliberately identical across groups. The restriction that makes roles
differ is the candidate group on the task, and the point of the evidence below is to show
that this is what actually separates the roles.

| Group | Demonstration user | Tasks routed to it |
| --- | --- | --- |
| `medical-secretaries` | `secretary.demo` | 6 |
| `consultant-team` | `consultant.demo` | 19 |
| `clinical-nurse-specialist-team` | `nurse.demo` | 2 |
| `outpatient-bookings-team` | `bookings.demo` | 9 |
| `treatment-bookings-team` | `treatment.demo` | 4 |
| `call-handling-team` | `callhandler.demo` | 6 |
| `finance-team` | `finance.demo` | 6 |
| `patient-pathway-coordinators` | `pathway.demo` | 0 |
| `administrative-management` | `adminmgmt.demo` | 0 |
| `hospital-management` | `management.demo` | 1 |
| *(deliberately ungranted)* | `norole.demo` | 0 |

The demonstration password is `demo1234`. `norole.demo` exists only as the control case in
the enforcement check below.

## How to reproduce and re-verify

```powershell
python 09_Tests_and_Tools/setup-rbac.py      # groups, users, authorizations
python 09_Tests_and_Tools/verify-rbac.py     # evidence, exits non-zero on failure
```

`verify-rbac.py` writes `05_Test_Evidence/rbac/task-visibility.json` and checks three
separate things, because Camunda 8 enforces "different roles see different tasks" at more
than one layer:

| Check | What it proves | Result |
| --- | --- | --- |
| A membership | each demonstration user belongs to exactly the candidate group the models assign to its role, and to no other | 10/10 |
| B enforcement | a user whose groups hold no user-task authorization is served an empty result where a granted user is served tasks | 0 vs 785 |
| C routing | each role's inbox, queried with the candidate-group filter Tasklist builds from the signed-in user's groups, contains only tasks the model assigns to that role | 0 mismatches |

Of the 84 task definitions the models route, 52 have been reached by an executed process
instance and therefore appear in an inbox. The remaining 32 have no instances in the
recorded runs, which is a property of what has been executed so far rather than a routing
gap. Exactly one task, `T_Authorise`, is reachable by two roles, and that is by design -
its candidate groups are `consultant-team,finance-team`.

## The one thing still to be photographed

Tasklist authenticates with its own login form, not with HTTP basic authentication, so a
headless browser reaches only the login page and cannot sign in. The two screenshots the
portfolio refers to therefore have to be taken by hand:

1. open `http://localhost:8080/tasklist`, sign in as `secretary.demo` / `demo1234`,
   screenshot the task list;
2. sign out, sign in as `finance.demo` / `demo1234`, screenshot again.

The two lists are disjoint, which is the requirement stated in the review list. Save them
as `05_Test_Evidence/rbac/tasklist-medical-secretaries.png` and
`05_Test_Evidence/rbac/tasklist-finance.png`.

## What the API cannot express, and why that is not a gap here

Camunda's `USER_TASK` authorization takes a resource id that identifies a task instance or
`*`, and `resourceId` cannot be combined with `resourcePropertyName`. There is therefore
no way to write "this group may read user tasks whose candidate group is X" as a single
authorization - role separation at task level is expressed by `candidateGroups` in the
model and applied by Tasklist for the signed-in user's groups. The authorization layer
then decides whether a caller may use the API at all, which is what check B measures.
