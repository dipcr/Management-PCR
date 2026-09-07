# Implementation Plan: Dean Draft IPCR Studio & Streamlined Chair IPCR Lifecycle

## 1. Problem Statement & Context
Based on consultations with an active institutional Program Chair:
- The IPCRs of **Program Chairs** and the **RET Chair** are fundamentally formulated by the **Dean**:
  1. **Departmental & RET Oversight Targets**: Automatically derived from institutional quotas cascaded by the Dean.
  2. **Teaching Load**: Mandated by institutional workload policy (10 hours for designated chairs/faculty).
  3. **College-Wide Targets**: Assigned directly to designated chairs and faculty members by the Dean.
  4. **Instruction Targets**: Distributed by the Program Chair to departmental faculty (including themselves) during Phase 1 Target Allocation.

### Current System Shortcomings
1. **Disconnected Dean Experience**: The Dean's Target Assignment modal currently only displays a raw checklist of College-Wide targets. The Dean cannot view the Chair's full IPCR picture (Departmental Oversight quotas and Teaching Load) when making assignments.
2. **Redundant Approval Loop**: Currently, Program Chairs and RET Chair must navigate to their own "My IPCR" (`/designated/`), check checkboxes, and submit a draft IPCR back to the Dean, who must then review and approve targets they themselves formulated.
3. **Workflow Continuity**: When the Dean finishes Quota Cascading, there is no guided prompt directing them to the next natural step: formulating and issuing the Draft IPCRs for the Chairs and designated staff.

---

## 2. Key Requirements & Architectural Decisions

### Decision 1: Post-Quota Cascading Guidance
- When the Dean locks Quota Cascading (`has_cascaded_quotas == True`), display a prominent banner/alert prompting the Dean:
  > *"Institutional quotas cascaded successfully! Next step: Proceed to Target Assignment to review and issue the Draft IPCRs for Program Chairs, RET Chair, and yourself."*
- Includes a direct CTA button navigating to `#nav-target-assign`.

### Decision 2: Target Assignment Panel & Modal Redesign (Draft IPCR Studio)
- In the Dean's Target Assignment table (`#assignDesignatedTable`):
  - Rename action button from `"Assign"` to `"Draft IPCR"`.
  - Update status column to show `"Draft IPCR Status"`: `"Issued / Approved"` (green), `"Drafted"` (blue), or `"Not Started"` (gray).
- Transform `#designatedAssignmentModal` into a full **Draft IPCR Studio**:
  - **Header**: Faculty Name, Rank, Designation, Program/Department.
  - **Table 1: Core Functions**:
    - Teaching Load (10 hours, locked).
    - Departmental Instruction Share (shows allocated units/subjects, or badge `"Pending Chair distribution"` if not yet divided).
  - **Table 2: Strategic Priorities & Support Functions**:
    - Departmental / RET Oversight Targets (locked quantity derived from cascaded quota; duration defaults to **6 months**, with duration/deadline selector).
    - College-Wide Targets (checkbox selection, target quantity input, duration/deadline selector, live remaining quota counter).
  - **Primary Action**: Button labeled `"Save & Issue Draft IPCR"`.

### Decision 3: Automated Approval for Chairs & Dean
- When the Dean issues the Draft IPCR for a **Program Chair**, **RET Chair**, or **Dean**:
  - Automatically populate `tbl_draft_targets` with `review_status = 'Approved'`.
  - Automatically record an `Approved` review in `tbl_ipcr_dean_review`.
  - On the Chair's `/designated/` ("My IPCR") panel:
    - Omit arbitrary pool selection checkboxes.
    - Display status badge: `"Dean Formulated (Pre-Approved)"`.
    - Once Core instruction targets are present, enable the **`"Lock & Commit IPCR"`** button directly.
    - The redundant submission and Dean approval loop is completely bypassed.

### Decision 4: Preserving Review for Plain Designated Faculty
- Plain Designated Faculty (coordinators, lab heads, etc.) author **custom targets** for specialized roles.
- For Plain Designated Faculty:
  - Dean's College-Wide assignments are stored in `tbl_draft_allocation`.
  - Faculty members log in, add their custom targets, and submit their draft to the Dean.
  - The Dean reviews and approves their draft via the existing Draft Approval panel (`#nav-draft-ipcr`).

---

## 3. Architecture & Code Impact

### A. Database Schema
- **No breaking schema migrations required**.
- Existing tables `tbl_cascaded_quotas`, `tbl_draft_allocation`, `tbl_draft_targets`, `tbl_ipcr_dean_review`, and `tbl_committed_targets` already have all necessary columns (`emp_id`, `indicator_id`, `is_admin_function`, `target_duration_value`, `target_duration_unit`, `review_status`).

### B. Dean Backend & Routes
- **`app/models/dean.py`**:
  - Add `get_designated_faculty_draft_preview(cursor, term_id, emp_id)`: Aggregates Teaching Load (`resolve_teaching_load`), Departmental/RET Oversight targets (`get_oversight_targets`), existing instruction allocations (`tbl_draft_allocation`), and College-Wide quotas into a single unified JSON payload.
  - Add `save_and_issue_designated_draft_ipcr(...)`: Saves College-Wide assignments to `tbl_draft_allocation`. For Chairs/Dean, populates `tbl_draft_targets` as `'Approved'` and creates an `'Approved'` record in `tbl_ipcr_dean_review`.
  - Update `get_designated_draft_submissions(cursor, term_id)`: Exclude pre-approved Chairs so the Dean's Draft Approval panel only displays Plain Designated Faculty with pending submissions.
- **`app/routes/dean.py`**:
  - Update `/designated_assignment_editor/<int:emp_id>` to invoke `get_designated_faculty_draft_preview`.
  - Update `/save_designated_assignments` to call `save_and_issue_designated_draft_ipcr`.

### C. Dean UI (`app/templates/dean_dashboard.html`)
- In `#nav-phase1`: Add alert banner prompting Dean to proceed to `#nav-target-assign` once quotas are locked.
- In `#nav-target-assign`: Rename `"Assign"` to `"Draft IPCR"`.
- In `#designatedAssignmentModal`: Render the two structured tables (Core Functions + Strategic Priorities & Support Functions) with clear badges, quantity inputs, duration selectors, and quota counters.

### D. Chair / Designated UI & Flow (`app/routes/designated.py` & `app/templates/designated_dashboard.html`)
- In `designated_dashboard()`:
  - Detect if the user is a Chair with a Dean-issued/pre-approved IPCR.
  - Show `"Dean Formulated (Pre-Approved)"` status banner.
  - If Core instruction targets are present, activate `"Lock & Commit IPCR"` directly.
- In `designated_lock_ipcr()`:
  - Support direct lock and commit into `tbl_committed_targets` for Dean-approved chair drafts.

---

## 4. Verification & Testing Steps

1. **Dean Quota Cascading to Draft IPCR Studio**:
   - Log in as Dean (`dean@test.com`).
   - Lock Quota Cascading and verify prompt banner appears.
   - Navigate to Target Assignment and click `"Draft IPCR"` for Computer Science Program Chair.
   - Verify modal displays:
     - Core: 10 hrs Teaching Load.
     - Support: Computer Science Departmental Oversight targets + College-Wide targets.
   - Select 2 College-Wide targets and click `"Save & Issue Draft IPCR"`.
2. **Program Chair Experience**:
   - Log in as Computer Science Program Chair.
   - Open `/designated/` ("My IPCR").
   - Verify that targets are pre-filled and marked `"Dean Formulated / Pre-Approved"`.
   - Distribute departmental instruction to themselves in Phase 1 Target Allocation.
   - Verify instruction targets appear in Core Functions, and `"Lock & Commit IPCR"` is immediately available without waiting for Dean review.
3. **Plain Designated Faculty Experience**:
   - Log in as Dean, assign College-Wide targets to a Plain Designated Faculty member.
   - Log in as that faculty member, add a custom target, and submit draft to Dean.
   - Verify they appear in the Dean's Draft Approval panel for review.
