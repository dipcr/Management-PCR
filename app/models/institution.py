"""
Institution-level configuration that used to be hardcoded in the application:

  * Departments / programs — previously fixed columns (WST/DST/NST/BSDS) in the
    Dean's cascade form and a hardcoded col_map in the Excel export.
  * Teaching load — previously the literals '21 hours of Teaching Load' (regular)
    and '10 hours of Teaching Load' (designated) scattered across the submit paths,
    with a free-text '1 Semester' deadline that could not be scored for Timeliness.

Both are now data, so the system scales to new programs and to a change in the
mandated teaching load without a code edit.
"""

from app.models.criteria import (DESIGNATION_TYPES, GENERAL_BAND, RANK_BANDS, rank_band,
                                 resolve_designation_type)

# Cascade targets that are not departments. The Dean assigns quotas to these
# alongside the real programs.
ROLE_RET = 'RET / Extension'
ROLE_COLLEGE_WIDE = 'College-Wide'
SPECIAL_CASCADE_ROLES = [ROLE_RET, ROLE_COLLEGE_WIDE]

# Not a real assigned_to_role value and never written to the database -- purely an in-memory
# marker so get_oversight_targets/get_oversight_indicator_ids/get_oversight_evidence can
# recognize "the Dean's oversight spans every department" without a second parallel code path.
ROLE_DEAN_ALL_DEPARTMENTS = '__DEAN_ALL_DEPARTMENTS__'


# ─────────────────────────────────────────────
# Departments
# ─────────────────────────────────────────────

def get_departments(cursor, active_only=True):
    """Departments/programs in display order. `department_name` is the value stored on
    tbl_employee_profiles.specialization and tbl_cascaded_quotas.assigned_to_role."""
    query = """
        SELECT department_id, department_name, department_code, display_order, is_active
        FROM tbl_departments
    """
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY display_order, department_name"
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def save_department(conn, cursor, name, code, department_id=None, display_order=None):
    """Create or rename a department. The name is what targets are routed by, so
    renaming one also updates the rows that reference it.

    display_order is only used on creation (auto-assigned when not given); an update never
    touches it, so a rename can't silently reset a department's position."""
    name = (name or '').strip()
    if not name:
        return False, "Department name is required."
    try:
        if department_id:
            cursor.execute("SELECT department_name FROM tbl_departments WHERE department_id = %s",
                           (department_id,))
            row = cursor.fetchone()
            old_name = row[0] if row else None

            cursor.execute("""
                UPDATE tbl_departments
                SET department_name = %s, department_code = %s
                WHERE department_id = %s
            """, (name, (code or '').strip() or None, department_id))

            # Keep the rows that route by name in step with the rename.
            if old_name and old_name != name:
                cursor.execute(
                    "UPDATE tbl_employee_profiles SET specialization = %s WHERE specialization = %s",
                    (name, old_name))
                cursor.execute(
                    "UPDATE tbl_cascaded_quotas SET assigned_to_role = %s WHERE assigned_to_role = %s",
                    (name, old_name))
        else:
            if display_order is None:
                cursor.execute("SELECT COALESCE(MAX(display_order), 0) + 10 FROM tbl_departments")
                display_order = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO tbl_departments (department_name, department_code, display_order)
                VALUES (%s, %s, %s)
            """, (name, (code or '').strip() or None, int(display_order)))

        conn.commit()
        return True, f"Department '{name}' saved."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def set_department_active(conn, cursor, department_id, is_active):
    """Soft-delete / restore a department. Existing faculty and quotas keep their
    routing value; the department simply stops appearing in new cascades."""
    try:
        cursor.execute("UPDATE tbl_departments SET is_active = %s WHERE department_id = %s",
                       (1 if is_active else 0, department_id))
        conn.commit()
        return True, ("Department activated." if is_active else "Department deactivated.")
    except Exception as e:
        conn.rollback()
        return False, str(e)


def reorder_department(conn, cursor, department_id, direction):
    """Swap this department's display_order with its immediate neighbor (up or down),
    ordered the same way get_departments() orders (display_order, department_name)."""
    if direction not in ('up', 'down'):
        return False, "Invalid direction."
    try:
        cursor.execute(
            "SELECT department_id, display_order FROM tbl_departments "
            "ORDER BY display_order, department_name")
        rows = cursor.fetchall()
        ids = [r[0] for r in rows]
        try:
            idx = ids.index(int(department_id))
        except ValueError:
            return False, "Department not found."
        neighbor_idx = idx - 1 if direction == 'up' else idx + 1
        if neighbor_idx < 0 or neighbor_idx >= len(rows):
            return False, "Already at the edge."
        this_id, this_order = rows[idx]
        other_id, other_order = rows[neighbor_idx]
        cursor.execute("UPDATE tbl_departments SET display_order = %s WHERE department_id = %s",
                       (other_order, this_id))
        cursor.execute("UPDATE tbl_departments SET display_order = %s WHERE department_id = %s",
                       (this_order, other_id))
        conn.commit()
        return True, "Order updated."
    except Exception as e:
        conn.rollback()
        return False, str(e)


# ─────────────────────────────────────────────
# Teaching load
# ─────────────────────────────────────────────

# Fallbacks used only when a term has no configuration yet, matching the values that
# were previously hardcoded.
DEFAULT_TEACHING_LOAD = {
    'Regular Faculty': 21,
    'Designated Faculty': 10,
}
DEFAULT_LOAD_DURATION = (6, 'months')


def get_teaching_load_config(cursor, term_id, designation_type=None):
    """Raw teaching-load rows for a term (optionally one designation type)."""
    query = """
        SELECT config_id, term_id, designation_type, rank_band, hours,
               duration_value, duration_unit
        FROM tbl_teaching_load_config
        WHERE term_id = %s
    """
    params = [term_id]
    if designation_type:
        query += " AND designation_type = %s"
        params.append(designation_type)
    query += " ORDER BY designation_type, rank_band"
    cursor.execute(query, tuple(params))
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_teaching_load_grid(cursor, term_id, designation_type):
    """{rank_band: {hours, duration_value, duration_unit}} including the General row."""
    grid = {}
    for row in get_teaching_load_config(cursor, term_id, designation_type):
        grid[row['rank_band']] = {
            'hours': row['hours'],
            'duration_value': row['duration_value'],
            'duration_unit': row['duration_unit'],
        }
    return grid


def get_teaching_load_mode(cursor, term_id, designation_type):
    """'SPECIFIC' when per-rank rows exist, otherwise 'GENERAL'."""
    cursor.execute("""
        SELECT COUNT(*) FROM tbl_teaching_load_config
        WHERE term_id = %s AND designation_type = %s AND rank_band <> %s
    """, (term_id, designation_type, GENERAL_BAND))
    return 'SPECIFIC' if cursor.fetchone()[0] > 0 else 'GENERAL'


def resolve_teaching_load(cursor, term_id, designation_type, academic_rank=None):
    """
    The teaching load that applies to one employee: (hours, duration_value, duration_unit).

    A General row wins for every rank; otherwise the employee's rank band is used.
    Falls back to the previously hardcoded values when a term has no configuration,
    so the mandatory teaching-load target is never missing.
    """
    # Callers may pass a job title ('Program Chair') rather than a weight table, so resolve
    # it the same way the scoring roll-up does.
    designation_type = resolve_designation_type(designation_type) or 'Regular Faculty'

    cursor.execute("""
        SELECT hours, duration_value, duration_unit FROM tbl_teaching_load_config
        WHERE term_id = %s AND designation_type = %s AND rank_band = %s
    """, (term_id, designation_type, GENERAL_BAND))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            SELECT hours, duration_value, duration_unit FROM tbl_teaching_load_config
            WHERE term_id = %s AND designation_type = %s AND rank_band = %s
        """, (term_id, designation_type, rank_band(academic_rank)))
        row = cursor.fetchone()

    if row:
        return int(row[0]), int(row[1]), row[2]
    hours = DEFAULT_TEACHING_LOAD.get(designation_type, 21)
    return hours, DEFAULT_LOAD_DURATION[0], DEFAULT_LOAD_DURATION[1]


def teaching_load_description(hours):
    """The indicator description for a teaching load target — the text the rest of the
    system matches on when detecting the mandatory target."""
    return f"{hours} hours of Teaching Load"


def save_teaching_load(conn, cursor, term_id, designation_type, mode, rows):
    """
    Replace a term + designation type's teaching load configuration.

    `rows` is a list of (rank_band, hours, duration_value, duration_unit). As with the
    weight matrix, the two modes are mutually exclusive: all existing rows for the pair
    are cleared first so a configuration is never half General and half per-rank.
    """
    if designation_type not in DESIGNATION_TYPES:
        return False, "Invalid designation type."
    if mode not in ('GENERAL', 'SPECIFIC'):
        return False, "Invalid teaching load mode."
    try:
        cursor.execute(
            "DELETE FROM tbl_teaching_load_config WHERE term_id = %s AND designation_type = %s",
            (term_id, designation_type))

        saved = 0
        for band, hours, dur_value, dur_unit in rows:
            if not hours or int(hours) <= 0:
                continue
            cursor.execute("""
                INSERT INTO tbl_teaching_load_config
                    (term_id, designation_type, rank_band, hours, duration_value, duration_unit)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (term_id, designation_type, band, int(hours),
                  int(dur_value or 6), dur_unit or 'months'))
            saved += 1

        conn.commit()
        label = "all ranks" if mode == 'GENERAL' else "per academic rank"
        return True, f"Teaching load saved for {designation_type} ({label})."
    except Exception as e:
        conn.rollback()
        return False, str(e)


# ─────────────────────────────────────────────
# Printed IPCR — institution text and signatories
# ─────────────────────────────────────────────

SIGNATORY_BLOCKS = ['REVIEWED_BY', 'APPROVED_BY', 'ASSESSED_BY', 'FINAL_RATING_BY']
SIGNATORY_BLOCK_LABELS = {
    'REVIEWED_BY': 'Reviewed by',
    'APPROVED_BY': 'Approved by',
    'ASSESSED_BY': 'Assessed by',
    'FINAL_RATING_BY': 'Final Rating by',
}
# How a block's name is obtained. Two of the four are positions in the org chart, so they
# follow whoever currently holds the role rather than being retyped each term.
SIGNATORY_SOURCES = ['FIXED', 'PROGRAM_CHAIR', 'DEAN']


def get_institution_settings(cursor):
    """All institution settings as a plain dict."""
    cursor.execute("SELECT setting_key, setting_value FROM tbl_institution_settings")
    return {row[0]: row[1] for row in cursor.fetchall()}


def save_institution_setting(conn, cursor, key, value):
    """Upsert one institution setting."""
    try:
        cursor.execute("""
            INSERT INTO tbl_institution_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value)
        """, (key, (value or '').strip() or None))
        conn.commit()
        return True, "Saved."
    except Exception as e:
        conn.rollback()
        return False, str(e)


# The signature blocks a printed IPCR always has. The set is fixed by the form itself —
# there is no such thing as an extra block — so rather than offering an "add" button the
# panel guarantees these exist. Without them the printed form has no signature lines and
# nothing in the UI could recreate them.
DEFAULT_SIGNATORIES = [
    ('REVIEWED_BY',     'Regular Faculty',    'PROGRAM_CHAIR', 'Immediate Supervisor'),
    ('REVIEWED_BY',     'Designated Faculty', 'DEAN',          'Immediate Supervisor'),
    ('ASSESSED_BY',     None,                 'DEAN',          'Supervisor'),
    ('APPROVED_BY',     None,                 'FIXED',         'Head of Office'),
    ('FINAL_RATING_BY', None,                 'FIXED',         'Head of Office'),
]


def ensure_default_signatories(conn, cursor):
    """
    Create any missing signature block. Idempotent — an existing block is left exactly as
    the Admin configured it, names included.
    """
    created = 0
    for block_key, designation_type, source, title in DEFAULT_SIGNATORIES:
        if designation_type is None:
            cursor.execute("""
                SELECT signatory_id FROM tbl_ipcr_signatories
                WHERE block_key = %s AND designation_type IS NULL
            """, (block_key,))
        else:
            cursor.execute("""
                SELECT signatory_id FROM tbl_ipcr_signatories
                WHERE block_key = %s AND designation_type = %s
            """, (block_key, designation_type))
        if cursor.fetchone():
            continue
        cursor.execute("""
            INSERT INTO tbl_ipcr_signatories
                (block_key, designation_type, source, full_name, position_title)
            VALUES (%s, %s, %s, NULL, %s)
        """, (block_key, designation_type, source, title))
        created += 1
    if created:
        conn.commit()
    return created


def get_signatories(cursor, conn=None):
    """
    Signatory configuration rows for the Admin panel.

    Passing conn lets the panel self-heal a missing set — the blocks are otherwise only
    creatable by re-running the migration.
    """
    if conn is not None:
        ensure_default_signatories(conn, cursor)
    cursor.execute("""
        SELECT signatory_id, block_key, designation_type, source, full_name, position_title
        FROM tbl_ipcr_signatories
        ORDER BY FIELD(block_key, 'REVIEWED_BY', 'APPROVED_BY', 'ASSESSED_BY', 'FINAL_RATING_BY'),
                 designation_type
    """)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def save_signatory(conn, cursor, signatory_id, source, full_name, position_title):
    """Update one signatory block. A FIXED block needs a name; derived blocks do not."""
    source = source if source in SIGNATORY_SOURCES else 'FIXED'
    name = (full_name or '').strip() or None
    if source == 'FIXED' and not name:
        return False, "A fixed signatory needs a name."
    try:
        cursor.execute("""
            UPDATE tbl_ipcr_signatories
            SET source = %s, full_name = %s, position_title = %s
            WHERE signatory_id = %s
        """, (source, name if source == 'FIXED' else None,
              (position_title or '').strip() or None, signatory_id))
        conn.commit()
        return True, "Signatory saved."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def _employee_label(cursor, emp_id=None, designation=None, specialization=None):
    """Name + academic rank of a person identified by id, or by designation (+ department)."""
    if emp_id:
        cursor.execute("""
            SELECT first_name, last_name, academic_rank FROM tbl_employee_profiles
            WHERE emp_id = %s
        """, (emp_id,))
    elif designation and specialization:
        cursor.execute("""
            SELECT first_name, last_name, academic_rank FROM tbl_employee_profiles
            WHERE designation = %s AND specialization = %s AND leave_status = 'Active'
            LIMIT 1
        """, (designation, specialization))
    elif designation:
        cursor.execute("""
            SELECT first_name, last_name, academic_rank FROM tbl_employee_profiles
            WHERE designation = %s AND leave_status = 'Active'
            LIMIT 1
        """, (designation,))
    else:
        return None, None

    row = cursor.fetchone()
    if not row:
        return None, None
    return f"{row[0]} {row[1]}".strip().upper(), row[2]


def resolve_signatories(cursor, emp_id, designation_type, specialization=None):
    """
    The four signature blocks for one ratee's printed IPCR.

    Derived blocks follow the org chart — a regular faculty's reviewer is their own Program
    Chair, a designated faculty's is the Dean — so they stay correct when a chair changes.
    A block with no resolvable name renders blank, exactly as the paper form is issued.
    """
    rows = get_signatories(cursor)
    resolved = {}
    for block in SIGNATORY_BLOCKS:
        # A row scoped to this designation type wins over the shared (NULL) row.
        match = next((r for r in rows
                      if r['block_key'] == block and r['designation_type'] == designation_type), None)
        if not match:
            match = next((r for r in rows
                          if r['block_key'] == block and r['designation_type'] is None), None)
        if not match:
            resolved[block] = {'name': None, 'title': None}
            continue

        source = match['source']
        if source == 'PROGRAM_CHAIR':
            name, _ = _employee_label(cursor, designation='Program Chair',
                                      specialization=specialization)
        elif source == 'DEAN':
            name, _ = _employee_label(cursor, designation='Dean')
        else:
            name = (match['full_name'] or '').strip().upper() or None

        resolved[block] = {
            'name': name,
            'title': match['position_title'],
            'label': SIGNATORY_BLOCK_LABELS[block],
        }
    return resolved
