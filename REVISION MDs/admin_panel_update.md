# Implementation Plan: Admin Dashboard User Interview Revisions

Address feedback from user interviews for the Digital IPCR System by streamlining the Admin Dashboard: removing the term deadline field/KPIs, standardizing and validating the Academic Year format (`YYYY - YYYY`), and updating the Management section sidebar navigation hierarchy and naming.

---

## User Review Required

> [!NOTE]
> **Active Term Overview Card**:
> In the Overview section, removing the "Term Deadline" card leaves an empty spot in the two-column grid. We propose replacing it with an **"ACTIVE ACADEMIC TERM"** card displaying `{{ active_term.academic_year }} ({{ active_term.semester }})` (or `"No Active Term"`). This keeps the dashboard layout balanced and informative.

> [!NOTE]
> **Sidebar Naming Choice**:
> In the sidebar and main view headers, `HR Roster` will be renamed to **`Faculty Configuration`** (while keeping its CSV upload and profile management features intact).

---

## Proposed Changes

### 1. Remove Term Deadline Field, KPIs, and Functions

#### [MODIFY] [admin_dashboard.html](file:///c:/Users/chest/Management-PCR/app/templates/admin_dashboard.html)
- **Overview Section (`#nav-overview`)**:
  - Replace the "TERM DEADLINE" KPI card with "ACTIVE ACADEMIC TERM" displaying `active_term.academic_year` & `active_term.semester` (or "No Active Term").
- **Term Configuration Section (`#nav-term`)**:
  - Remove the "Submission Deadline" date picker input field (`name="deadline_date"`) from the "Open New Term" card form.
  - Remove the `<th>Deadline</th>` column header and `<td>{{ term.deadline_date }}</td>` column in the "Term History" table.

#### [MODIFY] [admin.py (Routes)](file:///c:/Users/chest/Management-PCR/app/routes/admin.py)
- In `admin_open_term()`:
  - Remove extraction of `request.form.get('deadline_date')`.
  - Update call to `open_new_term(...)` to pass `deadline_date=None` (or omit).
  - Update audit log message: `f"New term opened: {academic_year} {semester}"`.

#### [MODIFY] [admin.py (Models)](file:///c:/Users/chest/Management-PCR/app/models/admin.py)
- In `get_admin_kpis(cursor)`:
  - Remove the `DATEDIFF(deadline_date, CURDATE())` query fragment.
  - Remove `days_remaining` and `term_status` calculations.

#### [MODIFY] [term.py (Models)](file:///c:/Users/chest/Management-PCR/app/models/term.py)
- In `open_new_term(conn, cursor, academic_year, semester, deadline_date=None, period_start=None, period_end=None)`:
  - Make `deadline_date` optional with a default of `None`.
- In `get_all_terms(cursor)`:
  - Keep query compatible with existing schema.

#### [MODIFY] [dean_dashboard.html](file:///c:/Users/chest/Management-PCR/app/templates/dean_dashboard.html)
- Clean up line 137 where `active_term.deadline_date` was printed in the header banner.

---

### 2. Standardize & Validate Academic Year Field (`YYYY - YYYY`)

#### [MODIFY] [admin_dashboard.html](file:///c:/Users/chest/Management-PCR/app/templates/admin_dashboard.html)
- In the "Open New Term" form:
  - Update `#openTermAcademicYear` input:
    - Set `placeholder="YYYY - YYYY (e.g. 2025 - 2026)"`.
    - Add `pattern="^\d{4}\s*-\s*\d{4}$"` and `maxlength="11"`.
    - Add helper text below the field explaining the required format (`YYYY - YYYY` with consecutive years).
  - Add client-side JavaScript input handler:
    - Automatically strip non-digits / non-hyphens on input.
    - Format input automatically as digits are entered (e.g. typing `2025` then typing `2` automatically inserts ` - `).
    - Validate that Year 2 = Year 1 + 1 before form submission with user feedback.

#### [MODIFY] [admin.py (Routes)](file:///c:/Users/chest/Management-PCR/app/routes/admin.py)
- In `admin_open_term()`:
  - Add server-side regex validation `r'^(\d{4})\s*-\s*(\d{4})$'`.
  - Validate that `int(year2) == int(year1) + 1` and years are within a valid range (e.g., 2000–2099).
  - Normalize spacing to `"YYYY - YYYY"`.
  - If validation fails, flash a clear error message (`"Invalid Academic Year format. Please use consecutive years in YYYY - YYYY format (e.g., 2025 - 2026)."`), rollback/abort, and redirect.

---

### 3. Reorder Sidebar Navigation & Management Section Hierarchy

#### [MODIFY] [admin_dashboard.html](file:///c:/Users/chest/Management-PCR/app/templates/admin_dashboard.html)
- **Sidebar Nav Block (`{% block sidebar_items %}`)**:
  - Reorder the items under `<div class="nav-label">Management</div>` to:
    1. `<button class="nav-item" data-section="nav-term">` &rarr; **Term Configuration** (`ti-calendar`)
    2. `<button class="nav-item" data-section="nav-roster">` &rarr; **Faculty Configuration** (`ti-users`)
    3. `<button class="nav-item" data-section="nav-institution">` &rarr; **Institution Setup** (`ti-building`)
    4. `<button class="nav-item" data-section="nav-criteria">` &rarr; **Criteria** (`ti-sitemap`)
    5. `<button class="nav-item" data-section="nav-indicators">` &rarr; **Master Indicators** (`ti-target`)
- **Main Body Content Sections**:
  - Rename the section header on `#nav-roster` from `HR Roster Management` to `Faculty Configuration`.
  - Reorder the section container elements in the DOM (`nav-term`, `nav-roster`, `nav-institution`, `nav-criteria`, `nav-indicators`) to match the sidebar sequence for logical tab navigation and DOM order.

---

## Verification Plan

### Automated / Syntax & Validation Tests
- Run Python syntax checks and model tests to ensure no broken imports or query failures:
  ```powershell
  python -c "from app.models.admin import get_admin_kpis; from app.models.term import open_new_term; print('Models OK')"
  ```
- Test Academic Year regex logic against valid and invalid sample strings (`2025-2026`, `2025 - 2026`, `2024-2026`, `abc`, `2025`).

### Manual Verification
1. **Admin Dashboard Overview**:
   - Verify Overview renders with Roster Adoption Rate and Active Academic Term KPI cards.
2. **Term Configuration**:
   - Verify the Deadline input is gone.
   - Verify Term History table no longer has the Deadline column.
   - Test opening a term with valid `2025 - 2026` &rarr; succeeds and normalizes properly.
   - Test opening a term with invalid text (e.g., `2025 - 2028` or `abcd`) &rarr; blocked by frontend pattern and backend validator with clear error message.
3. **Sidebar Navigation**:
   - Verify the Management section shows:
     1. Term Configuration
     2. Faculty Configuration
     3. Institution Setup
     4. Criteria
     5. Master Indicators
   - Click each nav link to confirm smooth section switching.
