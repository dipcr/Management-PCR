# Test Script — Dean Auto-Built IPCR & Linked Evidence

Focused script for the latest change set: the Dean's own IPCR now auto-builds from cascaded
quotas instead of manual picking, a Support-slug oversight total now scores under the Dean's
Core Functions instead of Strategic Priorities/Support, and the Dean's cross-department evidence
review now shows the real evidence behind an oversight row. Section 1 is a light regression pass
over the rest of the pipeline — confirms nothing upstream broke. For exhaustive/edge-case
coverage of any single phase, see `TEST_SCRIPT.md`.

**Legend:** `[ ]` not tested · `[/]` passed · `[*]` passed with a comment · `[-]` skipped

---

## Accounts you need

| Role | Designation | Department |
|---|---|---|
| Admin | `Admin` | — |
| Dean | `Dean` | e.g. WST Program |
| Program Chair A | `Program Chair` | Dean's own department (e.g. WST) |
| Program Chair B | `Program Chair` | a different department (e.g. DST) |
| Regular Faculty A1, A2 | `Regular Faculty` | Program Chair A's department |
| Regular Faculty B1 | `Regular Faculty` | Program Chair B's department |

No new migrations — this change set has no schema changes.

---

## Section 1 — Regression smoke pass (quick, not exhaustive)

- [ ] Admin: active term exists, master indicators defined for Instruction and Support
      (at least one of each), including one Instruction and one Support indicator meant to be
      split across departments.
- [ ] Dean: Quota Cascading loads, can cascade a quota to Program Chair A's and Program Chair
      B's departments for the same indicator (split, not College-Wide).
- [ ] Program Chair A: Target Allocation loads, can distribute Instruction to Faculty A1/A2
      (including a personal share to themself and, separately, to the Dean).
- [ ] Regular Faculty A1: can submit a draft IPCR, upload evidence, and it locks/commits
      normally.
- [ ] Print IPCR for Faculty A1: renders without error, correct weighted categories.
- [ ] No console/500 errors anywhere in the above.

If any of these fail, stop — it's not related to this change set, fix that first.

---

## Section 2 — Dean's IPCR auto-builds (no manual picking)

Setup: Dean cascades the **same** Instruction-slug indicator to both Program Chair A's and B's
departments (e.g. 15 + 15), and the **same** Support-slug indicator likewise (e.g. 10 + 5).
Program Chair A allocates the Dean a personal Instruction share (their own teaching load).

- [ ] Dean → Target Assignment → click **Draft IPCR** on the Dean's own row.
- [ ] **Core Functions** section shows, with no manual selection: locked Teaching Load, the
      personal Instruction share from Program Chair A, **and** the Support-slug oversight total
      (e.g. 15) — labeled "Oversight", quantity locked, duration editable.
- [ ] **Strategic Priorities & Support Functions** section shows the Instruction-slug oversight
      total (e.g. 30 = 15+15) — same locked/editable pattern. It does **not** also show the
      Support-slug total (that one moved to Core Functions above, not duplicated here).
- [ ] College-Wide checkbox pool shows nothing already covered by the two lists above.
- [ ] Click **Save & Issue Draft IPCR** with nothing manually checked. Succeeds; status becomes
      Issued/Approved.

---

## Section 3 — Category placement is correct on the real, printed/scored IPCR

- [ ] Print the Dean's IPCR: **I. Strategic Priorities/Support Functions (75%)** lists the
      Instruction-slug oversight total; **II. Core Functions (25%)** lists Teaching Load, the
      personal Instruction share, and the Support-slug oversight total as its own lettered
      subsection.
- [ ] Dean's live IPCR summary (dashboard) shows the same weighted breakdown as the print.
- [ ] **Regression check — Program Chair A**: their own IPCR still shows their department's
      whole oversight quota entirely under Strategic Priorities/Support Functions (75%) — the
      Support-slug reclassification is Dean-only; a chair's Support-slug oversight must **not**
      move to Core Functions.
- [ ] Same check for RET Chair, if one is set up.

---

## Section 4 — Linked evidence

Setup: Faculty A1 and A2 (both under Program Chair A) upload real evidence for the shared
Instruction-slug indicator and report a quantity; leave one Approved, one Pending.

- [ ] **Program Chair A's own Evidence Gathering panel** (`/designated/`): the oversight row
      shows the real aggregated quantity, "View Linked Evidence" button, and — opened — lists
      both faculty by name, with **no** upload form and **no** Approve/Return controls.
- [ ] **Dean's cross-department review** (Evidence Verification → open Program Chair A's
      package): the same oversight row shows "View Linked Evidence (N)", not "No evidence
      uploaded". Opening it lists the same two faculty by name/file/qty/status, **read-only** —
      confirm no Approve/Return button appears anywhere in that viewer.
- [ ] Network tab: confirm no `POST /dean/verify_evidence` fires while browsing that read-only
      viewer.
- [ ] Repeat once for the **Dean's own** committed oversight row (after Section 2/3): its linked
      evidence spans faculty from **both** Program Chair A's and B's departments at once.

---

## Section 5 — Sanity checks

- [ ] A **plain Designated Faculty** member (not a chair/Dean) is unaffected: still picks their
      own targets and submits for Dean review as before — no auto-build, no category change.
- [ ] Faculty A1/A2's own evidence, print, and score are unchanged by any of the above.
- [ ] No Python errors in the server log across all of Sections 2–4.
