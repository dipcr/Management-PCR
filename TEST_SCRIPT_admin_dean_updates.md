# Regression Test Script — Admin Faculty Config Guards & Dean Dashboard Clarity (2026-09-21)

Scoped to this session's changes only, not a replacement for `TEST_SCRIPT.md`. Each phase is a
short, self-contained check tied to one specific change — run them in any order except where
noted. Automated coverage for the same logic lives in
`test_faculty_config_and_dean_updates.py`; this script is for a human walking the actual UI.

**Legend:** `[ ]` not tested · `[/]` passed · `[*]` passed with a comment · `[-]` skipped
Add notes under any item as `:your comment`.

---

## Accounts needed

| Role (`system_role`) | Designation on the roster | Used in |
|---|---|---|
| ADMIN | `Admin` | 1, 2, 3, 4 |
| DEAN | `Dean` | 5, 6 |

No second account is required. You do need at least one specialization on the live roster that
**already has an active Program Chair** — check the Faculty Configuration table first and note
which specialization and who holds it; Phase 1 needs that name.

---

## Phase 1 — Admin: block a duplicate Program Chair / RET Chair / Dean (single edit)

- [ ] Admin dashboard → Faculty Configuration. Confirm which specialization already has an
  active Program Chair (e.g. from the roster table's DESIGNATION column).
- [ ] Add a **new** faculty profile (or edit an existing Regular Faculty) and set their
  **Designation** to `Program Chair` and **Specialization** to that same, already-taken
  specialization. Save.
  **CHECK:** save is rejected with an error naming the person who already holds the role for
  that specialization (e.g. *"Cannot save: Jane Cruz (2222) is already the Program Chair for WST
  Program..."*) — no new/changed row appears in the roster table.
- [ ] Repeat the same profile, but this time set Designation to `RET Chair` (any
  specialization). **CHECK:** rejected the same way, naming the current RET Chair — this role
  has no specialization scoping, so it blocks regardless of which specialization you pick.
- [ ] Repeat with Designation `Dean`. **CHECK:** rejected the same way, naming the current Dean.
- [ ] Now set Designation to `Regular Faculty` (or `Designated Faculty`) with that same
  specialization. **CHECK:** saves normally — non-chair designations never conflict, even in a
  specialization that already has a Program Chair.
- [ ] Open the **existing** Program Chair's own profile (the one already holding the role) and
  re-save it unchanged (or edit an unrelated field like Academic Rank). **CHECK:** saves
  normally — a person is never blocked by their own existing role.

---

## Phase 2 — Admin: same guard on CSV bulk import

- [ ] Prepare a CSV with the standard roster columns
  (`employee_id_number,first_name,last_name,college,assigned_program,specialization,academic_rank,employment_status,leave_status,designation`)
  containing **two rows** with `designation=Program Chair` and the **same** `specialization`
  value (a specialization not already taken, so this exercises a same-file conflict).
- [ ] Faculty Configuration → **Upload CSV**. **CHECK:** import completes, but the summary
  flash reports the second row skipped due to a role conflict, naming both employee IDs — only
  the first row's profile is created.
- [ ] Prepare a second CSV with one row: `designation=Program Chair`, specialization = the
  specialization from Phase 1 that already has a Program Chair. Import it. **CHECK:** that row
  is skipped (reported in the conflict summary) and no new/changed profile appears for it.
- [ ] Prepare a CSV with several `Regular Faculty` rows all sharing one specialization
  (including one that already has a Program Chair). Import it. **CHECK:** all rows import
  cleanly, 0 conflicts reported.

---

## Phase 3 — Admin: designation change syncs the person's login role

Needs a faculty member who has **already claimed their account** (can log in) and is currently
`Regular Faculty`.

- [ ] Faculty Configuration → edit that person, change Designation to `Program Chair` (pick a
  specialization with no existing chair), Save. **CHECK:** the success flash mentions the login
  role was synced (e.g. *"...Login role synced to PROGRAM_CHAIR."*).
- [ ] Have that person log out and back in (or start a fresh session). **CHECK:** they now land
  on the **Program Chair dashboard**, not the Faculty dashboard.
- [ ] Change their Designation back to `Regular Faculty`, Save, and have them log in again.
  **CHECK:** they now land back on the **Faculty dashboard** — demotion takes effect too.
- [ ] Add a **brand-new** profile (not yet registered/claimed) with Designation `Program
  Chair`. **CHECK:** saves normally with no role-sync mention in the flash (nothing to sync yet
  — the correct role is assigned automatically when they claim their account via `/register`).

---

## Phase 4 — Admin: "recheck Faculty Configuration" banner on term open

- [ ] Admin dashboard, any tab. **CHECK:** if the active term has not yet been marked
  reviewed, a warning banner is visible at the top of **every** tab (not just Overview),
  reading roughly *"New term opened: <year> (<semester>)... Recheck Faculty Configuration..."*.
- [ ] Click **Review Now** on the banner. **CHECK:** it jumps straight to the Faculty
  Configuration tab.
- [ ] Go back to the banner and click **Mark as Reviewed**. **CHECK:** the banner disappears
  and stays gone on every tab, including after a full page reload.
- [ ] Admin → Term Configuration → open a **new** term (different Academic Year/Semester).
  **CHECK:** the banner reappears for the newly-opened term — each term gets its own
  reviewed/unreviewed state, it doesn't stay dismissed forever.
- [ ] *(Optional cleanup)* Mark the new term reviewed too, or leave it — either is fine to hand
  off.

---

## Phase 5 — Dean: Quota Cascading button relabel (Silent → Dean Only / To Chairs → Share with Chairs)

Needs a term whose College-Wide quotas have **not** been cascaded yet (a fresh term works well
here — you can use the one opened in Phase 4).

- [ ] Dean dashboard → Institutional Quota Cascading, College-Wide column for any indicator.
  **CHECK:** the two buttons read **"Dean Only"** and **"Share with Chairs"** — not
  "Silent"/"To Chairs".
- [ ] Hover each button. **CHECK:** a tooltip explains the consequence in plain language (Dean
  Only = stays with you, Program Chairs never see it; Share with Chairs = Program Chairs can
  see and sub-allocate it).
- [ ] Hover the small info icon next to the button pair. **CHECK:** it shows a combined
  explanation of both options.
- [ ] Set a mix of Dean Only / Share with Chairs across a few indicators and click **Cascade
  Institutional Targets**, confirming in the modal. **CHECK:** after the one-time lock, each
  College-Wide cell now shows a **read-only badge** reading "Dean Only" or "Shared with
  Chairs" (matching what you picked) — same relabeling applied to the locked view.
- [ ] Log in as the Program Chair for a specialization that had a **Share with Chairs**
  indicator. **CHECK:** that indicator is visible on their allocation screen. Confirm a **Dean
  Only** indicator from the same cascade is **not** visible to them anywhere.

---

## Phase 6 — Dean: "Specialization" column replaces "Program"

- [ ] Dean dashboard → **IPCR Draft Approval** (both Pending and Approved tables). **CHECK:**
  the column reads **"Specialization"**, and shows each person's actual specialization (varies
  row to row), not a single repeated program name.
- [ ] Dean dashboard → **Assign College-Wide Targets to Designated Faculty & Chairs**.
  **CHECK:** column reads "Specialization" with varying values.
- [ ] Dean dashboard → open any College-Wide indicator's **Distribution Progress** detail
  table. **CHECK:** column reads "Specialization" with varying values.
- [ ] Dean dashboard → **Final Evidence Verification** (all three tables: Pending, Approved
  Designated Faculty & Chairs, Approved Regular Faculty). **CHECK:** each reads "Specialization"
  with varying values, not the same program repeated down the column.

---

## Sanity check

- [ ] While exercising Phases 5–6, confirm nothing else on the Dean dashboard changed —
  quota totals, distribution progress bars, evidence verification actions (View/Review IPCR
  buttons) all still work exactly as before. Only the labels and that one column changed.
