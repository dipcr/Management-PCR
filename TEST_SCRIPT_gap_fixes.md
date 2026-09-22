# Regression Test Script — Gap 1–6 Fixes (2026-09-20)

Scoped to the changes made in the recent gap-analysis pass, not a replacement for
`TEST_SCRIPT.md`. Each phase walks the **usual flow** for that role group end-to-end, with
explicit checkpoints (marked **CHECK:**) tied to a specific fix. Run phases in order — each
sets up what the next needs, same convention as `TEST_SCRIPT.md`.

**Legend:** `[ ]` not tested · `[/]` passed · `[*]` passed with a comment · `[-]` skipped

---

## Accounts needed

Same roster as `TEST_SCRIPT.md`'s "Accounts you need" table: one ADMIN, one DEAN, one
PROGRAM_CHAIR, one RET_CHAIR, one FACULTY (Regular), one DESIGNATED_FACULTY, plus a **second
Regular Faculty** for the account-claim checks in Phase 1. Fresh/active academic term required.

---

## Phase 1 — Admin: security cleanup, account claims, indicator guard

Covers Gap 1a/1b (dev routes removed), 2b (account unlock), 3g (dead route removed), 3h
(cascade-lock guard), 4c/4d (claim denial + notification).

- [ ] Visit these URLs directly while logged out — all should 404, not run:
  `/faculty/rollback_faculty/test@example.com`, `/faculty/test_ret_mail`,
  `/faculty/test_dean_package_mail`, `/faculty/test_ret_chair_targets_mail`,
  `/faculty/test_designated_tier2_mail`, `/faculty/test_ret_chair_evidence_mail`,
  `/faculty/test_chair_approved_first_mail`. **CHECK (1a/1b):** none of these should exist
  anymore.
- [ ] POST to `/dean/validate_quotas` (or just confirm no button/JS on the Dean dashboard
  calls it). **CHECK (3g):** route should 404.
- [ ] Second Regular Faculty registers via `/register` with a valid `employee_id_number`
  already on the roster (Admin must have created their profile first). Confirm the flash says
  the claim is pending Admin approval.
- [ ] Admin dashboard → Account Claims → **Approve** the claim. **CHECK (4d):** the
  claimant receives an email ("Account Claim Approved") — check the mail log/inbox configured
  in `.env` (`MAIL_SUPPRESS_SEND`). Confirm the claimant can now log in.
- [ ] Register a *third* throwaway claim the same way, then Admin **Deny** it. **CHECK
  (4d):** claimant receives an "Account Claim Denied" email. **CHECK (4c):** attempt to log in
  with the denied claim's credentials — should show the generic "Invalid Credentials" message
  (not a stale "claim was denied" message), and the same `employee_id_number`/email should be
  claimable again via `/register`.
- [ ] Admin → Security tab → **Lock Account** on the second Regular Faculty. Confirm they
  can't log in ("account has been deactivated" / locked message).
- [ ] Same row → **CHECK (2b):** an **Unlock Account** button is now enabled (Lock Account
  is disabled instead). Click it, confirm the account can log in again.
- [ ] Admin → Master Indicators → pick an indicator **not yet cascaded this term** →
  edit its category and save. Should succeed normally.
- [ ] Delete that same (not-yet-cascaded) indicator. Should succeed normally.
- [ ] *(After Phase 2 cascades quotas)* return here and try to edit the **category** of an
  indicator the Dean has already cascaded. **CHECK (3h):** rejected with "This indicator has
  already been cascaded to departments — its category cannot be changed." Editing just the
  description/efficiency type on the same indicator should still succeed.
- [ ] Try to **delete** that same cascaded indicator. **CHECK (3h):** rejected with "This
  indicator has already been cascaded to departments and cannot be deleted."

---

## Phase 2 — Dean: quota cascade (usual flow + permanent-lock check)

Covers Gap 3b.

- [ ] Dean dashboard → Phase 1: Institutional Quota Cascading. Enter quotas per
  department/RET/College-Wide for the active term's indicators as usual.
- [ ] Click **Cascade Institutional Targets** → confirm in the modal (its warning text:
  *"Cascading is a one-time action for this term... permanently locked"*). Confirm success —
  page now shows the "Cascaded & Locked" badge, inputs disabled, button gone.
- [ ] **CHECK (3b):** attempt to POST to `/dean/cascade_quotas` again directly for the same
  term (e.g. resubmit a saved form, or re-enable a disabled input via devtools and submit) —
  should be rejected with "Institutional quotas have already been cascaded and locked for this
  term," and the existing quota rows must be unchanged afterward.

---

## Phase 3 — Program Chair: distribution (usual flow + capacity-warning check)

Covers Gap 3c.

- [ ] Program Chair dashboard → distribute Instruction/Support targets to their
  department's faculty as usual, within the Dean's cascaded quota. Confirm normal success
  message, no warning.
- [ ] Repeat, but enter a quantity that — once multiplied across all faculty in the
  department — exceeds the Dean's cascaded total for that indicator. **CHECK (3c):** success
  message should still save the distribution, but with an appended warning like "Distributed
  total (N) exceeds the Dean's cascaded quota (M) for '<indicator>'."

---

## Phase 4 — RET Chair: rules, rejection, and resubmission (usual flow + status fixes)

Covers Gap 3d/3e (confirmed unchanged — no action needed, just don't expect a lock/gate here),
4a (rejection status), 4b (resubmission gating fix), plus the ret_chair.py/dashboard fixes from
the final review pass.

- [ ] RET Chair configures Research rank rules and Extension distribution as usual for the
  Regular Faculty's rank band.
- [ ] Regular Faculty submits their IPCR (Phase 5 below happens first if not already done)
  including at least one Research target.
- [ ] RET Chair dashboard → open the faculty's submission and **Reject** it with a remark.
- [ ] **CHECK (4a + final-review fix):** on the RET Chair dashboard's pending-drafts table,
  confirm the Status badge and the Actions-column button **agree** — both should read as
  "Returned"/"Awaiting Resubmission" for this row, not one saying "Pending Review" while the
  other is disabled.
- [ ] Faculty dashboard: confirm the rejected IPCR shows as returned/editable (not locked,
  not silently blank) and the submission form reappears so they can resubmit.
- [ ] **Before resubmitting**, have the RET Chair re-save the Research rule for this
  faculty's rank band (even with no real change — Gap 3d confirmed Research rules are always
  freely rewritten). This recreates the exact condition Gap 4b's bug depended on.
- [ ] Faculty resubmits. **CHECK (4b):** resubmission must succeed and must **not** be
  blocked with "Submission blocked: Program Chair has not allocated..." — that message would
  indicate the resubmission was incorrectly treated as a first-time submission.
- [ ] RET Chair reviews the resubmission and **Approves** it this time.

---

## Phase 5 — Regular Faculty submission (usual flow, if not already covered above)

- [ ] Faculty dashboard → select Research targets from the RET menu, confirm Extension
  targets appear read-only (not self-selectable) alongside the mandatory Teaching Load target
  and Program-Chair-allocated Instruction/Support targets.
- [ ] Submit. Confirm it routes to RET review first (since Research targets are present),
  then Program Chair review after RET approval — proceed into Phase 4/6.

---

## Phase 6 — Program Chair review & lock (usual flow)

- [ ] Program Chair reviews the RET-approved submission, adjusts quantities/remarks as
  needed, and **Approves**.
- [ ] Faculty dashboard → **Lock My IPCR**. Confirm committed targets are created and the
  dashboard now shows the locked/evidence-gathering view.

---

## Phase 7 — Designated Faculty: custom targets (usual flow + display fix)

Covers Gap 3f.

- [ ] Designated Faculty (or a chair/Dean on their own IPCR) opens their draft IPCR and
  adds a **Custom Target** (free-text description, quantity, duration), leaving category at its
  default.
- [ ] Submit the draft. **CHECK (3f):** on the Designated Faculty's own dashboard, the
  custom target's category should display as **"Support Functions"**, not a raw internal label.
- [ ] Dean reviews this designated faculty's draft (Phase 8). **CHECK (3f):** the same
  custom target must also show as "Support Functions" on the **Dean's review screen** — this is
  the cross-file consistency this fix specifically targeted (four separate display sites had to
  agree).
- [ ] Re-open the draft and edit the same custom target again before it's locked. Confirm
  it round-trips correctly (finds its real underlying category, doesn't break or duplicate) —
  this exercises the `custom_category_name` preservation kept during the 3f fix.

---

## Phase 8 — Dean review & lock (usual flow)

- [ ] Dean reviews the Designated Faculty's (or chair's) draft from Phase 7, approves it.
- [ ] Designated Faculty locks their IPCR (their own explicit "Lock My IPCR" action —
  confirm the commit only happens now, not automatically at Dean approval).

---

## Phase 9 — Evidence, scoring, print (usual flow, brief — untouched by this session's changes)

- [ ] Upload evidence for both the Regular Faculty's and the Designated Faculty's committed
  targets; have the appropriate reviewer (Program Chair / RET Chair / Dean per category) verify
  them.
- [ ] Confirm Q/E/T scoring and the Final Weighted Rating compute normally for both IPCRs.
- [ ] Print both IPCRs (`/faculty/print_ipcr` and `/designated/print_ipcr`) — confirm the
  layout is unaffected (no gap touched printing/export this session).

---

## Sanity checks (Gap 5, 6 — no functional behavior to test, spot-check only)

- [ ] While exercising Phase 4/6 above, confirm the server console shows no `[DEBUG]` print
  spam from the RET Chair's review endpoint, and no `error_log.txt` file appears in the project
  root after any error you trigger on purpose (e.g. a malformed request to
  `/prog_chair/review_ipcr/<bad_id>`).
- [ ] Skim `SETUP.md` §2.2 and `TEST_SCRIPT.md`'s reset appendix once — no functional test,
  just confirm the migration table and reset SQL read correctly (doc-only changes, Gap 6).
