# Running the process by hand, step by step

This is the manual route: you start the process yourself from **Operate**, fill
every form yourself in **Tasklist**, and watch the diagram advance. Nothing here
uses the automatic scripts.

Two interfaces, and the split between them matters:

* **Operate** (`/operate`) starts an instance and *shows* it: the diagram, which
  activity is running, the variables, any incidents. It cannot fill a form.
* **Tasklist** (`/tasklist`) is where the human work happens: it renders the
  Camunda Form attached to each user task and completes it.

So: start in Operate, work the forms in Tasklist, verify the outcome back in
Operate.

---

## Stage 0 — once per working session

**1. Start the cluster.** Open the bundle folder and run:

```
C:\Users\a1620\Desktop\camunda8-getting-started-bundle-8.10.0-alpha5-windows-x86_64\c8run-8.10.0-alpha5\c8run.exe start
```

Wait for `Camunda has started successfully`. Leave that window open — closing it
stops the engine.

> The cluster was down when you tried the start button, and that alone makes every
> start fail. Check this first.

**2. Deploy the models and forms** (skip if you have not changed them):

```
cd C:\Users\a1620\Desktop\UFCEP4-0-3_Final
node tools\deploy-all.mjs
```

Expect `forms -> 68/68 deployed` and six `PR_...` definitions.

**3. Start the workers — do not skip this.** Open a **second** window:

```
cd C:\Users\a1620\Desktop\UFCEP4-0-3_Final
powershell -File workers\run-workers.ps1
```

Wait for `13 workers subscribed and polling 127.0.0.1:26500`.

Without this the process stops at the first automated activity and looks broken:
the user task you just completed leads to a service task, and nothing is
listening for it. Leave this window open too.

**4. Open the browser** to `http://127.0.0.1:8080/operate` and log in `demo` /
`demo`.

---

## Stage 1 — start the process in Operate

1. In the left sidebar, click **Processes**.
2. Find **PR_Operational_Merged** — *Referral, appointment, treatment authorisation
   and payment*.
3. Click **Start process**.
4. In the variables box, add one variable and start:

   | Name | Type | Value |
   | --- | --- | --- |
   | `patientId` | String | any identifier, e.g. `STU-001` |

   `documentsComplete` is optional here — the first form sets it anyway.
5. Click **Start**.

The instance appears in the list. Open it: this is the **diagram view** you will
come back to. Nothing has run yet until the first task is completed, so the
running activity is *Receive and register the referral*.

> Every one of the seven processes can be started this way, including `PR_ReferringOrganisation`, the collaborating referring-organisation process. `PR_Operational_Merged`
> is the long one and is the walkthrough below; `PR_Landscape` and
> `PR_ReferralToAuthorisation` are the short strategic ones; `PR_EnquiryHandling`,
> `PR_TreatmentToAftercare` and `PR_ManagementReporting` are separate processes in
> the same file as `S3`.

---

## Stage 2 — work the forms in Tasklist

Open `http://127.0.0.1:8080/tasklist` (same login). Only tasks belonging to your
instance are shown; if other people are also running instances, filter by process
instance or just work the ones you started.

For **every** task: click the task in the list, click **Assign to me** on the
right, fill the fields below, then click **Complete Task** at the bottom right.

| # | Task | What to enter |
| --- | --- | --- |
| 1 | Receive and register the referral | tick **All expected supporting documents available?** |
| 2 | Check referral documentation completeness | tick the same box |
| 3 | Perform the clinical review of the referral | **Referral decision** = `accepted` |
| 4 | Record the referral decision, rationale and responsible clinician | **Referral decision** = `accepted` · leave **Destination service** empty |
| 5 | Forward the accepted referral to the Outpatient Bookings Team | nothing to fill — just Complete |
| 6 | Receive and validate the booking request | **Referral urgency** = `routine` |
| 7 | Select and book the new patient appointment | tick **Appointment due within the next 14 days?** · **Appointment reference** = `APT-0001` |
| 8 | Confirm the booking and record the appointment reference | **Appointment reference** = `APT-0001` again |
| 9 | Telephone the patient to confirm attendance | nothing to fill |
| 10 | Record the contact attempt and its outcome | tick **Patient confirmed the appointment?** |
| 11 | Deliver the new patient consultation and discuss treatment | tick **Patient consents to proceed with treatment?** |
| 12 | Record the patient consent to treatment | nothing to fill |
| 13 | Create the authorised Treatment Booking Request | tick **Request completed and authorised by a clinical professional?** |
| 14 | Validate the authorised request and confirm resource requirements | nothing to fill |
| 15 | Determine the funding route for the treatment | **leave Funding approved unticked** · tick **Advance payment required before confirmation?** |
| 16 | Request funding approval or an additional payment | tick **Funding approved or no payment required?** |
| 17 | Determine the funding route for the treatment *(second visit)* | tick **Funding approved or no payment required?** |
| 18 | Record the funding organisation, authorisation reference and outcome | nothing to fill |
| 19 | Confirm the treatment schedule and issue the patient instructions | nothing to fill |

After form 19 the instance ends by itself. Between two forms the workers do the
automated steps, so a few seconds' wait between tasks is normal.

### Why step 15 must be "not approved"

The funding route is a **loop**: not approved -> request approval -> decide again.
Walking it once through the loop exercises the branch the case study describes. If
you tick "Funding approved" on the very first visit, the process skips the loop and
you get 16 forms instead of 19 — still a valid run, just a shorter one.

### Do not blank a field

A Camunda Form submits **every field it renders**, including ones you leave empty.
An empty field overwrites that variable in the process with an empty string. This
is not theoretical: it is how `appointmentReference` was wiped during development
by the next task's form, which then failed a worker with
`missing mandatory input 'appointmentReference'`. So:

* carry `appointmentReference` = `APT-0001` into **both** form 7 and form 8;
* never clear `patientId` (it arrives pre-filled — leave it as it is).

---

## Stage 3 — check the run in Operate

Back in Operate, open your instance:

1. **Diagram** — every activity you completed is green, the sequence you actually
   took is highlighted. This is the "diagram ran" view.
2. **Variables** — `patientId`, `referralDecision`, `appointmentReference`,
   `suitableSlotFound`, `treatmentCapacityConfirmed`, `fundingApproved`,
   `paymentStatus` and the audit fields the workers wrote
   (`lastAutomatedActivity`, `lastAutomatedAt`, `episodeId`).
3. **Incidents** — should be **empty**. One incident means a worker rejected a job
   or a value was missing.
4. The instance state should read **Completed**.

---

## If something goes wrong

| Symptom | Cause | Fix |
| --- | --- | --- |
| Start process fails / red toast | cluster is not running | Stage 0 step 1 |
| The start button is missing for a process | that model has no plain start event | already fixed — all six have one; redeploy |
| Process parks after a form, nothing happens | worker fleet not running | Stage 0 step 3 |
| An incident says `missing mandatory input ...` | a field was left blank | re-run and fill it; the table above lists every field that matters |
| Task list empty | you are looking at another user's tasks, or the instance has not been started | check Operate for the instance state |
| Tasklist asks you to log in again | session expired | log in `demo` / `demo` |

To start a clean run, start another instance from Operate with a **new**
`patientId`; the old instance can stay or be cancelled from Operate.
