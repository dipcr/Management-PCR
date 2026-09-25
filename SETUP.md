# Setup Guide

Getting D-IPCR running, from a fresh clone to a working system with data in it.

Three situations are covered — pick the one you are in:

| Situation | Go to |
|---|---|
| Joining the team, database already exists | **Part 1** only |
| Setting up a brand-new database | **Part 1**, then **Part 2** |
| Resetting for a clean test run | **Part 3** |

---

## Part 1 — Run the app

### 1.1 Requirements

- **Python 3.10+** (developed on 3.14)
- Access to the team's MySQL database, or a local MySQL 8 instance

### 1.2 Clone and install

```bash
git clone <repo-url>
cd Management-PCR
python -m venv venv
```

Activate it — `venv\Scripts\activate` on Windows, `source venv/bin/activate` elsewhere — then:

```bash
pip install -r requirements.txt
```

### 1.3 Create your `.env`

Copy `.env-example` to `.env` and fill it in. **`.env` is gitignored and never committed**,
so ask a teammate for the values — they are not in the repo.

```
DB_HOST=...
DB_PORT=...
DB_NAME=ipcr_db
DB_USER=...
DB_PASSWORD=...
SECRET_KEY=...
```

`SECRET_KEY` signs the login cookie. Any long random string works for development, but
everyone sharing a database should **not** share a key in production.

### 1.4 Run it

```bash
python run.py
```

Open <http://127.0.0.1:5000>. If the login page appears, the app is running and can reach
the database.

**If it fails to start**, the error usually says which of these it is:

| Message | Cause |
|---|---|
| `Unknown database 'ipcr_db'` | The database does not exist — go to Part 2 |
| `Access denied` | Wrong `DB_USER` / `DB_PASSWORD` |
| `Can't connect to MySQL server` | Wrong `DB_HOST` / `DB_PORT`, or the server is unreachable |
| `Unknown column '...'` | The database is behind on migrations — see 2.2 |

> **Sharing one database?** Then you are done — the schema and data are already there.
> Skip Part 2.

---

## Part 2 — Build a database from scratch

Only needed when there is no existing database to point at.

### 2.1 Create the schema

Restore a schema dump from a teammate, or from a backup produced by
**Admin → Backup**, which writes a `.sql` file of the whole database.

```sql
CREATE DATABASE ipcr_db CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

> Use `utf8mb4_0900_ai_ci`. Some tables were created with `utf8mb4_general_ci` by earlier
> migrations, and comparing a column of one collation against the other fails outright with
> *"Illegal mix of collations"*. `MIGRATION_group7.sql` contains the repair.

### 2.2 Apply the migrations, in order

Run each file in `old MDS/`. Order matters — later ones assume the earlier schema.

| # | File | What it adds |
|---|---|---|
| 1 | `MIGRATION_group3_1.sql` | Research targets get a description and duration |
| 2 | `MIGRATION_group4.sql` | IPCR categories, weights re-keyed to them |
| 3 | `MIGRATION_group5.sql` | Departments, teaching load config, extension durations |
| 4 | `MIGRATION_group7.sql` | `is_admin_function` + backfill, collation repair |
| 5 | `MIGRATION_group8.sql` | Rating period, institution settings, signatories, remarks |
| 6 | `MIGRATION_group9.sql` | `target_description`/`target_duration_value`/`target_duration_unit` on `tbl_ret_assignments` |
| 7 | `MIGRATION_group10.sql` | `tbl_ipcr_approval_notifications` — tracks Tier 1/2 email dispatches for idempotency |
| 8 | `MIGRATION_group11.sql` | `is_auto_description` tracking (auto-mirrored vs. customized target text) across drafts, allocations, RET tables, committed targets |
| 9 | `MIGRATION_group12.sql` | Widens `tbl_ipcr_categories.designation_type` to add a `'Master Indicators'` scope for Admin dashboard grouping |
| 10 | `MIGRATION_group13.sql` | RET Menu lock flag — moves Extension config into `tbl_ret_rules`/`tbl_ret_rule_indicators`, replacing the old one-time-lock table |
| 11 | `MIGRATION_group14.sql` | Drops four dead, zero-reference, zero-row tables |
| 12 | `MIGRATION_group15.sql` | Repairs orphaned review-item rows and adds the FKs (draft_id, indicator_id) that prevent recurrence |
| 13 | `MIGRATION_group16.sql` | Column cleanup; drops `tbl_draft_targets.manager_feedback` (zero references, zero non-empty values) |
| 14 | `MIGRATION_group17.sql` | Drops `tbl_co_authors` — co-author claiming removed from scope |
| 15 | `MIGRATION_group18.sql` | Drops `tbl_ret_extension_distribution` and redundant direct `term_id` FKs to `tbl_academic_terms` (term now resolved via indicator) |
| 16 | `MIGRATION_group19.sql` | Gives `tbl_audit_logs.actor_id` a real FK to `tbl_employee_profiles` |
| 17 | `MIGRATION_group20.sql` | Gives `tbl_ret_assignments.assigned_by` a real FK |
| 18 | `MIGRATION_group21.sql` | Composite UNIQUE `uq_academic_terms_year_semester` on `tbl_academic_terms (academic_year, semester)` — ⚠ **listed for completeness, do not run as-is** (see note below) |
| 19 | `MIGRATION_group22.sql` | `tbl_academic_terms.faculty_config_reviewed` — per-term flag behind the Admin dashboard's recheck-Faculty-Configuration banner |

> ⚠ `MIGRATION_group21.sql` is **not applied** on the shared development database, and must not
> be run blindly. `tbl_academic_terms` still holds duplicate `(academic_year, semester)` groups,
> so the `UNIQUE` constraint is rejected outright. The file's header names the affected groups;
> decide which `term_id` to keep, re-point the child rows at it, and only then run the
> `ALTER TABLE`. Everything else in this table is safe to apply in order.
>
> `MIGRATION_update_emails.sql` is **not** part of this sequence — it's a one-off data fixup that
> overwrites specific seeded test accounts' emails with particular addresses, not a schema
> change. Skip it unless you know it applies to your own seeded accounts.

In **DBeaver**, open the file and use **Execute Script** (`Alt+X`) — not Execute Statement
(`Ctrl+Enter`), which runs only the statement under the cursor.

Or from the command line:

```bash
mysql -h HOST -P PORT -u USER -p ipcr_db < "old MDS/MIGRATION_group4.sql"
```

**Check it worked** — this should return no rows:

```sql
SELECT TABLE_NAME, TABLE_COLLATION FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'ipcr_db' AND TABLE_COLLATION <> 'utf8mb4_0900_ai_ci';
```

### 2.3 Create the first Admin

A brand-new database has no accounts, and **registration cannot create one** — it *claims*
an existing profile that an Admin has to have made first. So the first account is written
directly:

```bash
python bootstrap_admin.py
```

It prompts for employee ID, name, email and password. The password is typed at a prompt,
never passed as an argument, and must satisfy the same policy the registration form uses:
8+ characters, upper, lower, digit, special, no spaces.

The script refuses if an Admin already exists — pass `--force` only if you deliberately
want a second one.

> There's a second, automatic bootstrap path used by Docker: `app/setup.py:bootstrap_admin()` runs
> unconditionally at the top of every `run.py`/`wsgi.py` startup. If `ADMIN_EMAIL` and
> `ADMIN_PASSWORD` are both set in the environment, no Admin exists yet, and the password passes
> the same policy check as registration, it silently creates the first Admin from those two env
> vars — see `docker-compose.yml`. It's a no-op otherwise (missing vars, or an Admin already
> exists), but if you set those two vars in a local `.env` for some other reason, don't be
> surprised by an Admin account you didn't explicitly create.

### 2.4 Add everyone else

Log in as the Admin, then **HR Roster**:

- **Add Faculty** one at a time, or **Import CSV** for a batch.
- Set each person's **designation** carefully — it is not the same as their login role:

| `designation` | Effect |
|---|---|
| `Regular Faculty` | Rated on the 50/40/10 weight table |
| `Program Chair`, `RET Chair`, `Dean`, `Designated Faculty` | Rated on 75/25, and gets a **My IPCR** section |
| `Admin` | System account, no IPCR |

Then under **System Security**, set each person's **system role** — which dashboard they
land on at login.

> Getting `designation` wrong is the most common setup mistake. A Program Chair whose
> designation says `Regular Faculty` will silently have no My IPCR, and will be rated
> against the wrong weights.

### 2.5 Everyone claims their account

Each person goes to `/register` and enters their **employee ID number**, email and a
password. That claims the profile the Admin created. They cannot register without one.

### 2.6 Configure the system

As Admin, in this order:

1. **Term Configuration** — open a term; set the **Rating Period** dates (they print on the IPCR).
2. **Institution Setup → Departments** — the programs targets route to. Each department
   name must match what you put in faculty **specialization**.
3. **Institution Setup → Teaching Load** — hours and duration per designation.
4. **Institution Setup → Printed IPCR** — college name, and who signs each block. Enter the
   **Head of Office** name, or those signature lines print blank.
5. **Criteria** — the target types. If you are rebuilding these, set the **Slug** field by
   hand: the code matches on `instruction`, `research`, `extension`, `support`,
   `administrative`, `custom`. A generated slug like `a_instructions` breaks routing silently.
6. **Criteria → Category Management** — which target types belong to which IPCR category,
   per designation.
7. **Criteria → Weight Allocation** — 50/40/10 for Regular, 75/25 for Designated. Must total 100.
8. **Master Indicators** — the DPCR target pool, imported from a previous term or added by hand.

The system is now ready for the Dean to cascade quotas. `TEST_SCRIPT.md` walks the whole
cycle from there.

---

## Part 3 — Reset for a clean test run

Run `old MDS/RESET_for_clean_test.sql`. It clears terms, targets, evidence, reviews and
scores, and keeps accounts and configuration.

**Read the notes in that file before editing it.** Two things do not come back on their own:

- **Accounts** — clearing them locks everyone out until you run `bootstrap_admin.py` again.
- **Target types** — the code matches exact slugs; rebuilding them through the UI needs the
  Slug field filled in by hand.

Signatories *are* self-healing — opening Institution Setup recreates the standard blocks if
they are missing, though the names need re-entering.

Uploaded files are not deleted by the reset. For a genuinely clean state:

```bash
rm app/uploads/evidence/*.pdf
```

---

## Working on a shared database

Most of the team points at one MySQL server, which has consequences:

- **Migrations run once, for everybody.** If a teammate has applied them, you do not.
- **Configuration is global.** Only one term can be active; if someone opens a new one,
  everyone is on it.
- **Some actions are one-way.** Extension distribution locks for the term. RET rank rules
  are deleted and rewritten when saved.

For a test round, have **one person** do the setup (Admin → Dean → Chairs), then everyone
else works in parallel as **different faculty accounts**.

---

## Troubleshooting

**"My IPCR" is missing for a chair or the Dean**
Their `designation` on the roster is wrong. It must not be `Regular Faculty`.

**A faculty's Core Functions only shows the teaching load**
Their Program Chair has not allocated instruction to them. In Phase C the chair's list
includes the Dean and chairs, not just regular faculty.

**Targets are not routing after rebuilding criteria**
The slug is wrong. Check `SELECT slug FROM tbl_target_categories` against the six the code
expects.

**The printed IPCR has blank signature lines**
The Head of Office name is not set in Institution Setup → Printed IPCR.

**The IPCR header shows `__________` instead of a period**
The term has no Rating Period dates. Set them in Term Configuration.

**`Illegal mix of collations`**
Run the collation-repair section of `MIGRATION_group7.sql`.
