# Implementation Plan: Link Faculty Evidence to Chair Departmental Oversight Targets

## 1. Scope

Program Chair and RET Chair each carry a **Departmental Oversight** row on their own IPCR
(`is_admin_function = 1`, produced by `get_oversight_targets()` in `app/models/designated.py`) —
their department's (or RET's) *whole* cascaded quota for an indicator, taken as one number, not a
share. Today, in their own **Evidence Gathering** panel (`designated_dashboard.html`), this row is
treated exactly like any other personal target: the chair must manually upload a PDF and manually
type Accomplished Qty / Completed-in-duration for it — duplicating data that already exists,
because the real work behind that quota was done by faculty in their scope who already uploaded
their own evidence against their own committed target for the *same* `indicator_id`.

**Goal:** for a chair's oversight row, stop asking for a separate upload/self-report. Instead,
derive the row's evidence, Accomplished Qty, and Timeliness input directly from the scoped
faculty's own committed-target data for that indicator, and show it to the chair read-only.

**Decided (per user):** full auto-aggregation, not evidence-only linking — the oversight row
becomes entirely derived (no manual upload form, no manual Q/duration inputs for that row).

**Out of scope:** Dean's own IPCR (`get_oversight_cascade_role()` already returns `None` for Dean
— no oversight row exists for the Dean today, and this plan doesn't add one). Any change to how
Program Chair/RET Chair *review* regular faculty's evidence (that's the separate, already-shipped
`evidence_verification_workflow_update_plan.md`).

---

## 2. Current mechanics (verified against code)

- `get_oversight_cascade_role(cursor, emp_id)` (`designated.py:72`) returns the cascade bucket a
  chair oversees: their `specialization` string for a Program Chair, `ROLE_RET` for the RET Chair,
  `None` for anyone else (including Dean).
- `get_oversight_targets()` (`designated.py:194`) reads `tbl_cascaded_quotas` for that role and
  produces the chair's own draft oversight row(s), one per indicator cascaded to their bucket.
  `total_target_value` is the department's/RET's whole quota, fixed (not editable by the chair).
- At submission (`submit_designated_ipcr`), the oversight row is inserted into
  `tbl_draft_targets` with `is_admin_function = 1`; at lock (`lock_and_commit_designated_ipcr`) it
  becomes a `tbl_committed_targets` row, same flag. **`is_admin_function = 1` is not unique to
  oversight rows** — it's also set on any freely-picked Strategic Priorities/Support pool item
  (per `old MDS/updates.md` §4.1) — so a committed row can't be identified as "genuinely oversight"
  by that flag alone. Only the draft-time template computes a narrower `is_oversight_cascade` flag
  (`routes/designated.py:150,380`, by cross-referencing `get_oversight_targets()`'s indicator ids),
  and this is **not currently carried through to committed targets or the Evidence Gathering
  panel at all** — that panel treats every selected committed target identically.
- `get_designated_committed_targets()` (`designated.py:530`) is the single read path the Evidence
  Gathering panel, the live ratings preview, and the printed IPCR all draw from. It does not
  distinguish oversight rows either.
- Evidence itself is a simple 1:1 relationship: `tbl_evidence_repo.target_id` → one
  `tbl_committed_targets` row → one `emp_id`. There is no existing mechanism anywhere in the
  codebase for one person's committed target to draw on another person's evidence.
- `recalculate_target_accomplished_quantity()` (`faculty.py:799`) is what actually derives a
  target's `actual_quantity`: it sums that *same* target's own `tbl_evidence_repo.actual_qty_Q`,
  excluding `Rejected`/`Returned` rows. This already gives a clean, verification-aware quantity
  per person — the aggregation this plan needs can sum these already-clean per-faculty numbers
  rather than re-deriving from raw evidence rows.
- The Evidence Gathering modal (`evidenceGatheringModal` in `designated_dashboard.html`) is
  **shared** for uploading files *and* self-reporting Accomplished Qty/Completed-in via
  `saveAccomplishmentDetails()` → `POST /designated/save_accomplishment` →
  `save_accomplishment_details()` (`faculty.py:761`). Both the upload route
  (`POST /designated/upload_evidence`) and the accomplishment-save route currently accept any
  `target_id` the chair owns, with no distinction for oversight rows — both need a server-side
  guard once the UI stops offering them for these rows, so the block isn't just cosmetic.
- Faculty scoping for "who counts" already exists twice, and this plan reuses the same rules
  rather than inventing a third:
  - Program Chair: `get_program_chair_evidence_faculty()` (`prog_chair.py:705`) — same
    `specialization`, excluding designated designations (`Designated Faculty`, `Program Chair`,
    `RET Chair`, `Dean`).
  - RET Chair: `get_ret_chair_evidence_faculty()` (`ret_chair.py:769`) — **college-wide**, filtered
    to Research/Extension category, same designation exclusion, no specialization filter.
- Indicator ids are shared vertically across the cascade: the Dean cascades indicator X at qty 5
  to a department, the Program Chair splits X among faculty at the *same* `indicator_id`, and RET
  Chair's rank-band menu/extension configuration likewise assigns faculty the same `indicator_id`
  RET was cascaded. This is what makes "same `indicator_id`, scoped faculty set" a valid join key
  for finding the individual work behind a chair's oversight quota.

---

## 3. Design

### A. Reliably identify a committed oversight row
Add `get_oversight_indicator_ids(cursor, emp_id, term_id)` to `designated.py` — the `{indicator_id}`
set cascaded to this chair's role via `tbl_cascaded_quotas` (the query `get_oversight_targets()`
already runs, minus the draft join). Use it in two places:
1. `get_designated_committed_targets()`: tag each row `is_oversight_cascade = row['is_admin_function']
   and row['indicator_id'] in oversight_ids`.
2. Refactor `routes/designated.py:150,380`'s inline duplicate of this same computation to call the
   new shared helper instead (currently copy-pasted twice) — a cleanup, not a behavior change.

### B. Aggregate scoped-faculty data for each oversight row
New function `get_oversight_evidence(cursor, emp_id, term_id, indicator_id)` in `designated.py`:
1. Resolve the chair's scope exactly as `get_program_chair_evidence_faculty` /
   `get_ret_chair_evidence_faculty` do (reuse `get_oversight_cascade_role()` to decide which):
   Program Chair → same `specialization`; RET Chair → college-wide.
2. Join `tbl_employee_profiles` (scoped, designations excluded) → their own
   `tbl_committed_targets` row(s) for this exact `indicator_id` (`is_admin_function = 0`, i.e.
   their personal target, never another chair's own oversight copy) → `tbl_evidence_repo`.
3. Return:
   - `total_actual_quantity`: `SUM(ct2.actual_quantity)` across matching faculty rows — already
     verification-clean per §2, no re-filtering needed.
   - `max_actual_duration_value`: `MAX(ct2.actual_duration_value)` among faculty who reported one.
     **Recommendation, not yet confirmed:** the department's quota isn't finished until its
     *last* contributor finishes, so MAX (not average) is the honest Timeliness input. Flag if a
     different aggregate is wanted before this ships.
   - `evidence_breakdown`: one row per evidence file — faculty name, file, qty, verification
     status — for the read-only viewer, plus an `evidence_count`.
4. Faculty who have the indicator as their own personal committed target but haven't reported yet
   contribute 0/`None` — same "not accomplished yet" semantics as any other live target, not an
   error.

### C. Wire the aggregation into the read path
In `get_designated_committed_targets()`, for any row where `is_oversight_cascade` is true, call
`get_oversight_evidence()` and **override** that row's `actual_quantity`, `actual_duration_value`,
and `evidence_count` with the aggregated values before `compute_target_rating()` runs — this is
the one read path already shared by the dashboard, the live ratings preview, and the printed IPCR
(§2), so overriding here (not in each caller) keeps all three consistent automatically. Whatever
the chair's own `tbl_committed_targets` row stores for these columns becomes vestigial for
oversight rows specifically (never read, never written after this change) — leave the columns
alone rather than migrating them, whatever ends up recomputing here is what displays and scores.

### D. Evidence readiness / submission gating
`check_designated_evidence_readiness()` already treats "evidence present but no duration" as a
hard block (`has_missing_timeliness`, per the earlier evidence-verification plan). Once (C) feeds
an oversight row's aggregated qty/duration through the same dict shape, this logic applies
unchanged — **but confirm this is the wanted behavior**: it means a chair cannot submit their own
IPCR while a scoped faculty member has *uploaded evidence but not yet entered a duration* for that
indicator, even though the chair has no way to fix that themselves. Recommendation: exclude
oversight rows from `has_missing_timeliness` (they can't be unblocked by the chair — this mirrors
the already-accepted "target duration itself missing" edge case in the earlier plan, §3.D.5, which
was deliberately left unblocked for the same reason: don't trap someone with no way to self-unblock).
Aggregated qty/evidence still display normally; only the hard submission-block is skipped for
these rows.

### E. Server-side guards (not just hidden UI)
1. `save_accomplishment_details()` (`faculty.py:761`): reject with `"This is a Departmental
   Oversight target — its Accomplished Qty and Timeliness are derived automatically from your
   department's/RET's faculty evidence."` when the target is an oversight row (needs the same
   `is_oversight_cascade` check — cheapest is a small helper reusing (A) rather than duplicating
   the query here).
2. `designated_upload_evidence()` (`routes/designated.py:770`): same rejection before saving the
   file — a chair should not be able to attach their own PDF to an oversight row's (nonexistent)
   personal evidence slot.

### F. Evidence Gathering panel UI (`designated_dashboard.html`)
1. Table row (~line 741 onward): badge oversight rows the same way Table 1/2 already do
   (`is_oversight_cascade` → "Departmental Oversight" badge), and change the action button label
   to "View Linked Evidence" (no "Add" wording — nothing to add).
2. `openEvidenceModal()`: branch on a new `data-oversight` attribute. For an oversight row, hide
   the "Upload New Evidence" form and the "Completed in" / efficiency inputs entirely (not just
   disable them — `applyEvidenceLock()`'s existing lock-after-final-IPCR pattern is the closest
   precedent for toggling sections), and instead render the aggregated total + a labeled
   read-only list ("Linked from department faculty") sourced from (G).
3. Remove the Save/Submit-accomplishment button for this row's modal state (nothing to save).

### G. New read endpoint
Extend `designated_target_evidence()` (`routes/designated.py:753`) — or add a sibling route,
whichever keeps the branch simplest — to detect an oversight target (via (A)'s helper) and, when
true, return `get_oversight_evidence()`'s breakdown instead of `get_evidence_by_target()`'s raw
list, plus the aggregated qty/duration for the modal header. The existing `evidence_list` shape
can't represent "which faculty member" per file, so the oversight branch needs its own JSON shape
(`{'success': True, 'is_oversight': True, 'total_actual_quantity': ..., 'max_actual_duration_value':
..., 'breakdown': [{'faculty_name', 'file_path', 'actual_qty_Q', 'verification_status'}, ...]}`) —
update the JS to branch on `data.is_oversight` when rendering.

### H. Performance
`get_designated_committed_targets()` already runs once per dashboard load; (C) adds one extra
query per oversight row (typically 0–2 rows per chair, one per indicator cascaded to them — not
per faculty), so this stays cheap. No batching needed.

---

## 4. Summary of files changed

| File | Change |
| :--- | :--- |
| `app/models/designated.py` | New `get_oversight_indicator_ids()`, new `get_oversight_evidence()`; `get_designated_committed_targets()` tags `is_oversight_cascade` and overrides qty/duration/evidence_count for those rows; `check_designated_evidence_readiness()` exempts oversight rows from the missing-timeliness hard block. |
| `app/routes/designated.py` | Reuse `get_oversight_indicator_ids()` in the two existing inline computations (150, 380); `designated_target_evidence()` branches to the oversight aggregate shape; `designated_upload_evidence()` rejects oversight target ids. |
| `app/models/faculty.py` | `save_accomplishment_details()` rejects oversight target ids. |
| `app/templates/designated_dashboard.html` | Evidence Gathering table: oversight badge + relabeled button; `openEvidenceModal()`/modal markup: hide upload form and Q/duration inputs for oversight rows, render the read-only per-faculty breakdown instead; JS fetch branches on `data.is_oversight`. |

Not changed: `app/models/scoring.py`, `app/models/ipcr_form.py` / `ipcr_print.html` (both already
read through `get_designated_committed_targets()`, so they inherit the aggregated values with no
code change of their own — worth a manual print-preview check anyway, see §6).

---

## 5. Open decisions (please confirm before implementation)

1. **Timeliness aggregate: MAX vs. average** across contributing faculty's `actual_duration_value`
   (§3.B.3). Recommendation: MAX (department finishes when its last contributor finishes).
2. **Missing-timeliness gating for oversight rows** (§3.D): recommendation is to exempt them from
   the hard submission block, since the chair can't act on a faculty member's missing duration
   entry themselves.
3. Anything else surfaced once real data is checked — e.g. whether an oversight indicator can
   legitimately have zero scoped faculty holding it yet (Program Chair cascaded but hasn't run
   distribution) — current design already handles this gracefully (aggregate 0, not an error), just
   flagging it as an expected, not edge, case worth seeing once in testing.

---

## 6. Implementation notes (as built, 2026-09-07)

Both open decisions from §5 were confirmed and implemented as recommended: MAX aggregation for
Timeliness, and oversight rows exempted from the missing-timeliness hard block.

**Correction to §2/§3.C's central assumption.** While implementing, discovered that
`get_designated_committed_targets()` is **not** actually the shared read path for scoring/print —
that claim in the original plan was wrong. The real architecture:
- `get_designated_committed_targets()` (`designated.py`) feeds only the Evidence Gathering
  dashboard table and its own readiness gate.
- `get_faculty_committed_targets()` (`faculty.py`) is the one function `compute_ipcr_score()`
  (every rating number, dashboard and print alike) and `build_ipcr_form()` (the printed IPCR's
  target rows) actually call — for **both** Regular and Designated faculty, including chairs'
  own IPCRs.

Overriding only inside `get_designated_committed_targets()` would have made the dashboard's
evidence checklist show the aggregate while the actual score and printed IPCR silently kept using
the chair's own (permanently zero, once upload is removed) `actual_quantity`/`actual_duration_value`
— the aggregation would never have reached the number that matters. Fixed by extracting the
override into a new shared `apply_oversight_overrides(cursor, emp_id, term_id, rows)` in
`designated.py` (tags `is_oversight_cascade`, overrides qty/duration/evidence_count, and recomputes
`actual_accomplishment`/`rating` for oversight rows only) and calling it from **both**
`get_designated_committed_targets()` and `get_faculty_committed_targets()`. It's a no-op for
everyone without an oversight role (`get_oversight_indicator_ids` returns an empty set
immediately), so every other caller of `get_faculty_committed_targets()` — Regular Faculty's own
dashboard, Program Chair/RET Chair reviewing *regular* faculty, Dean reviewing a package —
is unaffected.

**Second correction, a real blocker not just a display gap.** `enrich_faculty_verification_status()`
(`faculty.py`) — the function gating `dean_approve_package` — counts evidence per CHAIR/RET
category bucket by `LEFT JOIN tbl_evidence_repo`. Once oversight rows can never have their own
evidence row (upload removed), a chair whose only non-RET committed target *is* an oversight row
would have `chair_targets_has_ev` stuck `False` forever, blocking Dean approval permanently. Fixed
by excluding oversight rows from that function's per-category tally entirely (same exemption
rationale as the missing-timeliness gate) — an oversight row's real evidence already went through
its own verification pipeline on the faculty side, so it should neither help nor block this gate.

**Known follow-up, not implemented (out of scope for this pass):** the Dean's own evidence
verification screen (`get_dean_faculty_evidence_details`, `dean.py`) still fetches a chair's
oversight row's evidence via the chair's own (permanently empty) `target_id` — the Dean will see
"no evidence" on that row even though its Accomplished Qty now shows the real aggregate (this is
cosmetic only; confirmed not to block approval, per the fix above). Flagging in case the Dean's
screen should eventually show the same linked breakdown the chair's own dashboard now does.

### Post-implementation recheck (2026-09-07): four fixes, one confirmed extension

A full recheck pass over the diff surfaced and fixed four issues, none of which showed up in
`py_compile` or the app-import smoke test:

1. **Stale duration/rating after a Returned evidence file.** `actual_duration_value` and
   `efficiency_rating_E` are only cleared by `_clear_accomplishment_details_if_unaccomplished`
   (`faculty.py`), which the *delete*-evidence path calls but the *Return/Reject*-evidence path
   does not. Without a guard, a faculty member whose evidence was Returned (quantity nets back
   to 0) could still contribute a stale duration/rating to the department's aggregate. Fixed by
   only counting a contributing faculty row's duration and rating when their own
   `actual_quantity > 0` (see `get_oversight_evidence`'s `reported_rows` filter).
2. **Pre-existing IDOR in `designated_target_evidence()`** (`routes/designated.py`): `emp_id` was
   read from the session but never checked against `target_id`'s actual owner — any authenticated
   designated-flow user could read another employee's evidence list by passing an arbitrary
   `target_id`. Not introduced by this feature, but closed while already touching this function.
3. **Same gap, more severe, in `designated_upload_evidence()`**: no ownership check meant a direct
   POST could attach a file to, and inflate the accomplished quantity of, another employee's
   committed target. Closed using the same row already fetched for the oversight-block guard.
4. **Unhandled exception on a malformed `target_id`** in the new ownership-check block (`int()`
   outside any `except`) — fixed by validating the id up front before the DB check.

**Extension, per user decision:** Efficiency (E) is now aggregated too, not left `None`. For a
Client-Satisfaction-rated oversight indicator, `get_oversight_evidence()` returns
`avg_efficiency_rating` — the rounded (round-half-up, not Python's round-half-to-even) average of
`efficiency_rating_E` across contributing faculty (same `actual_quantity > 0` staleness guard as
the duration). Inert for any other `efficiency_type`, since `rate_efficiency()` only reads this
field for Client Satisfaction. Rejected alternatives: minimum/worst-case rating (rejected — too
punitive, one low rating would drag the whole row down) and leaving it unscored (rejected — an
oversight row would be missing a component a normal target has).

### Files actually changed
| File | Change |
| :--- | :--- |
| `app/models/designated.py` | `get_oversight_indicator_ids()`, `get_oversight_evidence()` (qty sum, MAX duration, rounded-average efficiency rating, evidence breakdown — all staleness-guarded on `actual_quantity > 0`), `apply_oversight_overrides()` (new); `get_designated_committed_targets()` calls the shared override. |
| `app/models/faculty.py` | `get_faculty_committed_targets()` calls the shared override (the fix that makes it reach scoring/print); `save_accomplishment_details()` rejects oversight target ids; `enrich_faculty_verification_status()` excludes oversight rows from its per-category evidence tally. |
| `app/routes/designated.py` | `designated_target_evidence()` branches to the oversight aggregate JSON shape and now checks target ownership (closing a pre-existing IDOR); `designated_upload_evidence()` validates the target id, checks ownership (same pre-existing gap, closed), and rejects oversight target ids server-side; both inline draft-side `is_oversight_cascade` computations refactored onto the shared helper (one was fully redundant post-`get_designated_committed_targets` change and was removed, not just refactored). |
| `app/templates/designated_dashboard.html` | Evidence Gathering table: oversight badge, "View Linked Evidence" button; modal: `accomplishmentDetailsSection` hidden and upload form locked for oversight rows via `applyEvidenceLock()`, distinct info banner; `reloadEvidenceModalSubmissions()` renders the per-faculty read-only breakdown when `data.is_oversight`. |

### Second recheck (2026-09-07): live read-only validation against real data

Beyond `py_compile` and the app-import smoke test, ran every new function read-only (SELECT-only,
per CLAUDE.md's rollback-is-a-no-op caution — no writes) against the real shared dev database,
using historical committed-target data from RET Chair emp_id 49 (term 23), which happens to have
exactly the multi-faculty, mixed-rating scenario this feature targets:

- `get_oversight_evidence()` correctly summed `actual_quantity` across two different contributing
  faculty for the same indicator (e.g. indicator 206: 1 + 1 = 2), took MAX duration across them,
  and averaged Efficiency only over the faculty who had actually reported one (one contributor
  rated 5, the other unrated -> average correctly came out to 5, not diluted by the missing one).
- `get_designated_committed_targets()` and `get_faculty_committed_targets()` returned **identical**
  aggregated `actual_quantity`/`rating` for the same oversight rows when queried side by side —
  direct confirmation that the central fix (§ above: both paths must call
  `apply_oversight_overrides`, not just the dashboard one) actually holds.
- `enrich_faculty_verification_status()` on this exact chair: their oversight rows still carry old
  evidence directly uploaded to the chair's own target_id (`ev_id` present, status `Pending`) from
  *before* this feature existed — confirmed these are now correctly ignored by the gate (the
  `continue` skip fires on them), while their one genuine personal target (mandatory Teaching Load,
  `is_admin_function = 0`, its own real `Pending` evidence) still correctly drives `chair_finished`.
  Net result: `ret_finished = True` (bypassed, since every R&E-bucket target for this chair is an
  oversight row) while `chair_finished = False` (correctly still gated on the teaching load) — this
  is precisely the "entire IPCR is R&E-only" scenario the exclusion fix was written to protect
  against, now confirmed against real data rather than reasoned about in the abstract.
- `check_designated_evidence_readiness()`'s `targets_with_evidence` count (4 of 6) reconciled
  exactly by hand against which of the 5 oversight indicators had nonzero aggregate evidence plus
  the 1 teaching-load target — no drift between the two counting paths.

No new defects found in this pass. Combined with the first recheck's four fixes, this feature has
now been verified statically, via a live app-import/route-registration check, and via live
read-only execution against real multi-contributor data.

Verified: `python -m py_compile` across all touched files plus their direct dependents
(`dean.py`, `scoring.py`, `ipcr_form.py`, `ret_chair.py`, `prog_chair.py` routes) — no syntax/import
errors. **Not yet done:** the manual DB walkthrough in §6 below — needs a real term with a Dean
cascade to a department/RET, faculty distribution, and faculty-side evidence upload to exercise
end-to-end.

---

## 7. Verification plan

### Automated
```powershell
python -m py_compile app/routes/designated.py app/models/designated.py app/models/faculty.py
```

### Manual (against a real DB, per `TEST_SCRIPT.md` conventions)
1. Program Chair: Dean cascades indicator X at qty 5 to the department; chair distributes it
   3/2 to two faculty; both faculty upload evidence and report Q/duration on their own dashboards.
   Chair's Evidence Gathering panel shows the oversight row for X with Accomplished Qty = 5,
   badged "Departmental Oversight", "View Linked Evidence" opens a read-only list showing both
   faculty's files, no upload form, no Q/duration inputs.
2. Same setup, only one faculty member reports so far (qty 3 of 5): oversight row shows 3/5,
   chair can still submit their own IPCR for Program Chair review (missing-timeliness exemption
   from §3.D, assuming Decision 2 is confirmed as designed).
3. Attempt `POST /designated/upload_evidence` and `POST /designated/save_accomplishment` directly
   against an oversight `target_id` (e.g. via browser devtools) — confirm both are rejected
   server-side, not just hidden in the UI.
4. RET Chair: confirm the same flow works college-wide (no specialization filter) for a
   Research/Extension oversight indicator.
5. Printed IPCR: oversight row's Actual Accomplishment / Q / T columns reflect the aggregated
   values, not whatever (if anything) was previously stored directly on the chair's own row.
6. A chair with zero faculty holding the oversight indicator yet: row shows 0/quota, no evidence,
   remains submittable (matches the already-accepted "target with no evidence is submittable"
   rule from the earlier evidence-verification plan).

---

## 8. Addendum (2026-09-07): Department Accomplishment Summary on Program Chair's own dashboard

**Idea, from the Program Chair's side this time:** a live view of quota vs. accomplishment for
the same indicators cascaded to their department — but with a stricter, verification-gated
definition of "accomplished" than the oversight row itself uses (which counts any non-rejected
evidence, Pending included, matching the whole codebase's existing Q-scoring convention).

**Confirmed nothing like this existed** (research pass over `prog_chair.py`/
`prog_chair_dashboard.html`): the closest things were Phase 1's "Total Distributed" column (a
pre-lock planning projection, `assigned_qty × faculty_count`, unrelated to real accomplishment)
and the per-faculty evidence modal (one faculty at a time, never summed by indicator). This is net
new, not an extension of an existing feature.

**Decisions (per user):**
1. **Additive, not a replacement.** This is a second, stricter figure ("Verified Accomplished" =
   Approved-only) shown alongside — not instead of — the existing "Accomplished Qty" used for
   scoring and the oversight row's own display. No scoring change.
2. **Placement: Program Chair's own dashboard**, not the chair's personal `/designated/` IPCR
   page. Scoped to Program Chair only for this pass — RET Chair's oversight bucket is
   college-wide (`ROLE_RET`, no specialization), so an equivalent view for RET Chair would need a
   different, non-specialization-scoped query; flagged as a follow-up, not built here.

**Implementation:**
- `get_department_accomplishment_summary(cursor, specialization, term_id)`
  (`app/models/prog_chair.py`) — one row per indicator in `tbl_cascaded_quotas` for this
  specialization (the exact same cascade rows `get_oversight_targets` reads, so this always
  matches what becomes the chair's own oversight rows). `verified_accomplished` is a fresh
  `SUM(actual_qty_Q)` restricted to `verification_status = 'Approved'`, computed via a subquery
  scoped to regular faculty only (same specialization + designation-exclusion pattern used
  everywhere else — `get_program_chair_evidence_faculty`, `get_oversight_evidence`) — deliberately
  *not* reusing `ct.actual_quantity`, since that column mixes in Pending evidence. Independent of
  whether the chair has locked their own IPCR for the term.
- Wired into `prog_chair_dashboard()` (`app/routes/prog_chair.py`) as
  `department_accomplishment_summary`, computed alongside the existing evidence-faculty lists —
  already exported via `app.models`'s wildcard import, no new import line needed.
- New card in `prog_chair_dashboard.html`, "Department Accomplishment Summary," placed at the top
  of the Evidence Verification section (before the per-faculty submissions table) — Indicator /
  Quota / Verified Accomplished / progress bar, one row per cascaded indicator.

**Verified against real data** (read-only, live shared DB, no writes): hand-traced one indicator
(414, term 48, WST) with seven contributing rows across the *exact* edge cases this query needs to
get right — two Regular Faculty rows (one with evidence, one without), a Designated Faculty
member's row, the Dean's own admin-function row, **the WST chair's own oversight-row evidence
(qty 7 — large enough that including it by mistake would have been obvious)**, and a
Designated Faculty row from a *different* department. Only the one genuinely-scoped Regular
Faculty row's two Approved evidences (1+1=2) should count — the function returned exactly `2`.
`py_compile`, Jinja template parse, and a full app/route-registration check all pass.
