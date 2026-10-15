# Database integration and persistence

Item 1 of the review list: connect a database and make business data save and read back.
This records what changed, how it was verified, and what the earlier release said about it.

## What the earlier release did, and why it was not enough

The workers already kept the right records and the right relationships, in
`support/HospitalStore` and `support/OperationsLog`:

- an **episode handle** that ties patient, referral, appointment, funding, payment and
  refund together, which is the end-to-end correlation REQ-44 asks for;
- an **appointment index** so the same appointment cannot be confirmed twice;
- a **payment check** so the same charge cannot be taken twice;
- an **append-only audit log** with actor, instant, action and episode, and no update or
  delete operation on its surface.

All of it lived in maps in the process, and both classes said so in their own Javadoc:
*"It is deliberately not a database. Nothing here survives a restart, and the acceptance
evaluation says so."* That statement is now obsolete, and the documents that repeat it
have been corrected.

## What changed

| File | Change |
| --- | --- |
| `04_Java_Worker/pom.xml` | H2 added as an embedded database; Jackson pinned to the version the Zeebe client already brings in |
| `support/Database.java` | new: opens the embedded H2 file, creates the schema on first use, hands out one connection |
| `support/HospitalStore.java` | now backed by tables instead of maps; public API unchanged |
| `support/OperationsLog.java` | now backed by a table; public API unchanged |
| `PersistenceCheck.java` | new: writes records in one process and reads them back in another |

The public surface of both stores is unchanged, so **no worker had to be rewritten**. That
is deliberate: the item asked for integration and persistence, and rewriting 26 workers
would have added risk without adding evidence.

Schema, created on first use:

| Table | Holds |
| --- | --- |
| `record` | business records, keyed by episode, collection and record key, with the payload as JSON so new business fields need no migration |
| `appointment_index` | the appointment de-duplication index, now enforced by a primary key |
| `attempt_counter` | retry counts, incremented in a single statement so concurrent retries cannot lose a count |
| `audit_log` | the append-only audit trail, with the instant set at write time |

## One connection, deliberately

H2 normally allows several connections to one file database. Acquiring its file lock is
not permitted in every environment, and where the lock cannot be taken H2 opens the
database **read-only**. Two consequences follow, and both were observed here rather than
assumed:

1. **Within one process**, a second connection is read-only, so `Database` holds a single
   connection for the life of the process and serialises access to it with `inConnection`.
   This is a design choice and it works everywhere.
2. **Across processes**, in this sandbox the H2 file lock cannot be acquired at all, so a
   database file that already exists is opened **read-only** by every later process,
   including a restarted worker. Measured directly: a first `PersistenceCheck write` into a
   fresh directory reports `RESULT: PASS`, and a second one against the same file fails
   with *"The database is read only"*. `ACCESS_MODE_DATA=rw`, `FILE_LOCK=NO` and
   `FILE_LOCK=SOCKET` were each tried and none of them changes it - `FILE_LOCK=SOCKET` is
   worse, it makes even the first connection read-only.

   This is an environment restriction, not a property of the design. On an ordinary
   Windows, macOS or Linux machine the lock is available and a restarted worker writes
   normally. It does not affect the item being demonstrated, because **saving and reading
   back** is exactly what the two-process check verifies: the writing process exits, and a
   fresh JVM reads everything it stored.

   Operationally it does mean that, in this sandbox, the database file must be cleared
   before the worker fleet starts if the fleet is to write at all:

   ```powershell
   Remove-Item -Recurse -Force data      # only needed here, before starting the workers
   ```

## How to reproduce and verify

```powershell
mvn -o -f 04_Java_Worker/pom.xml package
java -cp 04_Java_Worker/target/hospital-external-workers-1.0.0.jar `
     uk.ac.uwe.hospital.PersistenceCheck write     # process 1
java -cp 04_Java_Worker/target/hospital-external-workers-1.0.0.jar `
     uk.ac.uwe.hospital.PersistenceCheck read      # process 2, fresh JVM
```

`write` and `read` are separate JVM invocations. The second process shares nothing with
the first except the database file, so anything it can read survived a restart. The
recorded output is in `05_Test_Evidence/persistence/`.

| Check in the reading process | Result |
| --- | --- |
| referral `REF-PERSIST-1` survived with its patient id | PASS |
| appointment `APPT-PERSIST-1` survived | PASS |
| the persisted payment still trips the duplicate-payment check | PASS |
| the appointment index still recognises the booking | PASS |
| the attempt counter still reads 2 | PASS |
| the audit log kept its 2 entries, indexed by episode | PASS |
| the audit log still exposes no update or delete operation | PASS |

`PersistenceCheck dump` prints everything currently stored, grouped by episode, which is
how an end-to-end run is inspected after the workers have processed a real process
instance.

## The 41 unit tests

`mvn -o -f 04_Java_Worker/pom.xml test` still passes 41 of 41. The tests run against an
in-memory database of the same schema, configured in the surefire plugin, so they never
touch the file the workers use. Their passing is the evidence that persistence did not
change behaviour: the retry semantics, the duplicate-payment rule and the audit surface
are all asserted by tests that predate this change.

## Known limits, stated rather than hidden

- H2 embedded is suited to a single-node demonstration, not to a production deployment.
  A production system would point `hospital.db.url` at a server database; the code uses
  plain JDBC throughout, so that is a URL and driver change rather than a rewrite.
- Only one process may write at a time. A second process opening the same file gets
  read-only access, which is fine for verification but means two worker fleets cannot
  share one database file.
- `REQ-37`'s access-control half - that ordinary users cannot edit audit records - is
  addressed by item 2 (RBAC) at the platform level and by the absence of any mutating
  method on the audit API, not by database permissions on this table.
