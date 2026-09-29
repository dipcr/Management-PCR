# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

D-IPCR: a Flask + MySQL capstone implementing the Philippine SPMS/IPCR (Strategic Performance
Management System / Individual Performance Commitment and Review) form for an academic college.
It routes faculty performance targets through a multi-role cascade — Admin → Dean → Program
Chair/RET Chair → Faculty — then multi-stage review, locking, evidence upload, scoring, and a
printable IPCR.

## Running it

```bash
python -m venv venv
venv\Scripts\activate          # Windows; `source venv/bin/activate` elsewhere
pip install -r requirements.txt
python run.py                  # http://127.0.0.1:5000
```

Requires a `.env` (copy `.env-example`) with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `SECRET_KEY`. There is no test runner or linter configured — `TEST_SCRIPT.md` is
a manual, phase-by-phase QA checklist covering all six roles; run through it by hand against a
real database after any change to the cascade/review/scoring flow.

Useful scripts:
- `python bootstrap_admin.py` — writes the first Admin account directly (interactive prompt for
  password; registration alone cannot create the first account, only claim one an Admin made).
- `python run_migration.py "old MDS/MIGRATION_groupN.sql"` — applies one migration file from
  `.env` connection settings, stopping at the first error.

Full fresh-clone-to-running-system steps, including migration order and common first-run errors,
are in [SETUP.md](SETUP.md). Read it before touching schema or term-lifecycle code — it documents
non-obvious one-way operations (extension distribution locks per term, RET rank rules are
deleted-and-rewritten on save, only one term can be active at a time on the shared dev database).

## Schema changes

There is no ORM and no migration framework. Schema changes are hand-written `.sql` files added to
`old MDS/` (despite the name, this is where migrations still live) and run once against the
shared database — coordinate before applying one, since everyone on the team points at the same
MySQL instance. New tables/columns must be added to a new numbered `MIGRATION_groupN.sql` file,
not applied ad hoc.

## Architecture

### Blueprints and roles

Six Flask blueprints under `app/routes/`, each mounted at its own prefix and mapping 1:1 to a
login role (`session['role']`, uppercase): `auth` (`/`), `admin` (`/admin`), `faculty`
(`/faculty`), `dean` (`/dean`), `prog_chair` (`/prog_chair`), `ret_chair` (`/ret_chair`),
`designated` (`/designated`). Each route module has a matching model module under `app/models/`
holding the actual query/business logic — routes stay thin. `app/decorators.py` has
`@role_required(role)` for the six dashboards and `@designated_ipcr_required` for the shared
Designated Faculty IPCR flow.

**`designation` vs `system_role` — the most common source of bugs in this codebase.** They are
orthogonal:
- `designation` (`tbl_employee_profiles.designation`) is the person's *job title*
  (`Regular Faculty`, `Designated Faculty`, `Program Chair`, `RET Chair`, `Dean`, `Admin`). It
  decides whether they have an IPCR of their own and which weight table scores it. See
  `resolve_designation_type()` / `is_designated()` in `app/models/criteria.py`.
- `system_role` (`session['role']`) decides which dashboard/blueprint they land on at login
  (`FACULTY`, `DESIGNATED_FACULTY`, `PROGRAM_CHAIR`, `RET_CHAIR`, `DEAN`, `ADMIN`).

A Program Chair, RET Chair, or Dean is a *designated faculty member* — they log into their own
role-specific dashboard (`system_role`) but their personal IPCR is scored and rendered through the
same shared `/designated/` flow used by plain Designated Faculty, gated by `designation` via
`@designated_ipcr_required`, not by `system_role`. `app/navigation.py` (`HOME_NAV`) lets that
shared page render each visitor's own dashboard sidebar as "back home" links instead of replacing
it. When adding a feature to "designated faculty," check whether chairs/Dean need it too — they
usually do.

### The cascade and review pipeline

1. **Admin** opens a term (`app/models/term.py`), defines master indicators
   (`app/models/indicator.py`) grouped into target categories (`app/models/criteria.py`).
2. **Dean** cascades quotas per specialization/program into `tbl_cascaded_quotas`
   (`app/models/dean.py`).
3. **Program Chair** distributes Instruction/Support quotas to faculty in their specialization
   (`tbl_draft_allocation`); **RET Chair** configures Research/Extension rank-based rules and
   per-faculty eligibility (`app/models/ret_chair.py`).
4. **Faculty** assemble and submit a draft IPCR (`tbl_draft_targets`) — Regular Faculty via
   `app/models/faculty.py`, Designated Faculty (including chairs/Dean, on their own IPCR) via
   `app/models/designated.py`.
5. **Review**: RET-eligible submissions go through RET Chair review
   (`tbl_ipcr_ret_review`) before Program Chair review (`tbl_ipcr_chair_review`); non-RET
   submissions go straight to the Program Chair. `get_overall_ipcr_status()`
   (`app/models/connection.py`) derives the current pipeline state dynamically from these tables
   rather than storing a status column — read it before changing review-stage logic, since it
   encodes the full state machine.
6. **Lock**: an approved IPCR is locked, copying `tbl_draft_targets` into
   `tbl_committed_targets`.
7. **Evidence**: PDF uploads per committed target (`tbl_evidence_repo`), verified by the
   Program Chair / RET Chair.
8. **Scoring**: `app/models/scoring.py` computes Q/E/T (Quantity/Efficiency/Timeliness) per target,
   rolls up into weighted IPCR categories, and produces a Final Weighted Rating + Adjectival
   Rating band.
9. **Print**: `app/models/ipcr_form.py` + `app/templates/ipcr_print.html` assemble the printable
   IPCR (landscape, matches the official SPMS form layout for both Regular and Designated
   faculty).

`flow.md` has a more detailed (though now slightly stale in places — cross-check against code)
phase-by-phase walkthrough with route/line references and a mermaid diagram of the whole cascade.

### In-app help

`app/help_content.py` holds the per-role help: the "About this page" drawer (a floating button in `base.html`, keyed by the active `nav-…` section id) and the User Manual page at `/help/` (`app/routes/help.py`). A role with no entry there gets neither. Section ids must be kept in step with the dashboards by hand, like `app/navigation.py`.

### Scoring and weights

Two weight tables, selected by `resolve_designation_type()`:
- **Regular Faculty**: 50% Strategic Priorities / 40% Core Functions / 10% Support Functions.
- **Designated Faculty** (incl. chairs/Dean): 75% Strategic Priorities & Support Functions / 25%
  Core Functions.

Which target-category a target type rolls into differs *by designation type* — e.g. Instruction is
Strategic Priorities for Regular Faculty but Core Functions for Designated Faculty — so that
mapping lives in `tbl_ipcr_category_types`, not on the category itself. The `is_admin_function`
flag on `tbl_draft_targets`/`tbl_committed_targets` separately distinguishes a designated faculty
member's own teaching work (Core Functions) from their oversight/cascaded/pool-selected work
(Strategic Priorities/Support), independent of the target's own type — a target forced into the
admin category by this flag overrides the normal category mapping.

Category display order matters for both the live dashboard summaries and the printed IPCR (must
read Strategic Priorities → Core Functions → Support Functions, not alphabetical) — sort by
`display_order`/`category_order`, never by category name.

### Target categories (`tbl_target_categories`)

Six built-in `slug` values that ~20+ places in the code match on exactly: `instruction`,
`research`, `extension`, `support`, `administrative`, `custom`. `review_lane` on each category
routes it through either the Program Chair (`CHAIR`) or RET Chair (`RET`) review pipeline. If
rebuilding categories through the Admin UI, the Slug field must be set by hand to one of these six
— an auto-generated slug breaks routing silently with no error.

### Database access

`app/models/connection.py` holds a single `MySQLConnectionPool` (`init_db_pool()`, called once at
app startup in `app/__init__.py`), initialized with **`autocommit=True`**. This means
`conn.rollback()` is a no-op — there is no way to speculatively run a mutating function against
the live pool and undo it. Any manual verification of a mutating code path needs either a real,
intentional commit (and cleanup afterward) or a `SELECT`-only check; do not rely on rollback for
safety. `get_db_connection()` pulls from the pool; callers are responsible for `cursor.close()` /
`conn.close()`. `timed_query()` is a helper that executes, logs slow queries (>0.3s), and returns
rows as `dict`s.

`tbl_master_indicators.indicator_id` is unique per term in practice (verified, not enforced by a
visible constraint), so queries keyed by `indicator_id` are implicitly term-scoped even without an
explicit `term_id` filter — don't assume a missing `term_id` join is a bug without checking this
first.

### Auth

Session-based (`session['user_id']`, `session['role']`, `session['specialization']`,
`session['designation']`), no JWT/OAuth. Passwords are bcrypt-hashed (`app/auth.py`). Registration
(`/register`) only *claims* a profile an Admin already created (matches on
`employee_id_number`) — it cannot create a new account from scratch. Failed logins get a 0.5s
sleep as a timing/brute-force mitigation.
