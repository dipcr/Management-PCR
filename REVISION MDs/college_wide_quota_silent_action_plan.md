# Implementation Plan: College-Wide Target Allocation Controls (Cascade to Chairs vs. Silent)

## 1. Problem Statement & Context
In the Dean's **Phase 1: Institutional Quota Cascading**, the Dean sets target quotas across departments, RET, and **College-Wide**. Currently, any College-Wide target under the Support category automatically flows down to all Program Chairs' **Phase 1: Target Allocation** tables.

In a real-world institutional setting:
- Only specific College-Wide Support targets are intended for regular faculty distribution by Program Chairs.
- Other College-Wide Support targets are administrative or institutional duties intended exclusively for the Dean, Program Chairs, or Designated Faculty members.
- Currently, Program Chairs must manually skip editing these targets (leaving quantity at 0). If a Chair accidentally fills in a number or clicks "Auto Divide All", those institutional targets get cascaded to all regular faculty members' IPCRs.

This feature introduces action controls (**Cascade to Chairs** vs. **Silent / Dean Only**) on College-Wide targets in the Dean's Quota Cascading table.

---

## 2. Key Decisions & Requirements

- **Decision (Option 2)**: All College-Wide targets default to **Silent / Dean Only** (`allow_chair_allocation = 0`).
- **Explicit Action Required**: The Dean must explicitly click/toggle **"Cascade to Chairs"** (`allow_chair_allocation = 1`) if the target should flow down to Program Chairs for distribution to regular faculty.
- **Behavior for Program Chairs**:
  - Targets marked **Silent / Dean Only** will **NOT appear at all** on the Program Chair's Target Allocation table.
  - Targets marked **Cascade to Chairs** will appear with their College-Wide indicator badge as usual.
- **Behavior for Dean Designated Assignment**:
  - All College-Wide targets (whether Silent or Cascaded to Chairs) remain available in the Dean's dedicated panel: **"Assign College-Wide Targets to Designated Faculty & Chairs"**.
- **Database Default**: `allow_chair_allocation TINYINT(1) NOT NULL DEFAULT 0`.

---

## 3. Architecture & Code Impact

### A. Database Schema
- File: `old MDS/MIGRATION_group19.sql` & `db/schema.sql`
- Add column `allow_chair_allocation` to `tbl_cascaded_quotas`:
  ```sql
  ALTER TABLE `tbl_cascaded_quotas` 
  ADD COLUMN `allow_chair_allocation` TINYINT(1) NOT NULL DEFAULT 0;
  ```

### B. Dean Backend & Persistence
- **`app/models/dean.py`**:
  - Update `save_cascaded_quotas()` to store `allow_chair_allocation`:
    ```sql
    INSERT INTO tbl_cascaded_quotas (term_id, indicator_id, total_target_value, assigned_to_role, allow_chair_allocation)
    VALUES (%s, %s, %s, %s, %s)
    ```
- **`app/routes/dean.py`**:
  - In `cascade_quotas()`:
    - Read `cw_allow_allocation_{indicator_id}` from request form.
    - Set `allow_chair_allocation = 1` if explicitly checked/selected for College-Wide; `0` by default. (For departments and RET, default to 1).
  - In `dean_dashboard()`:
    - Include `allow_chair_allocation` in the `existing_quotas` dictionary passed to the template so locked or pre-existing quotas show their selected state.

### C. Dean UI (Quota Cascading Table)
- **`app/templates/dean_dashboard.html`**:
  - Inside the College-Wide column cell (`{% if role == 'College-Wide' %}`):
    - Render a clean two-state pill toggle below the number input:
      - `[ Silent (Dean Only) ]` (Active by default, muted gray)
      - `[ Cascade to Chairs ]` (Active when chosen, green)
    - Hidden input: `name="cw_allow_allocation_{{ indicator.indicator_id }}"` synced to the toggle.
    - When locked (`has_cascaded_quotas` is True):
      - Display a read-only badge indicating either `Silent` or `To Chairs`.

### D. Program Chair Filtering
- **`app/models/prog_chair.py`**:
  - In `get_chair_indicators(cursor, term_id, specialization)`:
    ```sql
    LEFT JOIN tbl_cascaded_quotas cw_cq
        ON cw_cq.indicator_id = mi.indicator_id AND cw_cq.term_id = mi.term_id
       AND cw_cq.assigned_to_role = 'College-Wide'
       AND cw_cq.allow_chair_allocation = 1
       AND tc.slug = %s
    ```
  - **No changes needed in `prog_chair_dashboard.html` or `prog_chair.py` routes**, completely protecting auto-divide logic and form submission from any breaking changes or array mismatch errors.

---

## 4. Verification & Testing Steps

1. **Database Migration**:
   - Apply `ALTER TABLE tbl_cascaded_quotas ADD COLUMN allow_chair_allocation TINYINT(1) NOT NULL DEFAULT 0;` to local MySQL database.
2. **Dean Quota Cascading**:
   - As Dean (`dean@test.com`), open **Phase 1: Institutional Quota Cascading**.
   - Set a College-Wide quota for a Support target (e.g. 15) and keep it as default **Silent (Dean Only)**.
   - Set a College-Wide quota for another Support target (e.g. 10) and click **Cascade to Chairs**.
   - Submit and confirm cascading.
   - Verify locked view displays the correct status pills (**Silent** vs **Cascade to Chairs**).
3. **Program Chair Dashboard**:
   - As Program Chair, open **Phase 1: Standard Target Allocation**.
   - Verify the "Silent" target is **hidden**.
   - Verify the "Cascade to Chairs" target is **visible**.
   - Test **Auto Divide All Targets** to ensure error-free distribution.
4. **Dean Designated Assignment**:
   - Open **Assign College-Wide Targets to Designated Faculty & Chairs** modal in Dean Dashboard.
   - Verify both Silent and Cascaded College-Wide targets are present and directly assignable to designated faculty.
