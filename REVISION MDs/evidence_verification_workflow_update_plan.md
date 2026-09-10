# Implementation Plan: Evidence Modal Simplification & Regular-Faculty Evidence Verification Handoff

## 1. Scope (per Program Chair interview, verbatim intent)

1. **Evidence upload modal:** remove the Completion Status field entirely.
2. **Regular faculty evidence:** RET Chair no longer checks/verifies Research & Extension
   evidence for **regular faculty**. Program Chair now checks/approves **all** regular-faculty
   evidence (Instruction, Support, Research, Extension).
3. **RET Chair monitor:** once Program-Chair-approved, RET Chair must still be able to see
   regular faculty with Research/Extension targets and view their evidence, read-only.

**Explicitly out of scope:** Designated Faculty (including Program Chair/RET Chair/Dean's own
IPCR). Correction from an earlier draft of this plan: RET Chair does **not** currently verify any
designated faculty's evidence, including their own. Verified in code:
`get_designated_selectable_indicators()` (`app/models/designated.py:1-35`) shows only a
designation of exactly `'RET Chair'` can ever pick Research/Extension indicators — Program Chair,
plain Designated Faculty, and Dean never get R&E targets at all. And
`submit_designated_evidences()` (`app/models/designated.py:605-607`, comment verbatim): *"Every
Designated Faculty member -- plain or a Program Chair/RET Chair/Dean's own IPCR -- has their
evidence reviewed by the Dean, not a Program Chair; only Regular Faculty goes through
RET/Program Chair review first."* Every designated-faculty submission (including the RET Chair's
own) goes straight to `'Submitted to Dean'` and is approved/returned file-by-file only through
`/dean/verify_evidence` (`app/routes/dean.py:705-719`).

So RET Chair's evidence-verification role has **zero** legitimate remaining scope for designated
faculty — this isn't a workflow to preserve. §3 revises the design accordingly: RET Chair's
evidence section becomes exclusively about regular faculty, entirely read-only, no
pending/approved split. The one thing that *does* still need a designation check is
`enrich_faculty_verification_status()`'s internal `ret_finished` computation — not because RET
Chair reviews anything, but because Dean's own final-approval gate (`dean_approve_package`,
`app/routes/dean.py:757-765`) still requires every evidence file, R&E-categorized ones included,
to be explicitly reviewed (by the Dean) before letting a designated faculty's package through. If
the RET-gate were dropped globally rather than only for regular faculty, a chair whose entire IPCR
is R&E-only (the RET Chair's own oversight bucket) would trivially satisfy `chair_finished` — zero
non-R&E targets — and skip that check even with unreviewed evidence. See §3.B.3.

---

## 2. Current mechanics (verified against code, not assumed)

- `enrich_faculty_verification_status()` (`app/models/faculty.py:1031`) is the single shared
  function computing `WAITING_CHAIR` / `WAITING_RET` / `APPROVED` / `is_both_approved`. It's called
  from 4 places: `get_program_chair_evidence_faculty` (prog_chair.py, regular-faculty-only rows),
  `get_ret_chair_evidence_faculty` (ret_chair.py, **no designation filter today** — technically
  mixes regular + designated, see below), `get_dean_evidence_faculty` (dean.py, mixes both), and
  `dean_approve_package` (routes/dean.py:763, gates final Dean approval **only for designated
  faculty**).
- `get_ret_chair_evidence_faculty()` (`app/models/ret_chair.py:769`) has no designation filter, so
  it *can* surface a designated faculty row (in practice only the RET Chair's own R&E oversight
  targets, since no other designated faculty ever has R&E targets — see §1). But nobody is
  actually meant to act on that row through this dashboard: per `submit_designated_evidences()`
  (designated.py:605-607), designated-faculty evidence — the RET Chair's own included — is
  reviewed only by the Dean via `/dean/verify_evidence`, never by the RET Chair. The missing
  filter here looks like an oversight rather than a deliberate self-review path — worth closing
  as part of this change (§3.C.1).
- `/ret_chair/verify_evidence` (`app/routes/ret_chair.py:211`, `ret_chair_verify_evidence`) is the
  backend endpoint RET Chair uses to approve/return evidence. It has no ownership/designation
  check — whoever the evidence_id belongs to gets approved. Once regular faculty no longer route
  through it and designated faculty never legitimately did, this endpoint has no remaining caller.
- `prog_chair_faculty_evidence_details()` (`app/routes/prog_chair.py:238-244`) currently blanks
  `evidence_list` for R&E targets (`is_ret == True`), and `prog_chair_dashboard.html` renders a
  "Managed by RET Sector" badge instead of a working evidence viewer for those rows
  (lines ~1910-1911, ~1961-1962).
- `rate_timeliness()` (`app/models/scoring.py:249-270`) uses `completion_status` to hard-code
  Timeliness to 1 (`NOT_BEGUN`) or 2 (`PARTIAL_AT_DEADLINE`) specifically because the
  duration-ratio formula can't score those cases. `compute_target_rating()` already has a
  documented rule that a `None` T-score is silently dropped from the average rather than counted
  as a penalty (scoring.py:279-282) — the same trap applies if `completion_status` always
  becomes `'COMPLETED'` and `actual_duration_value` is left blank.
- The real function name is `save_accomplishment_details()` (`app/models/faculty.py:761`), not
  `save_faculty_accomplishment`.

---

## 3. Design

### A. Evidence upload modal — remove Completion Status
- `app/templates/faculty_dashboard.html` and `app/templates/designated_dashboard.html`: remove the
  completion-status `<fieldset>` (radios), `toggleCompletedInState()`, and all
  `input[name="completionStatus"]` references; `evidenceCompletedIn` duration stays directly
  editable; `saveAccomplishmentDetails()` always sends `completion_status: 'COMPLETED'`.
- `app/routes/faculty.py`, `app/routes/designated.py`: `completion_status` becomes optional,
  defaulting to `'COMPLETED'`.
- `app/models/faculty.py::save_accomplishment_details()`: default `completion_status` to
  `'COMPLETED'` when not provided.
- **Leave `app/models/scoring.py` untouched.** `NOT_BEGUN`/`PARTIAL_AT_DEADLINE` become
  unreachable via the UI, which is harmless dead code, not a bug. The blank-`actual_duration_value`
  edge case (§2) is instead handled by blocking submission rather than patching the scoring
  formula — see §3.D.

### B. Program Chair becomes sole approver of all regular-faculty evidence
1. **`app/routes/prog_chair.py::prog_chair_faculty_evidence_details()`**: delete the
   `if not is_ret: ... else: t['evidence_list'] = []` split (lines 238-244) — always call
   `get_evidence_by_target()`.
2. **`app/templates/prog_chair_dashboard.html`**: remove the `if (t.is_ret)` branches (~1910,
   ~1961) that render "Managed by RET Sector" / "RET Sector" badges — R&E targets get the normal
   "View Uploaded Evidence (N)" button and verification badge like any other target. Remove the
   "Waiting for RET" / "Approved by Chair (Waiting for RET)" badges (line ~1739) since they become
   unreachable for regular faculty once (3) below lands.
3. **`app/models/faculty.py::enrich_faculty_verification_status()`**: add a designation check —
   fetch `designation` for `emp_id` (one extra lookup, matches the existing per-row-query pattern
   already used in `get_dean_evidence_faculty`), and when the faculty member is **not**
   `is_designated()` (i.e. Regular Faculty), force `ret_finished = True` regardless of RET target
   evidence state, so `is_both_approved == chair_finished` and `WAITING_RET` never fires for them.
   When the faculty member **is** designated, keep today's dual-gate logic byte-for-byte. This is
   *not* about preserving a RET Chair review step (there isn't one, see §1) — it's so
   `dean_approve_package`'s own gate (routes/dean.py:764) still correctly requires every evidence
   file, R&E-categorized ones included, to be Dean-approved before a designated faculty's package
   clears. Dropping the RET check unconditionally would let an R&E-only IPCR (the RET Chair's own)
   trivially satisfy `chair_finished` with zero non-R&E targets and skip that check.
4. **`app/services/notification_service.py::send_evidence_submission_notification()`**: in the
   Regular Faculty branch, drop the RET Chair email — notify Program Chair only.

### C. RET Chair: read-only monitor for regular faculty, no verify role left at all
Since RET Chair never legitimately verifies designated faculty's evidence either (§1), this
section is simpler than an earlier draft assumed — no per-row branching needed, the whole
evidence-verification section becomes regular-faculty-only and permanently read-only.

1. **`app/models/ret_chair.py::get_ret_chair_evidence_faculty()`**: add the same designation
   exclusion `get_program_chair_evidence_faculty()` already uses (prog_chair.py:721-724) — filter
   out `'Designated Faculty'`, `'Program Chair'`, `'RET Chair'`, `'Dean'` — so this list is
   Regular Faculty only, closing the pre-existing gap where the RET Chair's own R&E oversight
   targets could otherwise surface here. Combined with §B.3, `is_both_approved` for every
   remaining row now just means "Program Chair approved everything" — collapse the two-list
   pending/approved split into a single list of faculty whose evidence is Program-Chair-approved
   (nothing left to be "pending" here, since Program Chair's own dashboard is where that happens).
2. **`app/routes/ret_chair.py::ret_chair_verify_evidence()`**: remove this route entirely — it has
   no remaining legitimate caller once (1) lands.
3. **`app/templates/ret_chair_dashboard.html`**:
   - Remove the pending table (§2220-2258) and its nav badge counter (§38-39) entirely.
   - Approved table (§2270-2327) keeps its shape but is now sourced from the single regular-faculty
     list from (1); rename heading/copy from "Approved RET Evidence Submissions" to reflect a
     monitor, not a queue (e.g. "Faculty with Research & Extension Targets — Evidence Monitor").
   - Evidence modal (`retFacultyEvidenceVerificationModal`, ~2341+): remove the Approve/Return
     buttons and the "Return Evidence" reason modal (~2703+) — every row is now view-only, files
     shown with preview/download only, same as Program Chair's own read-only handling of
     non-R&E-target evidence used to look before this change.
4. **`app/routes/ret_chair.py::ret_chair_faculty_evidence_details()`**: no route change needed —
   it already returns evidence files for inspection; only the template's action buttons go away.

### D. Block submission when a target has evidence but no computable Timeliness score
**Decision (resolves §5):** the system must not allow evidence to be submitted for Program Chair
review if any target has valid (non-returned) evidence uploaded but no Timeliness score can be
computed for it — i.e. `actual_duration_value` is blank. This prevents `rate_timeliness()`
returning `None` and `compute_target_rating()` silently dropping T from that target's Q/E/T
average (scoring.py:279-282) instead of scoring it. Enforced at submission time, not at upload
time, so faculty can save partial progress and come back — the gate only fires on the final
"Submit for Verification" action.

1. **`app/models/faculty.py::check_faculty_evidence_readiness()`** (line 891): for each target,
   after computing `valid_evs`, also flag it when `valid_evs` is non-empty *and*
   `t.get('actual_duration_value')` is `None`/blank. Collect these into
   `targets_missing_timeliness` (list of target_ids) and `has_missing_timeliness` (bool). Fold
   into the existing gate: `all_evidence_ready = (total_targets > 0) and not has_returned_evidence
   and not has_missing_timeliness`.
2. **`app/models/designated.py::check_designated_evidence_readiness()`** (line 542): same addition,
   mirroring its existing shape (it currently has no `has_returned_evidence` counterpart to model
   after for missing-duration, so add the field fresh); fold into its `all_evidence_ready`.
3. **`app/models/faculty.py::submit_faculty_evidences()`** (line 1000) and
   **`app/models/designated.py::submit_designated_evidences()`** (line 593): add a check mirroring
   the existing `has_returned_evidence` block — reject with a message naming which targets need a
   duration, e.g. *"Provide a completion duration for evidence already uploaded on: {target
   names} before submitting."*
4. **Templates** (`faculty_dashboard.html:765-767`, `designated_dashboard.html:872-873`): the
   Submit button already disables on `not evidence_readiness.all_evidence_ready` — extend the
   `title`/help text to mention the new case (currently only mentions "returned evidence").
5. **Edge case, not blocked by this rule:** a target whose `target_duration_value` itself is
   missing/invalid (an admin/chair target-setup gap, not something the faculty can fix by editing
   their own input) would also make `rate_timeliness()` return `None` even with a duration filled
   in. Since target duration is a required field at target creation, this is assumed not to occur
   in practice — not handled here to avoid trapping a faculty member with no way to unblock
   themselves; flag separately if it turns out to happen.

---

## 4. Summary of files changed

| File | Change |
| :--- | :--- |
| `app/templates/faculty_dashboard.html` | Remove completion-status radios; default `'COMPLETED'`. |
| `app/templates/designated_dashboard.html` | Same. |
| `app/routes/faculty.py`, `app/routes/designated.py` | `completion_status` optional, defaults `'COMPLETED'`. |
| `app/models/faculty.py` | `save_accomplishment_details()` default; `enrich_faculty_verification_status()` designation-aware RET bypass; `check_faculty_evidence_readiness()`/`submit_faculty_evidences()` block on missing Timeliness data. |
| `app/models/designated.py` | `check_designated_evidence_readiness()`/`submit_designated_evidences()` same missing-Timeliness block. |
| `app/routes/prog_chair.py` | Drop RET evidence blocking in `prog_chair_faculty_evidence_details()`. |
| `app/templates/prog_chair_dashboard.html` | Remove "Managed by RET Sector" / "Waiting for RET" branches. |
| `app/models/ret_chair.py` | `get_ret_chair_evidence_faculty()` excludes designated designations; single approved-only list. |
| `app/routes/ret_chair.py` | Remove `ret_chair_verify_evidence()` route entirely. |
| `app/templates/ret_chair_dashboard.html` | Remove pending table, nav badge, Approve/Return buttons, Return-reason modal; single read-only monitor table remains. |
| `app/services/notification_service.py` | Regular faculty evidence submission notifies Program Chair only. |

Not changed: `app/models/scoring.py` (see §3.A rationale), any `.sql` migration (no schema change
needed — `completion_status` column stays, just always written as `'COMPLETED'` going forward).

---

## 5. Resolved: blank-duration Timeliness gap

Decision: block evidence submission outright when a target has uploaded evidence but no
computable Timeliness score, rather than letting it through with a silently-dropped T. See §3.D
for the implementation (`check_faculty_evidence_readiness()` / `check_designated_evidence_readiness()`
/ the two `submit_*_evidences()` functions).

---

## 6. Verification plan

### Automated
```powershell
python -m py_compile app/routes/prog_chair.py app/routes/ret_chair.py app/routes/faculty.py app/routes/designated.py app/models/faculty.py app/models/designated.py app/models/ret_chair.py app/services/notification_service.py
```

### Manual (against a real DB, per `TEST_SCRIPT.md` conventions)
1. Regular faculty: upload evidence for an Instruction and a Research target — modal has no
   Completion Status field, duration is editable and saves.
2. Program Chair: sees and can Approve/Return evidence for both Instruction/Support **and**
   Research/Extension targets for a regular faculty member; once all approved, "Submit to Dean"
   is enabled without waiting on RET Chair.
3. RET Chair: the regular faculty member from (2) appears in the evidence monitor table, evidence
   viewer is read-only (no Approve/Return anywhere on the page), and does not appear until Program
   Chair has finished.
4. Designated faculty (e.g. the RET Chair's own IPCR, if it has R&E targets): unaffected — never
   appears on the RET Chair's own dashboard; still routes to `'Submitted to Dean'` directly and is
   approved/returned only via `/dean/verify_evidence`, exactly as before this change.
5. Confirm no regular faculty member can reach `WAITING_RET` status anywhere in the UI, and that
   `/ret_chair/verify_evidence` no longer exists (404, not just permission-denied).
6. Upload evidence to a target and leave "Completed in" blank — Submit button is disabled with a
   message naming the target; filling in the duration and re-checking readiness clears it. Repeat
   for a designated faculty member's own IPCR (`submit_designated_evidences`).
7. A target with no evidence at all is still submittable (unaffected by §3.D — the block is
   evidence-present-but-no-duration only, not evidence-absent).
