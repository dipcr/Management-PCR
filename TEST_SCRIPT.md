# End-to-End Test Script — Full System

Covers every role and every feature in the system. Phases run in order: each one sets up
what the next needs. Where a phase can be skipped, it says so.

**Legend:** `[ ]` not tested · `[/]` passed · `[*]` passed with a comment · `[-]` skipped
Add notes under any item as `:your comment`.

---

## Accounts you need

| Role (`system_role`) | Designation on the roster | Used in |
|---|---|---|
| ADMIN | `Admin` | 0, A, L, M |
| DEAN | `Dean` | 0, B, F, H, I, J, K, M |
| PROGRAM_CHAIR | `Program Chair` | 0, C, F, H, J, K, M |
| RET_CHAIR | `RET Chair` | 0, D, F, H, J, K, M |
| FACULTY | `Regular Faculty` | 0, E, F, G, K, M |
| DESIGNATED_FACULTY | `Designated Faculty` | 0, I, J, K, M |

You also need a **second Regular Faculty** (different person, same department) for the
permission checks in Phase M, and ideally a **second Program Chair** in another department.

> ### ⚠ Two different fields, easy to confuse
> `system_role` decides **which dashboard** you land on at login.
> `designation` decides **whether you have an IPCR of your own** and **which weight table**
> rates it. A Program Chair has both: role `PROGRAM_CHAIR` *and* designation `Program Chair`.
> If a chair's designation is wrong, their My IPCR silently will not appear.

> **Migrations required:** all of `old MDS/MIGRATION_group*.sql` in numeric order — see SETUP.md
> §2.2 for the full table. Later phases below depend on more than the four groups this note used
> to list (e.g. Phase D3's Extension distribution assumes the `group13`/`group18` RET-rules
> refactor, not the older `tbl_ret_extension_distribution` table); keeping one authoritative list
> in SETUP.md avoids the two docs drifting against each other again.

---

## Coverage map

| Phase | What it covers |
|---|---|
| **0** | Login, logout, registration, bad credentials |

| **A** | Admin: term, departments, teaching load, printed-IPCR config, criteria, categories, weights, indicators |

| **B** | Dean: cascade quotas to departments / RET / College-Wide (with permanent lock & warning) |
| **C** | Program Chair: distribute to faculty **and to chairs/Dean** |
| **D** | RET Chair: research menu, direct assignment (with desc/duration), extension distribution |
| **E** | Regular Faculty: select and submit |
| **F** | RET review → PC review → return/resubmit → lock |
| **G** | Evidence upload, accomplishment reporting, Q/E/T scoring |
| **H** | Verification by Program Chair, RET Chair and Dean (official printable IPCR document review) |

| **I** | Designated Faculty: full cycle including custom targets & Program Chair allocated instruction |
| **J** | Program Chair / RET Chair / Dean own IPCR & Dean College-Wide target assignments | 


| **K** | Print IPCR, both variants |
| **L** | Admin maintenance: roster, CSV import, backup, accounts |
| **M** | Permissions and security |
| **N** | Auto-generated IPCR target descriptions (live mirroring, reset, backend fallback) |

---

## Phase 0 — Login and accounts

- [/] Each of the six accounts logs in and lands on **its own dashboard**.
- [/] Wrong password is rejected with a message, and does **not** reveal whether the email exists.
- [/] **Logout** returns to the login page; pressing Back does not restore the dashboard.
- [/] Visiting a dashboard URL while logged out redirects to login.
- [/] **Register** a new account → it is created as unapproved and **cannot log in** until
      an Admin approves it.

---

## Phase A — Admin setup

### A1. Open the term
Admin → **Term Configuration**.

- [/] Form has Academic Year, Semester, Submission Deadline, and **Rating Period From / To**.
- [/] Set the period (e.g. `2026-01-01` → `2026-06-30`) — Phase K prints
      *"for the period JANUARY to JUNE 2026"*.
- [/] Open the term → it becomes active and **every other term is deactivated**.

### A2. Departments
Admin → **Institution Setup** → *Departments / Programs*.

- [ ] Seeded departments listed with codes and display order.
- [ ] **Add** `MST Program` / `MST` / order 50 → appears.
- [ ] **Edit** its code and order → persists.
- [ ] **Deactivate** it → greys out, Status reads Inactive, and it disappears from the
      Dean's cascade columns in Phase B.

> Renaming a department also renames it on the faculty roster and on existing quotas,
> because targets route by that name.

### A3. Teaching load
Same panel → *Teaching Load*.

- [ ] **Regular Faculty** shows `21` hours / `6` months; **Designated Faculty** shows `10` / `6`.
- [ ] Change Regular to `18` → Save → reopen → persisted.
- [ ] Switch to **Per academic rank**, fill Instructor only → Save → reopen → in per-rank mode, the "all ranks" row gone.
- [ ] Switch back to **Same for all ranks**, set `21` / `6 months`, Save. *(Leave it here.)*
- [ ] After saving, fields are **locked**; an **Edit** button unlocks them and Save returns.

### A4. Printed IPCR configuration
Same panel → *Printed IPCR*.

- [ ] **College Full Name** pre-filled; code reads `CICT`.
- [ ] Four blocks listed: Reviewed by · Approved by · Assessed by · Final Rating by.
- [ ] "Filled from" offers **A named person / Their Program Chair / The Dean**.
- [ ] Choosing a derived option **disables** the Name field.
- [ ] Enter the **Head of Office** name on *Approved by* and *Final Rating by* → Save → persists.
- [ ] Saving a *named person* block with an empty name is refused.
- [ ] **Self-heal:** if the signatory table is ever emptied, opening this panel recreates
      the five standard blocks; names already configured are left untouched.

### A5. Criteria (target types)
Admin → **Criteria**.

- [ ] Table shows slug / lane / core / order — **no Weight Group column**.
- [ ] **Add** `Innovation`, lane `CHAIR`, order 60, core ✓ → slug auto-generates as `innovation`.
- [ ] The form has an optional **Slug** field, with a note naming the built-in slugs the
      code matches on. Leaving it blank generates one from the name.
- [ ] **Edit** it — the name changes but the **slug stays fixed**.
- [ ] **Deactivate** it — the row dims but Edit / Activate stay clearly clickable.
- [ ] Reactivate it, or leave it inactive — either way it must not break Phase A7.

### A6. Category Management
Admin → Criteria → **Category Management**.

- [ ] **Regular Faculty**: Strategic Priorities (Instructions) · Core Functions (Research,
      Extension) · Support Functions.
- [ ] **Designated Faculty**: Strategic Priorities/Support Functions (Administrative,
      Support) · Core Functions (Instructions).
- [ ] **Edit** a category, change its target types → saves.
- [ ] **Add** a category for a designation → appears with the types you chose.

> The key behaviour: **Instructions belongs to a different category per designation** —
> Strategic Priorities for Regular, Core Functions for Designated.

### A7. Weight allocation
Admin → Criteria → **Weight Allocation by Rank**.

- [ ] Columns show **real category names**, not `instruction / ret / support`.
- [ ] **Regular Faculty**, General: `50` / `40` / `10`. Total badge turns green at 100, red at 90.
- [ ] Saving at 90% is **rejected** and stores nothing.
- [ ] Saving at 100% succeeds.
- [ ] **Designated Faculty**, General: `75` / `25` → saves independently; Regular still 50/40/10.
- [ ] Switch Regular to **Per Academic Rank**, fill Instructor at 100%, save, reopen →
      per-rank mode, General row gone.
- [ ] Switch back to **General**, re-enter 50/40/10, save. *(Leave it here.)*
- [ ] **Copy weights from previous term** brings the earlier term's values in.

### A8. Master indicators
Admin → **Master Indicators**.

- [ ] **Import from Previous Term** populates the pool (or add manually).
- [ ] Panel is grouped by **IPCR category**, mirroring the DPCR.
- [ ] Each category header has **Add Target**; it opens a modal with a **Target Type
      dropdown scoped to that category**.
- [ ] Add one under Core Functions → choose `Research` → lands under the right sub-heading.
- [ ] **Edit** an indicator's description and efficiency type → persists.
- [ ] **Delete** an indicator that has no targets against it → removed.
- [ ] An **Other Target Types** section exists for Administrative Functions.
- [ ] **Custom Target Items is NOT offered** as a category to file targets under.

**Set up for later phases:**
- [ ] Set one indicator to **Efficiency Type = Client Satisfaction** *(needed for G3)*.
- [ ] Create at least one **Administrative Functions** indicator *(needed for J2)*.
- [ ] Create at least one indicator using **click-to-tag**: type
      `"Submit 51 accurate report of grades within 10 days after the final examination period"`
      into the description field, click the detected `51` → **Qty**, click `10 days` → **Dur**
      (the Dur button consumes the trailing unit word too — you should see it offer to tag
      `"10 days"` as one unit, not just `10`) → Save *(needed for the placeholder-mode cases in
      Phase N)*.
- [ ] Reopen the Master Indicators list → the row still reads as a normal sentence with `51` and
      `10 days` visible, not raw `{qty:51}`/`{duration:10:days}` syntax — confirms the tagged
      default is used for display, even though the *actual* substitution (Phase N4) uses
      whatever quantity/duration gets assigned later, not this original number.
- [ ] Click **Undo last tag** immediately after tagging → the last tag reverts to its original
      plain number.

> **Placeholder authoring**: for a real-world indicator that already states its own quantity
> mid-sentence (the common case — see Phase N), tag it instead of leaving the sentence bare.
> Typing `{qty}`/`{duration}` by hand still works too. An indicator with no placeholders at all
> still works — the system falls back to prepending the quantity and appending the duration —
> but that only reads correctly for a bare activity name with no number of its own.

---

## Phase B — Dean: cascade quotas

Dean → **Quota Cascading**.

- [ ] Columns are generated from the **managed departments** plus `RET / Extension` and
      `College-Wide`. The department deactivated in A2 is **absent**.
- [ ] Fill quotas for your Faculty's department, for **RET / Extension**, and at least one
      **College-Wide**.
- [ ] Cascade an **Administrative Functions** target to a department *(feeds J2)*.
- [ ] Leave one target unallocated → press **Cascade Institutional Targets** → a
      confirmation modal appears and **blocks submission**, naming the unassigned target.
- [ ] Fill it → press again → modal shows target count & warns that cascading is a one-time action and permanently locks quotas for the term → **Confirm & Cascade** → button disables with spinner and submits.
- [ ] Reopen: saved quotas persist, card displays **Cascaded & Locked** badge, info alert is shown, all inputs are disabled, and cascade button is removed.

> Record what you cascade to each department and to RET — phases C and J check those
> exact numbers reappear.

---

## Phase C — Program Chair: distribute targets

Program Chair → **Target Allocation**.

- [ ] The list shows the department's **Regular Faculty**.
- [ ] It **also shows the Dean, the Program Chair themselves, the RET Chair and any other
      designated faculty** in that department.
- [ ] Each row has a **duration number + unit dropdown**, not free text.
- [ ] Leave the description blank, fill quantity `2` and duration `1 semester` → the
      description field **live-fills** with `2 <indicator text> within 1 semester` as you
      type, with a small **Auto** badge next to it.
- [ ] Change the quantity to `3` → the description text updates immediately.
- [ ] Type over the description by hand → the **Auto** badge disappears and a **Reset to
      Auto** button appears; changing quantity again no longer touches your typed text.
- [ ] Click **Reset to Auto** → your text is replaced with the regenerated standard wording
      and the Auto badge returns.
- [ ] Fill quantity, duration (`6` + `months`) and a target description → Save.
- [ ] **Allocate instruction to the Dean, the Program Chair and the RET Chair** — Phase J checks these appear in their Core Functions.
- [ ] Reopen → values persist including the unit, and rows you left on Auto still show the
      Auto badge; rows you customized still show your text with the badge hidden.
- [ ] Support-type targets are offered to **Regular Faculty only**, not to designated faculty.
- [ ] Re-saving after finalisation is blocked with a warning.

---

## Phase D — RET Chair

### D1. Research menu
RET Chair → **Menu Config**.

- [ ] Form is **Research-only** — no Extension fields.
- [ ] Each research indicator has an **IPCR description** and **duration + unit**, enabled
      only when its checkbox is ticked.
- [ ] Tick an indicator and leave its description blank → it live-fills with the standard
      auto wording (Auto badge shown) as you fill quantity/duration; type over it → badge
      hides and **Reset to Auto** appears.
- [ ] Pick your Faculty's rank, Research Required = `1`, tick 2 indicators, fill their
      descriptions and durations → Save.
- [ ] **Edit** an already-saved rule (see below) → each row's Auto/customized state restores
      correctly — a row you'd customized before still shows your text and no Auto badge;
      an untouched row still auto-mirrors.
- [ ] **Active Research Rules** appears **in the same panel** (no separate nav item).
- [ ] **Edit** a rule → stays on this panel and repopulates description + duration.
- [ ] **Delete** a rule → removed, and the faculty of that rank no longer see a menu.
      *(Re-create it before Phase E.)*

### D2. Direct research assignment
RET Chair → **Target Assignment**.

- [ ] All regular faculty are listed.
- [ ] **Assign** on a *different* faculty → modal shows **Research only** → tick one, verify IPCR description and duration (value + unit dropdown) fields appear and pre-fill → Save.
- [ ] With the description left blank, the pre-filled preview already shows the standard
      auto wording (Auto badge) before you even save — change the quantity and it updates live.
- [ ] The button shows a count badge.
- [ ] Reopen the editor → the assignment is still ticked and description/duration persist.
- [ ] Log in as the assigned faculty in Phase E → assigned research is locked, carrying the assigned description and deadline.

### D3. Extension distribution — ⚠ one-time
Same panel → *Distribute Extension Targets to All Faculty*.

- [ ] There is **no checkbox** — every extension target is distributed.
- [ ] Each has qty / faculty, a **description**, and **duration + unit**.
- [ ] Leave a description blank and set duration `6 months` → it auto-fills with the standard
      wording (Auto badge). ⚠ Since this action is permanent, deliberately check the
      auto-generated text reads correctly for at least one indicator before distributing —
      there is no way to fix it afterward this term.
- [ ] Fill them (`1`, `6 months`) → **Distribute** → confirm.
- [ ] Card flips to **Distributed & Locked**; inputs disabled; button gone.
- [ ] Refresh → still locked. *(Cannot be undone — see the Reset appendix.)*

---

## Phase E — Regular Faculty: select and submit

### E1. Standard initial submission (with Research)
Log in as the FACULTY whose rank you configured in D1.

- [ ] **Research Menu** shows that rank's indicators with configured descriptions and durations.
- [ ] **Extension Targets** card is read-only with a lock icon ("Distributed to all faculty").
- [ ] Research counter reads **"(optional) — up to: 0 / 1"**.
- [ ] **Submit is enabled with 0 research selected** *(research is optional)*.
- [ ] Selecting 1 locks remaining options; unticking releases them.
- [ ] The **Teaching Load** target shows the hours configured in A3 (e.g. 21).
- [ ] Instruction/support targets allocated in Phase C appear with their custom descriptions and durations.
- [ ] Select 1 research target → **Submit IPCR for Review**.
- [ ] On submit and page reload:
      - Research checkbox remains **checked and disabled / read-only** as submitted.
      - Overall status updates to **"Pending Review"** (does *not* skip directly to Program Chair approval).
      - Verify all targets persist on dashboard: mandatory Teaching Load, selected Research target, and distributed Extension target.

### E2. Assigned research combination
Log in as the faculty who received a direct assignment from D2:
- [ ] Assigned research is **checked and disabled**, badged "Assigned by RET Chair".
- [ ] Assigned description and duration/deadline carry over from the chair's assignment.
- [ ] Faculty can optionally select an additional self-selected research target if rank menu quota allows, or submit directly.
- [ ] Submit IPCR → both assigned and self-selected targets are retained.

### E3. Zero research / Non-RET-eligible faculty (Direct bypass)
Log in as a faculty whose rank has no research rule (or choose 0 research targets):
- [ ] Sees the read-only **Extension** card and allocated instruction targets.
- [ ] Submits IPCR → submission **bypasses RET review completely** and immediately transitions to **"Waiting for Approval"** (Program Chair queue).
- [ ] Confirm Teaching Load and Extension targets remain intact.

---

## Phase F — Reviews, return, resubmit, and lock

### F1. RET Chair review & approval
RET Chair → **Commitments**.

- [ ] Faculty from E1 and E2 appear in the review queue; faculty from E3 (0 research / non-RET) do **not** appear here.
- [ ] **Submitted Targets** shows selected Research **and** distributed Extension as read-only rows (🔒 Not editable).
- [ ] **Unselected Indicators** lists unselected Research indicators only.
- [ ] Edit a reviewed quantity and add an item remark → Save → persists.
- [ ] **Approve** → submission advances out of RET queue and moves to Program Chair review queue.

### F2. RET Chair reject / return flow (Edge case)
*Test on a secondary faculty submission or before approving:*
- [ ] RET Chair selects **Reject / Return** with remarks (e.g. "Please pick an alternative research indicator").
- [ ] Faculty dashboard shows **Returned** status with RET Chair's remarks.
- [ ] Research checkbox is **editable again**.
- [ ] Faculty switches selection and resubmits → status resets to **"Pending Review"** and re-enters RET Chair queue.

### F3. Program Chair review & return (Deadlock regression test)
Program Chair → **Commitments**.

- [ ] Faculty submission appears with full target list: mandatory Teaching Load, approved Research target, Extension target, and instruction/support allocations.
- [ ] Research shows badge **"Approved by RET Chair"**; Extension shows approved.
- [ ] Program Chair edits a standard workload quantity / adds an item remark.
- [ ] Program Chair clicks **Return** with remarks (e.g. "Adjust teaching hours or instruction target").
- [ ] Faculty logs in:
      - Sees **Returned** alert with Program Chair's remarks.
      - Standard workload targets are editable.
      - **Research target remains locked / approved** (not reset to unapproved).
- [ ] Faculty adjusts a target and clicks **Resubmit for Approval**.
- [ ] **Critical Deadlock Check**:
      - Submission returns directly to Program Chair queue (`overall_status = 'Pending'`).
      - Research target still shows **"Approved by RET Chair"** (does **not** revert to "Awaiting RET Chair Approval").
      - RET Chair queue remains unaffected (does not get stuck waiting for re-approval).

### F4. Final approval and lock
Program Chair → **Commitments**.

- [ ] Program Chair clicks **Approve** → faculty dashboard updates to "Approved".
- [ ] Faculty logs in and clicks **Lock My IPCR**.
- [ ] Committed targets page displays all targets (Instruction, Support, Research, Extension, Teaching Load) with quantities, deadlines, and durations intact.
- [ ] Once locked, the IPCR is read-only and cannot be re-submitted or modified.

---

## Phase G — Evidence and scoring

Faculty → **Evidence Gathering**.

### G1. Checklist
- [ ] **Actual Accomplishment** column shows the target sentence with blanks.
- [ ] Badge reads "Time to complete not reported".

### G2. Report a target
- [ ] **Accomplishment Details** card shows the composed sentence, "Completed in",
      the target duration for reference, and status radios.
- [ ] There is **no "Tag Co-Authors" section** anywhere in the modal.
- [ ] Upload a PDF with a quantity → **Accomplished Qty** updates.
- [ ] Upload a second file → quantity accumulates.
- [ ] **Delete** one of your own files → quantity drops back.
- [ ] Enter **Completed in** = 4 of 6 → status **Completed** → Save.
- [ ] **Computed Rating** badges populate: Q · E · T → Average.
- [ ] The sentence now reads with real values.
- [ ] On a target whose description was **auto-generated** (Auto badge was showing when it
      was submitted): confirm the actual-accomplishment sentence substitutes the reported
      quantity/duration into the `within X units` clause at the **end** of the sentence, not
      into the middle of the indicator text — a mismatch there would mean the cleaning logic
      in `format_ipcr_target_description` let a second duration-shaped phrase through.
- [ ] Selecting a non-Completed status **disables** the "Completed in" field.
- [ ] Type a **Remarks** note (e.g. `Chairperson, BSDS`) → Save → reopen → still there.

**Timeliness spot-checks** (target 6 months):

| Completed in | RT | Expected T |
|---|---|---|
| 4 | .33 | **5** |
| 5 | .17 | **4** |
| 6 | .00 | **3** |
| *Partially completed at deadline* | — | **2** |
| *Not yet begun* | — | **1** |

**Quantity spot-checks** (target qty 10):

| Accomplished | RQn | Expected Q |
|---|---|---|
| 13+ | ≥1.30 | **5** |
| 12 | 1.20 | **4** |
| 10 | 1.00 | **3** |
| 6 | .60 | **2** |
| 5 | .50 | **1** |

### G3. Client Satisfaction
On the indicator tagged in A8:
- [ ] Only that target's modal shows the **Client Satisfaction Rating** dropdown.
- [ ] *Very Satisfactory* → **E = 4**, sentence reads "…with Very Satisfactory rating."
- [ ] Other targets show **no** dropdown.

### G4. Research & Extension timeliness
- [ ] The **research** target has a duration (from D1) — `T` is not `—` once reported.
- [ ] The **extension** target likewise (from D3).

### G5. Summary of Ratings
- [ ] Lists each **real category name** with Weight % · Average · Weighted, then
      Total Overall → Final Weighted → Adjectival.
- [ ] Categories are in **I / II / III order**, not alphabetical.
- [ ] Percentages match A7 (50 / 40 / 10).
- [ ] Adjectival matches: ≥4.75 Outstanding · ≥3.75 Very Satisfactory · ≥3.00 Satisfactory ·
      ≥2.01 Unsatisfactory · else Poor.

### G6. Submit evidences
- [ ] **Submit Evidences** → flash message includes the Final Weighted Rating and Adjectival.
- [ ] **Uploading is now locked** — a notice replaces the form; existing files still viewable.
- [ ] Verify persisted in database:

```sql
SELECT f.emp_id, f.final_score, f.adjectival_rating,
       b.weight_group AS category, b.raw_avg, b.weight_pct, b.weighted_value
FROM tbl_final_scores f
LEFT JOIN tbl_final_score_breakdown b ON b.score_id = f.score_id
WHERE f.term_id = (SELECT term_id FROM tbl_academic_terms WHERE is_active = 1);
```

- [ ] One score row + one breakdown row per category; re-submitting does not duplicate.

---

## Phase H — Verification

### H1. Program Chair
Program Chair → **Evidence Verification** → a faculty's details modal.

- [ ] **Reported & Rating** column shows *Completed in 4 months of 6 months*, the Client
      Satisfaction rating where applicable, and Q · E · T · Avg badges.
- [ ] The **actual accomplishment sentence** shows under each target description.
- [ ] **Status** column shows Approved / n Pending / n Returned / No evidence.
- [ ] **View Uploaded Evidence** opens **truly full-screen**, and the file renders.
- [ ] Each file has **Approve** and **Return**.
- [ ] **Return** without a reason is refused; with a reason it saves and displays.
- [ ] After deciding, that file's buttons disappear.

### H2. RET Chair
RET Chair → evidence details.

- [ ] Research/extension evidence is listed — the viewer is **not empty** when a count shows.
- [ ] Viewer opens full-screen; **Approve / Return** present and working.
- [ ] Return requires a reason; the reason displays on the item.

### H3. Faculty sees the return
- [ ] The returned file shows **Returned** with its reason.
- [ ] **Uploading is unlocked again** for that target only.
- [ ] The returned file no longer counts toward Accomplished Qty, and the rating updates.
- [ ] Re-upload and re-submit → back to Pending.

### H4. Dean
Dean → **Final Verification**.

- [ ] Faculty with submitted evidence packages are listed.
- [ ] Click **Review IPCR** → official printable IPCR document form is rendered directly inside the review modal (commitments, indicators, accomplishments, Q·E·T scores, summary ratings, and signatories).
- [ ] **Approve IPCR** → the faculty's targets become **Dean Approved**.
- [ ] **Return to Faculty** sends it back with confirmation.
- [ ] Approved tables allow viewing the finalized official IPCR anytime.

---

## Phase I — Designated Faculty (full cycle)

Log in as DESIGNATED_FACULTY.

- [ ] Selection table columns are readable — the description does not squeeze Target Qty
      and Deadline into squares.
- [ ] Selection uses **duration number + unit dropdown**.
- [ ] The **Teaching Load** target shows the *Designated* hours from A3 (e.g. 10) under **Core Functions**.
- [ ] Instruction allocated by their Program Chair in Phase C appears under **Core Functions** (locked).
- [ ] Targets picked from the pool land under **Strategic Priorities/Support Functions**.
- [ ] Pick a pool target and leave its description blank → it live-fills with the standard
      auto wording (Auto badge) as you set quantity/duration; typing over it hides the badge
      and shows **Reset to Auto**, which restores the auto text on click.
- [ ] **Add custom target** modal has description, quantity and **Target Duration** value + unit dropdown.
- [ ] A custom target saves and appears under **Strategic Priorities/Support Functions**
      — it does **not** get an Auto badge (custom items are always free text, never mirrored).
- [ ] **Submit** → the Dean sees it in **IPCR Draft Approval**.
- [ ] Dean edits a quantity, adds a remark, and **returns** it → designated faculty sees remarks.
- [ ] **Resubmit** → back to the Dean.
- [ ] Dean **approves** → designated faculty can **Lock** → targets committed with durations.
- [ ] Evidence Gathering has the **Accomplishment Details** card (sentence, Completed in,
      completion status, Client Satisfaction where applicable, Q·E·T badges).
- [ ] Saving those details persists and the badges update.
- [ ] **Summary of Ratings** uses the **Designated** weights (75 / 25) — *not* 50/40/10.

**Category split — the counts must match the two sections on My IPCR:**
- [ ] Count the targets in **1. Core Functions** and **2. Strategic Priorities & Support
      Functions** on the My IPCR page.
- [ ] The Summary of Ratings shows **those same two counts**.
- [ ] Only the **teaching load** and **Program-Chair-allocated instruction** are Core. Pool selections, custom items and oversight cascades are Strategic Priorities/Support
      — *even when their target type is Instruction*.
- [ ] Neither weighted category shows **0 targets** while the other holds them all.

**Evidence submission routing — plain Designated Faculty goes through the Program Chair:**
- [ ] Upload evidence for all committed targets and **Submit Evidences**.
- [ ] Log in as the Program Chair of this person's department → **Evidence Verification** →
      this Designated Faculty appears in the **pending** queue (not yet Dean-visible).
- [ ] Log in as Dean → **Final Verification** → this person is **absent** until the Program
      Chair submits the package to the Dean.
- [ ] Program Chair reviews the files and clicks **Submit to Dean** → *now* the Dean sees them
      in the pending queue.
- [ ] Repeat for a Program Chair's / RET Chair's / Dean's **own** evidence: it should reach the
      Dean's queue directly on submit, skipping Program Chair review (no one else is positioned
      to review a chair's own evidence).

---

## Phase J — Program Chair / RET Chair / Dean own IPCR

Run after B and C so there are cascades and allocations to pick up.

### J1. Access and navigation
- [ ] As **PROGRAM_CHAIR**: sidebar shows **My Performance → My IPCR**.
- [ ] It opens **with your Program Chair navigation still present**.
- [ ] Clicking one of those items returns you to your dashboard **on that exact section**.
- [ ] Same for **RET_CHAIR** and **DEAN**, each showing their own items.
- [ ] Regular **FACULTY** has **no** My IPCR item.
- [ ] **ADMIN** has none, and `/designated/` directly is refused.

### J2. Core Functions — the instruction they were allocated
- [ ] **Program Chair**: the instruction allocated to them in Phase C appears under
      **Core Functions**, alongside the mandatory teaching load.
- [ ] **RET Chair**: same.
- [ ] **Dean**: same.
- [ ] Quantities and durations match what the Program Chair entered.

### J3. Strategic Priorities/Support — oversight cascades
- [ ] **Program Chair**: pre-filled with **every** target the Dean cascaded to their
      department, at **full quota** (cascade `5` to WST → the WST chair reads **5**).
- [ ] Rows are badged **"Departmental Oversight — Fixed Quota"**; the **quantity is locked**
      (not editable — it's the department's/RET's whole cascade, not a share), but the
      **checkbox is pre-checked** (not disabled) like any other row, and the **deadline
      (duration value + unit) is editable** — there's no other source for it, and Timeliness
      scoring needs it.
- [ ] Leaving an oversight row's deadline blank and submitting is **refused**, same as any
      other target.
- [ ] **RET Chair**: pre-filled with everything cascaded to **RET / Extension**, full quantity,
      same locked-quantity / editable-deadline behaviour.
- [ ] **Dean**: pre-filled with the **college-wide total** of every Instruction-type indicator
      cascaded to any department/RET (summed across all of them — cascade `15/15/15/6/0` across
      WST/DST/NST/BSDS/RET → the Dean reads **51**), badged and locked the same way a chair's
      single-department oversight row is.
- [ ] All of them can still add from the selectable pool.

### J4. Claimed targets are not selectable
- [ ] A target cascaded to a department or to RET does **not** appear in the pool anyone
      else can select from.
- [ ] Another Designated Faculty sees only unclaimed instruction/support targets.
- [ ] The RET Chair's own free-pick pool likewise excludes anything already cascaded to
      RET / Extension — it has no personal-allocation table the way Instruction does for a
      Program Chair, so there's no legitimate reason for it to be pickable there too.

### J5. The same indicator, both ways
- [ ] A chair may hold one indicator **twice** — the oversight copy (full quota, Strategic
      Priorities/Support) and their own allocated teaching work (Core Functions). Submit and
      confirm **exactly one row of each** appears — not two of either.
- [ ] For **Program Chair/RET Chair**, in Summary of Ratings the oversight copy sits under
      **Strategic Priorities/Support (75%)** and the personal copy under **Core Functions
      (25%)**, regardless of the oversight indicator's own type (Instruction or Support).
- [ ] For the **Dean specifically**, an Instruction-type oversight total (e.g. the summed
      report-of-grades) sits under **Strategic Priorities/Support (75%)** as before, but a
      Support-type oversight total (e.g. summed professional meetings/faculty advisers/client
      satisfaction surveys) sits under **Core Functions (25%)** instead — this is intentional
      and matches the Dean's real filled-out IPCR; Program Chair/RET Chair behavior for the
      same Support-type indicators is unchanged.
- [ ] Dean's **IPCR Draft Approval** modal shows the same split — for a chair, the oversight
      copy under Strategic Priorities, not duplicated into Core Functions; for the Dean's own
      draft, Instruction-type oversight under Strategic Priorities and Support-type oversight
      under Core Functions.
- [ ] In that modal, with nothing touched, **Approve IPCR is enabled** (not permanently
      disabled by a false "quantities were modified" detection).
- [ ] Edit a quantity in the modal → Approve correctly becomes disabled ("must return to
      faculty"); revert it → Approve re-enables.
- [ ] **Program Chair's evidence-verification modal** for this chair/faculty shows the same
      two tables — Core Functions, then Strategic Priorities & Support Functions — matching
      their own My IPCR page, not a category-based breakdown (Strategic/Research/Extension/
      Support) with the oversight row under the wrong heading.

### J6. Dean sees the chairs & assigns College-Wide targets
- [ ] Dean → **Target Assignment** lists Program Chairs and the RET Chair among designated faculty with their assigned targets count.
- [ ] Click **Assign** on a chairperson / designated faculty → modal shows College-Wide targets with total and remaining quotas.
- [ ] Check a **College-Wide** target, set quantity, custom description, and duration (value + unit dropdown) → **Save Assignments** → badge updates.
- [ ] Leave the description blank on one target instead → it live-fills with the standard
      auto wording (Auto badge) from the target's own indicator text and quota-quantity.
- [ ] Log in as that chair / designated faculty → the assigned College-Wide target appears on their IPCR under **Strategic Priorities & Support Functions** with the specified quantity and duration.

**Dean's Review / Add Target modal** (during their own IPCR review of a designated faculty/chair):
- [ ] Open **unpicked target items** for a submission awaiting review, add one with quantity
      but no description → it auto-fills with the standard wording (Auto badge); adjusting
      the quantity/duration before saving updates the preview live.
- [ ] Type a custom description instead → Auto badge hides, **Reset to Auto** appears and
      restores the auto text on click.
- [ ] Save → reopening the review shows the same Auto/customized state you left it in.

### J7. Full cycle
- [ ] A chair submits their own IPCR → Dean reviews → approves → chair locks.
- [ ] The chair's Summary of Ratings shows both categories populated (Core Functions 25% and Strategic Priorities/Support Functions 75%).

---

## Phase K — Print IPCR

Run after G (ratings exist) and A4 (signatories set).

### K1. Regular Faculty
Faculty → **Print IPCR** (new tab).

- [ ] Title reads **INDIVIDUAL PERFORMANCE COMMITMENT AND REVIEW (IPCR)**.
- [ ] Opening: *"I, NAME, faculty member of the College of Information and Communications
      Technology, … for the period JANUARY to JUNE 2026."*
- [ ] First column header is **MFO/PAP**.
- [ ] Sections: **I. Strategic Priorities (50%) · II. Core Functions (40%) ·
      III. Support Functions (10%)**.
- [ ] Under Core Functions: **A. Research** then **B. Extension…**, in that order.
- [ ] Rating columns **Q¹ E² T³ A⁴** match the badges on the evidence panel.
- [ ] **Final Average Rating** row present.
- [ ] Summary box in **I / II / III** order, then Total Overall → Final Weighted →
      **Adjectival Rating inside the box**.
- [ ] Legend and the **Discussed with / Assessed by / Final Rating by** footer.
- [ ] Signature names match A4 — Reviewed by is **their Program Chair**.

### K2. Designated Faculty and chairs
- [ ] First column header is **Output**.
- [ ] A Program Chair's opening reads *"Program Chairperson of the … program of the …"*.
- [ ] Sections: **I. Strategic Priorities/Support Functions (75%) · II. Core Functions (25%)**.
- [ ] Sub-section under I is **A. Administrative Functions**.
- [ ] Summary box uses **75 / 25**.
- [ ] Reviewed by is **the Dean**, per A4.

### K3. Remarks
- [ ] The note typed in G2 appears in the **Remarks** column against that target.
- [ ] Clearing it leaves the column blank, not whitespace.
- [ ] At least one printed target's description was **auto-generated** (never hand-edited) —
      confirm it reads as a complete, correctly-worded sentence, not truncated or duplicated
      wording (e.g. no `"...within 6 months within 3 months"`).

### K4. Draft vs final
- [ ] Before Dean approval, a red **DRAFT** banner appears.
- [ ] After Dean approval, the banner is gone.
- [ ] A faculty who has not locked is redirected with *"No committed IPCR to print yet."*

### K5. Print settings
Press **Print / Save as PDF** → **More settings**:

- [ ] Paper **Letter 8.5 × 11**, Layout **Landscape**, Scale **100**.
- [ ] An outer **border frames the whole form** on every page.
- [ ] Toolbar buttons do **not** print.
- [ ] Text legible at 100%, no clipped columns.

> A typical form runs to **2 sheets** — targets on page 1, summary and signatures on page 2.
> That is expected; the sample IPCR runs to 3.

---

## Phase L — Admin maintenance

### L1. Faculty roster
Admin → **HR Roster**.

- [ ] **Add** a faculty profile with all fields → appears in the list.
- [ ] **Edit** their rank, department and **designation** → persists.
- [ ] **Deactivate** a profile → they no longer appear in allocation or assignment lists.
- [ ] Changing a designation from `Regular Faculty` to `Program Chair` gives that person a
      **My IPCR** item next login.

### L2. CSV import
- [ ] Import a CSV of profiles → rows are created.
- [ ] A malformed row is reported rather than silently skipped.
- [ ] Re-importing the same file does not duplicate people.

### L3. Backup
- [ ] **Backup** downloads a `.sql` file.
- [ ] The file contains `INSERT` statements for the main tables and is not empty.

### L4. Account security
Admin → **System Security**.

- [ ] **Reset password** for a user → they can log in with the new one.
- [ ] **Lock account** → that user is refused at login with a clear message.
- [ ] Unlock → they can log in again.
- [ ] **Audit log** shows the term opening, password reset and lock actions.

---

## Phase M — Permissions and security

Each of these should be **refused**. They are the checks that matter most.

### M1. Cross-role access
- [ ] A **Regular Faculty** opening `/admin/`, `/dean/`, `/prog_chair/`, `/ret_chair/` → refused.
- [ ] A **Program Chair** opening `/admin/` or `/dean/` → refused.
- [ ] **ADMIN** opening `/designated/` → refused (Admin has no IPCR).
- [ ] A **Regular Faculty** opening `/designated/` → refused (they use `/faculty/`).

### M2. Cross-user data
- [ ] Faculty A **cannot delete** Faculty B's evidence.
- [ ] Faculty A **cannot view** Faculty B's evidence file via its URL.
- [ ] Faculty A **cannot save accomplishment details** against Faculty B's target.
- [ ] A Program Chair sees only **their own department's** faculty.
- [ ] A Program Chair of WST cannot review a DST faculty's IPCR.

### M3. Workflow guards
- [ ] A faculty cannot submit evidence before their IPCR is locked.
- [ ] A faculty cannot upload after submitting evidences (until something is returned).
- [ ] A locked IPCR cannot be edited.
- [ ] Extension distribution cannot be run twice.

---

## Phase N — Auto-generated IPCR target descriptions

Individual phases above (C, D1–D3, I, J6) already exercise the live-mirroring and Reset-to-Auto
UI on each dashboard. This phase covers the behaviors that cut across all of them: what happens
with JS disabled, what happens across a role handoff, and what a mismatched legacy description
does.

### N1. Backend fallback (JS disabled)
- [ ] With JavaScript disabled in the browser, submit a target allocation (Program Chair,
      RET Chair Direct Assignment, or Dean College-Wide Assignment) with the description field
      left completely blank.
- [ ] The submission **succeeds** — no validation error blocks it — and the saved row shows
      the standard auto-generated description on reload, exactly as if JS had filled it live.
- [ ] This applies to all five hard-fail points that existed before this feature: Program
      Chair allocation, RET Chair Research Menu rule, RET Chair Direct Assignment, RET Chair
      Extension Distribution, and Dean College-Wide Assignment — pick at least two to spot-check.

### N2. Staleness across a role handoff
- [ ] Dean cascades a quota of `5` to a department (Phase B).
- [ ] Program Chair allocates it to a faculty member with quantity `5`, leaves the description
      blank (Auto badge showing) → Save.
- [ ] Program Chair re-opens the allocation and changes the quantity to `3`, without touching
      the description field → Save.
- [ ] Reload → the saved description now reads **"3 ..."**, not the stale "5 ..." — confirms
      the backend recomputes from the row's current quantity/duration whenever the Auto flag
      is still set, rather than keeping whatever text was last written to the column.

### N3. Legacy mode / mismatched indicator text (no placeholders)
- [ ] As Admin, create a master indicator with **no** `{qty}`/`{duration}` tokens, whose
      description already contains a leading quantity or a trailing duration phrase in the old
      manual style, e.g. `"1 Research paper published in a refereed journal"`.
- [ ] Allocate it with a **different** quantity, e.g. `2` → the generated description reads
      `"2 1 Research paper published..."` (the mismatch is left visible, not silently
      "corrected") — this is expected: only an *exact*-matching leading quantity gets cleaned.
- [ ] Allocate the same indicator with duration `3 months` when the indicator text already
      ends in `"...within 6 months"` → the generated description shows only **one** duration
      clause (`"...within 3 months"`), not both — confirms the trailing-duration clause is
      always stripped before the current duration is appended, regardless of match.

### N4. Placeholder mode — the real-world common case
Uses the indicator created in A8 with `{qty}`/`{duration}` tokens, e.g. `"Submit {qty}
accurate report of grades within {duration} after the final examination period"`.

- [ ] Assign it via any dashboard with quantity `15`, duration `10 days`, description left
      blank → the live preview (and the saved value) reads `"Submit 15 accurate report of
      grades within 10 days after the final examination period"` — the number lands **exactly
      where the placeholder was**, not prepended to the front.
- [ ] Reuse the **same** indicator at a different cascade level with a different quantity, e.g.
      a Program Chair distributing a smaller share (`3`) of a Dean-level total (`15`) — the
      generated text shows only `3`, with no leftover `15` anywhere in the sentence.
- [ ] Leave `{duration}` unset (no duration entered yet) → it renders as `____`, matching the
      paper form's own blank convention, not the literal text `{duration}`.
- [ ] **Evidence/accomplishment check** (this is the specific bug this redesign fixed): report
      an **actual** quantity/duration different from the target's (e.g. target `15`/`10 days`,
      actual `12`/`8 days`) on a target that is still on **Auto** → the printed "Actual
      Accomplishment" sentence shows `12` and `8 days`, substituted at the same placeholder
      positions. Before this redesign, this exact shape silently printed the *target* text
      unchanged — neither actual value appeared anywhere.
- [ ] Repeat the same report on a target where the description was **customized** (Auto turned
      off) → the actual values are **not** guaranteed to substitute correctly (pre-existing,
      documented limitation of free-text customization — see Known Gap below) — confirm this is
      unchanged, not a new regression.

### N5. Custom ad-hoc targets — the three composition branches
Designated Faculty (including a Program Chair, RET Chair, or Dean on their own IPCR) →
**Add Custom Target**. Each branch is decided by what you typed, with no guessing; the live
preview under the form always shows exactly what will be saved.

- [ ] **Plain phrase, no numbers.** Description `"Number of workshops conducted"`, Quantity `5`,
      Duration `6 months` → preview reads `"5 Number of workshops conducted within 6 months"`.
      Add it; the row shows that same sentence, and the Quantity/Duration columns show `5` and
      `6 months`.
- [ ] **Full sentence with its own numbers, untagged.** Description
      `"Report 3 activities within 6 months"`, Quantity `1` → preview reads back the sentence
      **exactly as typed**, with no `1` prepended. This is the fix for the confusing
      `"1 Report 3 activities within 6 months"`: when the system can't know which number is the
      tracked quantity, it never invents one.
- [ ] **Same sentence, tagged.** With `"Report 3 activities within 6 months"` still in the field,
      use the tag buttons below it: click **Qty** on `3`, then **Dur** on `6`. Confirm all of:
      - the description becomes `Report {qty:3} activities within {duration:6:months}`;
      - the **Target Quantity** field jumps to `3` and goes read-only, with the
        "Taken from the number you tagged" note visible;
      - the **Duration** field/unit jump to `6` / `months` and go read-only;
      - the preview still reads `"Report 3 activities within 6 months"` — braces never shown;
      - **Undo last tag** releases the field back to editable.
- [ ] Tagging `6` as **Dur** consumes the word `months` too — the preview must read
      `"...within 6 months"`, never `"...within 6 months months"`.
- [ ] Submit the tagged target, then have the reviewer open it (Program Chair review, then the
      Dean's IPCR Draft Approval modal) → the sentence reads correctly in both, with no literal
      `{qty}`/`{duration}` anywhere and no duplicated number.
- [ ] **Accomplishment check** — the payoff for tagging. Lock the IPCR, then report an actual
      quantity/duration different from the target (e.g. actual `2` in `4 months`) → the printed
      "Actual Accomplishment" reads `"Report 2 activities within 4 months"`, substituted
      **mid-sentence**. Repeat on the *untagged* version of the same target: only the duration
      updates and the `3` stays put — expected, and the reason to tag.
- [ ] A custom description containing an incidental number, e.g. `"Conduct ISO 9001 audit"` with
      Quantity `2` → saved verbatim, `9001` untouched, no `2` prepended.

### N6. Percent quantities, empty deadlines, and half-finished tagging
The three defects behind a real Dean IPCR that saved as
`"100 % of undergraduate programs with valid accreditation in ____"`.

- [ ] **Percent carried over.** Author an indicator as `{qty:80%} of undergraduate student
      population enrolled in priority programs in {duration:6:months}`. Assign it at quantity
      `75` → the description reads `75% of …`, not `75 of …` and not `80% of …`. The Admin's
      indicator-list preview and the assigned description now agree.
- [ ] **Empty deadline seeds from the token.** Open a dashboard where that indicator has never
      had a deadline entered → the Deadline field is pre-filled `6 months` from
      `{duration:6:months}`, the sentence reads `… in 6 months`, and the field is still
      editable. It must **not** render `… in ____` on load. Change the deadline to `3 weeks`
      → the sentence follows.
- [ ] A `{duration}` token with **no** embedded default seeds nothing and still renders `____`
      until a deadline is entered — unchanged, and correct.
- [ ] Confirm the row stays on **Auto** through all of the above (the Auto badge remains, no
      Reset button appears) — the whole point is that nobody has to hand-edit the text, since
      hand-editing permanently freezes the row.
- [ ] **Half-finished tagging is caught.** In Add Custom Target, type
      `Accomplish 3 activities in 6 months`, tag only the `6` as **Dur**, and leave the `3`
      untagged with Target Quantity at `1` → a warning names both numbers ("says 3 but Target
      Quantity is 1") and the **Add** button is disabled. This is the exact state that
      previously saved as a sentence reading 3 with a quantity column reading 1.
- [ ] Now tag the `3` as **Qty** → warning clears, Add re-enables, quantity syncs to `3`.
      Alternatively set Target Quantity to `3` by hand → warning also clears.
- [ ] An entirely **untagged** description with numbers still warns but stays submittable —
      that is the documented verbatim branch (Known Gap 17), not an error.
- [ ] No warning when the only untagged number is the deadline's own value, e.g.
      `Accomplish 3 activities in 6 months` with quantity `3` and deadline `6 months`.
- [ ] Cancel and reopen the modal → warning cleared, Add re-enabled, fields editable again.

### N7. Correcting a returned IPCR (Known Gap 16, fixed)
Run as any Designated Faculty, then repeat as a Program Chair and as the **Dean** on their own
IPCR — the Dean's own IPCR uses this same shared flow, and this is where the dropped-custom-target
bug was first seen.

- [ ] Submit an IPCR that includes at least one custom target, then have the reviewer **return**
      it with overall remarks and a per-item note.
- [ ] Reopen the returned IPCR → the banner now says the targets are editable again, the
      **Add Target** button is back, quantity/deadline inputs are editable, and the Dean's
      overall remarks and per-item notes are all still visible.
- [ ] The previously saved **custom target still appears**, with an editable Quantity, an
      editable deadline, and a **Remove** button. Its sentence reads correctly — no literal
      `{qty}`/`{duration}`, no duplicated number.
- [ ] Change a standard target's quantity, change the custom target's quantity **and** deadline,
      unselect one standard target, and add one new custom target. Re-submit.
- [ ] Reopen → every one of those five changes persisted. In particular the newly added custom
      target is present (this is the exact bug: it used to be silently dropped, because
      "Re-submit" only flipped `review_status` and never rebuilt the targets).
- [ ] For a **tagged** custom target, changing the quantity on re-submit updates the number
      inside the sentence too. For an untagged one it does not — expected, see Known Gap 17.
- [ ] Remove a custom target, re-submit, reopen → it is gone, and the remaining targets are
      unaffected.
- [ ] The reviewer sees the corrected values (Program Chair review list, then the Dean's IPCR
      Draft Approval modal), with the prior review cleared so it can be reviewed fresh.
- [ ] Deadline-specific case from the original gap report: have the reviewer add a target with
      **no deadline**, return the IPCR → the owner can now fill that deadline in themselves and
      re-submit, with no direct database edit needed.
- [ ] Negative check — an IPCR that is merely **awaiting** review (not returned) stays read-only,
      and an **approved** or **locked/committed** one stays read-only.

---

## Appendix — Known gaps

1. **Rank rules reset each term** by design; redo D1 for a new term.
2. **Extension distribution is permanent** for a term — no unlock in the UI.
3. **Legacy targets** set before the duration work score as un-timed (`T = —`).
4. The **return-reason prompt** is a plain browser dialog, not a styled modal.
5. `Adjectival` efficiency type exists but nothing uses it by default.
6. **Signatory rules are unconfirmed** for two cases: who reviews the Dean's own IPCR, and
   a non-chair designated faculty's. The latter resolves to the Dean. Editable in A4.
7. **A weighted category with no targets contributes nothing**, deflating the final rating
   rather than renormalising. The case that surfaced this was a categorisation bug, since
   fixed; no gate was built.
8. **Eight tables carry a different collation** from the original schema. Harmless today;
   the repair is in `MIGRATION_group7.sql`.
9. **Export DPCR was removed** (adviser's call). Print IPCR is the only document output.
10. **Four unscoped deletes** in the submit paths remove draft targets from *earlier* terms.
    No current-term behaviour is affected and committed targets are untouched, but
    historical drafts are lost on resubmit.
11. **Co-author claiming was removed entirely** (group's call, out of scope). The table,
    the four routes, the six model functions and the `is_co_authored` UI in all four
    dashboards are gone; `MIGRATION_group17.sql` drops `tbl_co_authors`.
12. **108 evidence PDFs are tracked in git.** They are runtime uploads and will keep
    accumulating; `app/uploads/evidence/` should be gitignored and untracked.
13. **In legacy mode (no `{qty}`/`{duration}` placeholders), auto-generated descriptions omit
    the duration clause if the indicator text already contains an unrelated mid-sentence
    duration-shaped phrase** (e.g. an indicator worded "...as needed every 3 months for
    continuous improvement") — `format_ipcr_target_description` deliberately falls back to
    `"[Quantity] [Indicator]"` rather than risk a second duration match corrupting the
    actual-accomplishment sentence (see the module's docstring). Only applies to indicators
    without placeholders; work around it by adding `{qty}`/`{duration}` tokens, rewording the
    master indicator, or typing the description by hand.
14. **`{duration}` only renders the system's standard unit vocabulary**
    (days/weeks/months/semesters via `format_duration()`) — an indicator wanting different
    wording (e.g. "10 *working* days" rather than "10 days") either accepts the closest
    standard unit or has that target's description typed manually per recipient with Auto
    turned off. Not solved by the placeholder redesign; explicitly out of scope.
15. **A customized (non-Auto) description's actual-accomplishment sentence keeps the
    pre-existing, position-dependent substitution limitation** — `build_actual_accomplishment`
    only reliably substitutes the actual quantity/duration when they sit where the regex
    expects (quantity at the very start of the string, duration as the first matching phrase).
    This predates the whole auto-description feature and is unrelated to whether the indicator
    uses placeholders; it only stops being a problem when the description is left on Auto,
    since that path substitutes deterministically instead of guessing via regex.
16. ~~A designated faculty/chair cannot self-correct a Dean-rejected submission's data.~~
    **Fixed 2026-09-01.** A returned IPCR is editable again (`can_edit = not has_submitted or
    is_returned`, `app/routes/designated.py`), and "Re-submit IPCR for Approval" now posts the
    full submit path, which rebuilds `tbl_draft_targets` and resets the Dean review, instead of
    only flipping `review_status`. Existing custom targets round-trip through the positional
    `custom_*[]` fields with editable quantity and deadline, and can be removed. The old
    `/designated/resubmit_ipcr` route still exists but nothing in the UI posts to it.
17. **An untagged custom target that contains its own numbers is stored verbatim** — the
    Quantity and Duration fields still drive scoring and still show in their own columns, but
    they are not woven into the sentence, and the actual-accomplishment sentence can only
    substitute the duration. This is deliberate (see the three-branch comment in
    `submit_designated_ipcr`): with a free-typed sentence there is no way to tell a tracked
    quantity from a year level or a standard number, and prepending regardless produced the
    confusing `"1 Report 3 activities within 6 months"`. Tagging the number resolves it fully.
18. ~~A percent quantity loses its `%` on substitution.~~ **Fixed 2026-09-01.** A trailing `%`
    in the embedded default is now treated as a *unit* and carried over, so `{qty:80%}` at
    assigned quantity `75` renders `75%`. The number still always comes from the assignment,
    never from the default. This was not merely cosmetic: the Admin's own preview rendered
    `80%` while substitution wrote `80`, so people retyped the `%` by hand, which flipped the
    row to customized and froze whatever else was wrong in it (see Phase N6).

---

## Appendix — Starting from a clean database

To run the whole script against empty data, use
[`old MDS/RESET_for_clean_test.sql`](old%20MDS/RESET_for_clean_test.sql). It clears every
term, target, evidence file, review and score, and keeps what the system cannot rebuild.

**Three things must survive a truncate:**

| Keep | Why |
|---|---|
| `tbl_employee_profiles`, `tbl_auth_credentials`, `tbl_system_access` | Registration *claims* an existing profile via `register_user()` in `app/models/user.py`, landing the claim as PENDING for Admin approval — so clearing these locks everyone out — **unless** you then run `python bootstrap_admin.py`, which writes the first Admin directly. With that, even a fully empty database is recoverable. |
| `tbl_target_categories` | 23 places in the code match exact slugs (`instruction`, `research`, …). Rebuildable — Admin → Criteria now has a **Slug** field — but a generated slug like `a_instructions` breaks routing **silently**, so it has to be typed exactly. |

`tbl_ipcr_signatories` is now **self-healing**: opening Institution Setup recreates the five
standard blocks if they are missing, without disturbing any already configured. Only the
names need re-entering.

- [ ] After the reset, confirm config survived: target types, IPCR categories, signatories,
      departments and employee profiles all still return rows.
- [ ] Delete orphaned files in `app/uploads/evidence/` if you want a genuinely clean state.
- [ ] Phase 0 still passes — accounts were preserved.

**Starting with no accounts at all** (optional, the harshest reset):
- [ ] Truncate the three account tables as well, then run `python bootstrap_admin.py`.
- [ ] The script **refuses** if an Admin already exists, unless given `--force`.
- [ ] It rejects a weak password, a duplicate employee ID and a duplicate email.
- [ ] The created Admin can log in, and lands on the Admin dashboard.
- [ ] From there, add profiles (Phase L) so everyone else can claim theirs at `/register`.

---

## Appendix — Reset a single term (keeps other terms intact)

```sql
-- Replace 99 with the term you are resetting.
SET @t = 99;

DELETE b FROM tbl_final_score_breakdown b
  JOIN tbl_final_scores f ON b.score_id = f.score_id WHERE f.term_id = @t;
DELETE FROM tbl_final_scores               WHERE term_id = @t;
DELETE ra FROM tbl_ret_assignments ra
  JOIN tbl_master_indicators mi ON ra.indicator_id = mi.indicator_id WHERE mi.term_id = @t;
DELETE FROM tbl_criteria_weights           WHERE term_id = @t;
DELETE FROM tbl_teaching_load_config       WHERE term_id = @t;

-- Review records
DELETE ri FROM tbl_ipcr_chair_review_items ri
  JOIN tbl_ipcr_chair_review r ON ri.review_id = r.review_id WHERE r.term_id = @t;
DELETE FROM tbl_ipcr_chair_review WHERE term_id = @t;
DELETE ri FROM tbl_ipcr_ret_review_items ri
  JOIN tbl_ipcr_ret_review r ON ri.review_id = r.review_id WHERE r.term_id = @t;
DELETE FROM tbl_ipcr_ret_review WHERE term_id = @t;
DELETE ri FROM tbl_ipcr_dean_review_items ri
  JOIN tbl_ipcr_dean_review r ON ri.review_id = r.review_id WHERE r.term_id = @t;
DELETE FROM tbl_ipcr_dean_review WHERE term_id = @t;

-- Target data (uploaded files on disk are not removed)
DELETE e FROM tbl_evidence_repo e JOIN tbl_committed_targets ct ON e.target_id = ct.target_id
  JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id WHERE mi.term_id = @t;
DELETE ct FROM tbl_committed_targets ct
  JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id WHERE mi.term_id = @t;
DELETE dt FROM tbl_draft_targets dt
  JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id WHERE mi.term_id = @t;
DELETE da FROM tbl_draft_allocation da
  JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id WHERE mi.term_id = @t;
```

> Departments, criteria, IPCR categories, institution settings and signatories are **not**
> term-scoped, so the reset leaves them intact — that is intentional.

> Clearing the target tables also clears the chairs' own IPCRs, including their oversight
> rows. Those repopulate from `tbl_cascaded_quotas` as soon as the chair reopens My IPCR,
> so Phase B need not be redone.
