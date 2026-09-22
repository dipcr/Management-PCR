from datetime import datetime

from app.models.criteria import SLUG_INSTRUCTION, SLUG_SUPPORT
from app.models.ipcr_description import format_ipcr_target_description, render_indicator_preview


def _truncate_title(text, max_len=37):
    """Clean, readable indicator title for a compact flash message -- long descriptions
    would otherwise blow up a multi-indicator warning into an unreadable wall of text."""
    text = (text or '').strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + '...'


# ─────────────────────────────────────────────
# Existing functions (unchanged)
# ─────────────────────────────────────────────

def get_chair_indicators(cursor, term_id, specialization):
    """
    Indicators the Program Chair can allocate: those quota'd specifically for their own
    specialization, PLUS any Support Function indicator the Dean cascaded College-Wide instead
    (e.g. "Conduct/attend N Professional meetings," which isn't split per department in the
    DPCR). A dept-specific quota takes priority over a College-Wide one for the same indicator,
    if both happen to exist. `quota_source` tells the UI which bucket the number came from,
    since a College-Wide figure is a whole-college target, not this department's own pool to
    divide.

    The College-Wide fallback is deliberately restricted to Support (tc.slug = 'support').
    College-Wide Instruction/Strategic-Priorities indicators are institution-level rollup
    metrics (e.g. "80% of undergraduate programs with valid accreditation") that no individual
    faculty member personally commits to — they must never be offered to a Program Chair for
    per-faculty distribution.

    Within Support, the Dean additionally gates each College-Wide quota with
    `allow_chair_allocation` (set via the Cascade to Chairs / Silent toggle on the Quota
    Cascading table). Only rows explicitly marked "Cascade to Chairs" show up here — a Silent
    (Dean Only) quota is an institutional/administrative duty the Dean intends to keep off
    every regular faculty member's IPCR, so it's excluded from this query entirely rather than
    relying on the Chair to leave it at 0.
    """
    from app.models.connection import timed_query
    query = """
        SELECT mi.indicator_id, mi.indicator_description, mi.efficiency_type, tc.category_name, tc.slug,
               COALESCE(dept_cq.total_target_value, cw_cq.total_target_value) as dept_quota,
               CASE WHEN dept_cq.quota_id IS NOT NULL THEN 'DEPT' ELSE 'COLLEGE_WIDE' END as quota_source
        FROM tbl_master_indicators mi
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        LEFT JOIN tbl_cascaded_quotas dept_cq
            ON dept_cq.indicator_id = mi.indicator_id
           AND dept_cq.assigned_to_role = %s
        LEFT JOIN tbl_cascaded_quotas cw_cq
            ON cw_cq.indicator_id = mi.indicator_id
           AND cw_cq.assigned_to_role = 'College-Wide'
           AND cw_cq.allow_chair_allocation = 1
           AND tc.slug = %s
        WHERE mi.term_id = %s
          AND tc.review_lane = 'CHAIR' AND tc.is_core = 1
          AND (dept_cq.quota_id IS NOT NULL OR cw_cq.quota_id IS NOT NULL)
        ORDER BY tc.category_name, mi.indicator_id
    """
    return timed_query(cursor, query, (specialization, SLUG_SUPPORT, term_id), label="get_chair_indicators")


def get_specialization_faculty(cursor, specialization):
    """
    Everyone in this department the Program Chair allocates instruction targets to.

    That includes the department's designated faculty — the Program Chair themselves, the
    RET Chair, the Dean, and any other designated title — because a designated faculty's
    Core Functions are exactly the instruction the Program Chair cascades to them, plus the
    mandatory teaching load. The old filter listed only 'Regular Faculty' and 'Designated
    Faculty' literally, so anyone holding a chair or dean title never appeared as a
    recipient and their Core Functions stayed empty.

    Only system accounts with no IPCR at all are excluded.
    """
    from app.models.connection import timed_query
    from app.models.criteria import NON_FACULTY_DESIGNATIONS
    excluded = sorted(NON_FACULTY_DESIGNATIONS)
    placeholders = ','.join(['%s'] * len(excluded))
    query = f"""
        SELECT emp_id, first_name, last_name, academic_rank, leave_status, designation
        FROM tbl_employee_profiles
        WHERE (specialization = %s OR assigned_program = %s)
          AND leave_status = 'Active'
          AND designation IS NOT NULL AND designation <> ''
          AND designation NOT IN ({placeholders})
    """
    return timed_query(cursor, query, tuple([specialization, specialization] + excluded),
                       label="get_specialization_faculty")


def get_assigned_quantity_batch(cursor, term_id, indicator_ids, faculty_ids):
    """
    Get assigned quantities, custom descriptions, and deadlines for MULTIPLE indicators in ONE query.
    Returns dict: {indicator_id: {'assigned_quantity': qty, 'custom_description': desc, 'target_deadline': deadline}}
    Replaces N+1 get_assigned_quantity() calls.
    """
    if not faculty_ids or not indicator_ids:
        return {}
    from app.models.connection import timed_query
    fac_placeholders = ','.join(['%s'] * len(faculty_ids))
    ind_placeholders = ','.join(['%s'] * len(indicator_ids))
    query = f"""
        SELECT da.indicator_id, da.assigned_quantity, da.custom_description, da.target_deadline,
               da.target_duration_value, da.target_duration_unit, da.is_auto_description
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        JOIN tbl_employee_profiles ep ON da.emp_id = ep.emp_id
        WHERE mi.term_id = %s
          AND tc.review_lane = 'CHAIR'
          AND ep.designation = 'Regular Faculty'
          AND da.indicator_id IN ({ind_placeholders})
          AND da.emp_id IN ({fac_placeholders})
        GROUP BY da.indicator_id, da.assigned_quantity, da.custom_description, da.target_deadline,
                 da.target_duration_value, da.target_duration_unit, da.is_auto_description
    """
    rows = timed_query(cursor, query, [term_id] + indicator_ids + faculty_ids, label="get_assigned_quantity_batch")
    result = {}
    for row in rows:
        result[row['indicator_id']] = {
            'assigned_quantity': row['assigned_quantity'],
            'custom_description': row.get('custom_description'),
            'target_deadline': row.get('target_deadline'),
            'target_duration_value': row.get('target_duration_value'),
            'target_duration_unit': row.get('target_duration_unit'),
            'is_auto_description': row.get('is_auto_description')
        }
    return result


def get_assigned_quantity(cursor, term_id, indicator_id, faculty_ids):
    if not faculty_ids:
        return 0
    format_strings = ','.join(['%s'] * len(faculty_ids))
    query = f"""
        SELECT da.assigned_quantity
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        WHERE mi.term_id = %s AND da.indicator_id = %s AND da.emp_id IN ({format_strings})
        LIMIT 1
    """
    cursor.execute(query, [term_id, indicator_id] + faculty_ids)
    res = cursor.fetchall()
    return res[0][0] if res else 0


def save_chair_allocations_batch(conn, cursor, term_id, allocations, faculty_ids, specialization=None):
    try:
        if not faculty_ids:
            return False, "No active faculty found for this specialization."

        quota_warnings = []

        for item in allocations:
            # Newer callers pass a structured duration (value + unit) alongside the label,
            # and newest callers also pass an explicit auto/customized flag (from
            # wireAutoDescription in base.html) rather than leaving it to be inferred.
            duration_value, duration_unit, is_auto_flag = None, None, None
            if len(item) == 7:
                (indicator_id, assigned_quantity, custom_description,
                 target_deadline, duration_value, duration_unit, is_auto_flag) = item
            elif len(item) == 6:
                (indicator_id, assigned_quantity, custom_description,
                 target_deadline, duration_value, duration_unit) = item
            elif len(item) == 4:
                indicator_id, assigned_quantity, custom_description, target_deadline = item
            else:
                indicator_id, assigned_quantity = item[0], item[1]
                custom_description, target_deadline = None, None

            # Determine category of the indicator, and its description for auto-generation
            cursor.execute("""
                SELECT tc.slug, mi.indicator_description
                FROM tbl_master_indicators mi
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                WHERE mi.indicator_id = %s
            """, (indicator_id,))
            cat_row = cursor.fetchone()
            cat_slug = cat_row[0] if cat_row else ''
            indicator_description = cat_row[1] if cat_row else ''

            # is_auto_flag True (explicitly, from the frontend) always regenerates, even if
            # non-blank text was submitted — protects against client-side drift (Decision 1).
            # A blank description always regenerates too regardless of the flag, as a safety
            # net against ever storing an empty description.
            is_auto_description = 1 if (is_auto_flag is True or not custom_description) else 0
            if is_auto_description:
                custom_description = format_ipcr_target_description(
                    indicator_description, assigned_quantity, duration_value, duration_unit)

            if cat_slug == SLUG_INSTRUCTION:
                # Instruction targets are cascaded to both Regular and Designated Faculty
                target_emp_ids = faculty_ids
            else:
                # Support targets are cascaded to Regular Faculty ONLY
                format_strings = ','.join(['%s'] * len(faculty_ids))
                cursor.execute(f"""
                    SELECT emp_id FROM tbl_employee_profiles
                    WHERE emp_id IN ({format_strings}) AND designation = 'Regular Faculty'
                """, faculty_ids)
                target_emp_ids = [r[0] for r in cursor.fetchall()]

            try:
                assigned_quantity = int(assigned_quantity)
            except (TypeError, ValueError):
                assigned_quantity = 0

            if assigned_quantity <= 0:
                # A 0/blank quantity means the chair chose NOT to distribute this indicator
                # (common for a College-Wide indicator that doesn't apply to their faculty,
                # e.g. an admin-only Support item) — not "distribute a zero-quantity target."
                # Clear any prior distribution instead of leaving/creating a phantom 0-qty row
                # on every applicable faculty member's IPCR.
                if target_emp_ids:
                    del_placeholders = ','.join(['%s'] * len(target_emp_ids))
                    cursor.execute(
                        f"DELETE FROM tbl_draft_allocation WHERE indicator_id = %s AND emp_id IN ({del_placeholders})",
                        [indicator_id] + target_emp_ids
                    )
                continue

            # Non-fatal capacity check: flag (don't block) when the total about to be
            # distributed exceeds what the Dean actually cascaded for this indicator — a
            # chair may have a legitimate reason for the totals not to match exactly.
            if specialization and target_emp_ids:
                cursor.execute("""
                    SELECT COALESCE(dept_cq.total_target_value, cw_cq.total_target_value)
                    FROM tbl_master_indicators mi
                    LEFT JOIN tbl_cascaded_quotas dept_cq
                        ON dept_cq.indicator_id = mi.indicator_id AND dept_cq.assigned_to_role = %s
                    LEFT JOIN tbl_cascaded_quotas cw_cq
                        ON cw_cq.indicator_id = mi.indicator_id AND cw_cq.assigned_to_role = 'College-Wide'
                       AND cw_cq.allow_chair_allocation = 1
                    WHERE mi.indicator_id = %s
                """, (specialization, indicator_id))
                quota_row = cursor.fetchone()
                dept_quota = quota_row[0] if quota_row else None
                if dept_quota is not None:
                    total_distributed = assigned_quantity * len(target_emp_ids)
                    if total_distributed > dept_quota:
                        # Store the raw pieces, not a pre-formatted sentence -- the final
                        # message compacts/truncates these once every indicator has been
                        # processed, rather than concatenating a full sentence per indicator.
                        quota_warnings.append((total_distributed, dept_quota, indicator_description))

            for emp_id in target_emp_ids:
                # Check if an allocation record already exists in the draft staging table
                check_query = """
                    SELECT allocation_id 
                    FROM tbl_draft_allocation
                    WHERE emp_id = %s AND indicator_id = %s
                """
                cursor.execute(check_query, (emp_id, indicator_id))
                existing = cursor.fetchall()

                if existing:
                    update_query = """
                        UPDATE tbl_draft_allocation
                        SET assigned_quantity = %s, custom_description = %s, target_deadline = %s,
                            target_duration_value = %s, target_duration_unit = %s, is_auto_description = %s
                        WHERE allocation_id = %s
                    """
                    cursor.execute(update_query, (assigned_quantity, custom_description, target_deadline,
                                                  duration_value, duration_unit, is_auto_description, existing[0][0]))
                else:
                    insert_query = """
                        INSERT INTO tbl_draft_allocation (emp_id, indicator_id, assigned_quantity, custom_description, target_deadline,
                                                          target_duration_value, target_duration_unit, is_auto_description)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (emp_id, indicator_id, assigned_quantity, custom_description,
                                                  target_deadline, duration_value, duration_unit, is_auto_description))

        conn.commit()
        msg = "Targets distributed successfully to all faculty draft worklists."
        if quota_warnings:
            # Clean placeholder syntax (e.g. "{qty:50}") out of the raw indicator template
            # and truncate each title -- the full, repeated sentence-per-indicator this used
            # to build was the actual complaint (a wall of text once a few indicators went
            # over quota), not the underlying check.
            items = [
                f"'{_truncate_title(render_indicator_preview(desc))}' "
                f"(Distributed: {total} / Quota: {quota})"
                for total, quota, desc in quota_warnings
            ]
            if len(items) > 3:
                remaining = len(items) - 2
                summary = ", ".join(items[:2]) + f", ...and {remaining} other indicators."
            else:
                summary = ", ".join(items) + "."
            msg += " Warning: Quota exceeded for: " + summary
        return True, msg
    except Exception as e:
        conn.rollback()
        return False, str(e)


def check_chair_targets_saved(cursor, term_id, specialization):
    """
    Returns True if baseline departmental target allocations (Instruction & Support)
    have already been saved in tbl_draft_allocation for regular faculty members under `specialization` for `term_id`.
    College-wide targets personally assigned by the Dean to chairs are excluded.
    """
    if not term_id or not specialization:
        return False
    query = """
        SELECT COUNT(*) 
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        JOIN tbl_employee_profiles ep ON da.emp_id = ep.emp_id
        WHERE mi.term_id = %s 
          AND ep.specialization = %s
          AND tc.review_lane = 'CHAIR'
          AND ep.designation = 'Regular Faculty'
          AND da.assigned_quantity > 0
    """
    cursor.execute(query, (term_id, specialization))
    res = cursor.fetchone()
    return res[0] > 0 if res else False


# ─────────────────────────────────────────────
# New functions — Commitments & IPCR Review
# ─────────────────────────────────────────────

def get_pending_drafts_count(cursor, specialization, term_id):
    """
    Returns the count of faculty members under `specialization` who have
    submitted a draft IPCR (tbl_draft_targets) for the term that still
    have an overall_status of 'Pending' (or 'Waiting for Approval' or no review record yet).
    """
    query = """
        SELECT COUNT(DISTINCT dt.emp_id)
        FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        JOIN tbl_employee_profiles ep ON dt.emp_id = ep.emp_id
        LEFT JOIN tbl_ipcr_chair_review cr ON cr.emp_id = dt.emp_id AND cr.term_id = mi.term_id
        LEFT JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
        LEFT JOIN tbl_ipcr_ret_review rr ON rr.emp_id = dt.emp_id AND rr.term_id = mi.term_id
        LEFT JOIN tbl_ipcr_ret_review_items rri ON rri.review_id = rr.review_id AND rri.indicator_id = dt.indicator_id
        WHERE mi.term_id = %s
          AND ep.specialization = %s
          AND ep.designation = 'Regular Faculty'
          AND dt.review_status IN ('Pending Review', 'Waiting for Approval')
          AND (
              ((tc.review_lane = 'CHAIR' AND tc.is_core = 1) AND COALESCE(ri.reviewed_quantity, dt.proposed_quantity) > 0)
              OR (tc.review_lane = 'RET' AND COALESCE(rri.reviewed_quantity, dt.proposed_quantity) > 0)
              OR (tc.is_core = 0 AND dt.proposed_quantity > 0)
          )
          AND (cr.overall_status IS NULL OR cr.overall_status = 'Pending' OR cr.overall_status = 'Waiting for Approval')
    """
    cursor.execute(query, (term_id, specialization))
    result = cursor.fetchone()
    return result[0] if result else 0


def get_pending_draft_ipcrs(cursor, specialization, term_id):
    """
    Returns all faculty members under `specialization` who have submitted
    a Draft IPCR for the active term, along with their current review status.
    Faculty with no review record yet are treated as 'Pending Review'.
    Approved or Locked IPCRs are excluded from this list.
    """
    query = """
        SELECT
            ep.emp_id,
            CONCAT(ep.first_name, ' ', ep.last_name) AS faculty_name,
            ep.academic_rank,
            ep.specialization,
            (
                SELECT COUNT(dt2.draft_id)
                FROM tbl_draft_targets dt2
                JOIN tbl_master_indicators mi2 ON dt2.indicator_id = mi2.indicator_id
                JOIN tbl_target_categories tc2 ON mi2.category_id = tc2.category_id
                LEFT JOIN tbl_ipcr_chair_review cr2 ON cr2.emp_id = ep.emp_id AND cr2.term_id = mi2.term_id
                LEFT JOIN tbl_ipcr_chair_review_items ri2 ON ri2.review_id = cr2.review_id AND ri2.draft_id = dt2.draft_id
                LEFT JOIN tbl_ipcr_ret_review rr2 ON rr2.emp_id = ep.emp_id AND rr2.term_id = mi2.term_id
                LEFT JOIN tbl_ipcr_ret_review_items rri2 ON rri2.review_id = rr2.review_id AND rri2.indicator_id = dt2.indicator_id
                WHERE dt2.emp_id = ep.emp_id AND mi2.term_id = %s
                  AND (
                      ((tc2.review_lane = 'CHAIR' AND tc2.is_core = 1) AND COALESCE(ri2.reviewed_quantity, dt2.proposed_quantity) > 0)
                      OR (tc2.review_lane = 'RET' AND COALESCE(rri2.reviewed_quantity, dt2.proposed_quantity) > 0)
                      OR (tc2.is_core = 0 AND dt2.proposed_quantity > 0)
                  )
            ) AS target_count,
            CASE 
                WHEN (SELECT COUNT(*) FROM tbl_committed_targets ct 
                      JOIN tbl_master_indicators mi2 ON ct.indicator_id = mi2.indicator_id 
                      WHERE ct.emp_id = ep.emp_id AND mi2.term_id = %s AND ct.assigned_quantity > 0) > 0 THEN 'Locked'
                ELSE MAX(dt.review_status)
            END AS review_status,
            cr.review_id,
            cr.overall_remarks,
            cr.reviewed_at
        FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        JOIN tbl_employee_profiles ep ON dt.emp_id = ep.emp_id
        LEFT JOIN tbl_ipcr_chair_review cr
            ON cr.emp_id = dt.emp_id AND cr.term_id = mi.term_id
        WHERE mi.term_id = %s
          AND ep.specialization = %s
          AND ep.designation = 'Regular Faculty'
          AND dt.review_status IN ('Pending Review', 'Waiting for Approval', 'Approved', 'Returned')
          AND (cr.overall_status IS NULL OR cr.overall_status IN ('Pending', 'Rejected'))
          AND NOT EXISTS (
              SELECT 1 FROM tbl_committed_targets ct 
              JOIN tbl_master_indicators mi2 ON ct.indicator_id = mi2.indicator_id 
              WHERE ct.emp_id = ep.emp_id AND mi2.term_id = %s AND ct.assigned_quantity > 0
          )
        GROUP BY ep.emp_id, ep.first_name, ep.last_name,
                 ep.academic_rank, ep.specialization,
                 cr.review_id, cr.overall_status, cr.overall_remarks, cr.reviewed_at
        ORDER BY ep.last_name, ep.first_name
    """
    cursor.execute(query, (term_id, term_id, term_id, specialization, term_id))
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_locked_faculty_ipcrs(cursor, specialization, term_id):
    """
    Returns all faculty members under `specialization` who have either:
    - Locked/committed their IPCR (tbl_committed_targets rows exist), OR
    - Been approved by the Program Chair but not yet locked.
    """
    query = """
        SELECT
            ep.emp_id,
            CONCAT(ep.first_name, ' ', ep.last_name) AS faculty_name,
            ep.academic_rank,
            ep.specialization,
            COALESCE(
                NULLIF((SELECT COUNT(*) FROM tbl_committed_targets ct 
                        JOIN tbl_master_indicators mi2 ON ct.indicator_id = mi2.indicator_id 
                        WHERE ct.emp_id = ep.emp_id AND mi2.term_id = %s AND ct.assigned_quantity > 0), 0),
                (SELECT COUNT(*) FROM tbl_draft_targets dt2 
                 JOIN tbl_master_indicators mi2 ON dt2.indicator_id = mi2.indicator_id 
                 WHERE dt2.emp_id = ep.emp_id AND mi2.term_id = %s AND dt2.proposed_quantity > 0),
                0
            ) AS target_count,
            CASE
                WHEN (SELECT COUNT(*) FROM tbl_committed_targets ct 
                      JOIN tbl_master_indicators mi2 ON ct.indicator_id = mi2.indicator_id 
                      WHERE ct.emp_id = ep.emp_id AND mi2.term_id = %s AND ct.assigned_quantity > 0) > 0
                THEN 'Locked'
                ELSE 'Approved'
            END AS review_status,
            cr.review_id,
            cr.overall_remarks,
            cr.reviewed_at
        FROM tbl_employee_profiles ep
        LEFT JOIN tbl_ipcr_chair_review cr
            ON cr.emp_id = ep.emp_id AND cr.term_id = %s
        WHERE (ep.specialization = %s OR ep.assigned_program = %s)
          AND ep.designation = 'Regular Faculty'
          AND cr.overall_status = 'Approved'
        GROUP BY ep.emp_id, ep.first_name, ep.last_name,
                 ep.academic_rank, ep.specialization,
                 cr.review_id, cr.overall_remarks, cr.reviewed_at
        ORDER BY ep.last_name, ep.first_name
    """
    from app.models.connection import timed_query
    return timed_query(cursor, query, (term_id, term_id, term_id, term_id, specialization, specialization), label="get_locked_faculty_ipcrs")


def get_or_create_chair_review(conn, cursor, emp_id, term_id, chair_emp_id):
    """
    Fetches an existing review record for emp_id + term_id, or creates one
    and pre-populates tbl_ipcr_chair_review_items by copying from tbl_draft_targets.
    Returns the review_id.
    """
    # Check for existing review
    cursor.execute(
        "SELECT review_id FROM tbl_ipcr_chair_review WHERE emp_id = %s AND term_id = %s",
        (emp_id, term_id)
    )
    existing = cursor.fetchone()
    if existing:
        review_id = existing[0]
        # Sync: Insert any draft targets that are missing from review items
        cursor.execute(
            """
            INSERT INTO tbl_ipcr_chair_review_items
                (review_id, draft_id, indicator_id, original_quantity, reviewed_quantity)
            SELECT %s, dt.draft_id, dt.indicator_id, dt.proposed_quantity, dt.proposed_quantity
            FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            LEFT JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = %s AND ri.draft_id = dt.draft_id
            WHERE dt.emp_id = %s AND mi.term_id = %s AND dt.review_status IN ('Pending Review', 'Waiting for Approval', 'Approved') AND ri.item_id IS NULL
            """,
            (review_id, review_id, emp_id, term_id)
        )
        # Sync RET target quantities to match the finalized RET-approved quantities
        cursor.execute(
            """
            UPDATE tbl_ipcr_chair_review_items ri
            JOIN tbl_draft_targets dt ON ri.draft_id = dt.draft_id
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            SET ri.original_quantity = dt.proposed_quantity,
                ri.reviewed_quantity = dt.proposed_quantity
            WHERE ri.review_id = %s
              AND tc.review_lane = 'RET'
            """,
            (review_id,)
        )
        conn.commit()
        return review_id

    # Create the review header
    cursor.execute(
        """
        INSERT INTO tbl_ipcr_chair_review (emp_id, term_id, chair_emp_id, overall_status)
        VALUES (%s, %s, %s, 'Pending')
        """,
        (emp_id, term_id, chair_emp_id)
    )
    review_id = cursor.lastrowid

    # Pre-populate items from tbl_draft_targets
    cursor.execute(
        """
        SELECT dt.draft_id, dt.indicator_id, dt.proposed_quantity
        FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        WHERE dt.emp_id = %s AND mi.term_id = %s AND dt.review_status IN ('Pending Review', 'Waiting for Approval', 'Approved')
        """,
        (emp_id, term_id)
    )
    draft_rows = cursor.fetchall()

    for draft_id, indicator_id, proposed_qty in draft_rows:
        cursor.execute(
            """
            INSERT INTO tbl_ipcr_chair_review_items
                (review_id, draft_id, indicator_id, original_quantity, reviewed_quantity)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (review_id, draft_id, indicator_id, proposed_qty, proposed_qty)
        )

    conn.commit()
    return review_id


def get_review_items(cursor, review_id):
    """
    Returns all items for a given review_id, joined with indicator descriptions,
    category names, and draft review statuses.
    """
    query = """
        SELECT
            ri.item_id,
            ri.draft_id,
            ri.indicator_id,
            ri.original_quantity,
            ri.reviewed_quantity,
            ri.item_remarks,
            COALESCE(dt.target_description, mi.indicator_description) AS indicator_description,
            mi.indicator_description AS indicator_template,
            dt.target_deadline,
            dt.target_duration_value,
            dt.target_duration_unit,
            dt.is_auto_description,
            tc.category_name,
            dt.review_status AS draft_status
        FROM tbl_ipcr_chair_review_items ri
        JOIN tbl_master_indicators mi ON ri.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        JOIN tbl_draft_targets dt ON ri.draft_id = dt.draft_id
        WHERE ri.review_id = %s
          AND (
              tc.review_lane <> 'RET'
              OR (tc.review_lane = 'RET' AND dt.proposed_quantity > 0)
          )
        ORDER BY tc.category_name, mi.indicator_id
    """
    cursor.execute(query, (review_id,))
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def update_review_item(conn, cursor, item_id, reviewed_quantity, item_remarks):
    """
    Updates a single review item's reviewed quantity and optional remark.
    The original tbl_draft_targets row is never modified.
    """
    try:
        cursor.execute(
            """
            UPDATE tbl_ipcr_chair_review_items
            SET reviewed_quantity = %s, item_remarks = %s
            WHERE item_id = %s
            """,
            (reviewed_quantity, item_remarks if item_remarks else None, item_id)
        )
        conn.commit()
        return True, "Change saved."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def save_chair_review_items(cursor, conn, review_id, items):
    """
    Batch save all Program Chair review item changes (quantities + remarks).
    """
    try:
        for item in items:
            item_id = item.get('item_id')
            reviewed_qty = item.get('reviewed_quantity', 0)
            item_remarks = item.get('item_remarks', '')

            cursor.execute(
                """
                UPDATE tbl_ipcr_chair_review_items
                SET reviewed_quantity = %s, item_remarks = %s
                WHERE item_id = %s
                """,
                (reviewed_qty, item_remarks if item_remarks else None, item_id)
            )
        conn.commit()
        return True, "Review items saved successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def decide_chair_review(conn, cursor, review_id, action, overall_remarks):
    """
    Sets overall_status to 'Approved' or 'Rejected' on the review header.
    If rejected, flips the related tbl_draft_targets rows back to 'Returned'
    so the faculty member can see the returned status and re-submit.
    """
    try:
        new_status = 'Approved' if action == 'approve' else 'Rejected'

        cursor.execute(
            """
            UPDATE tbl_ipcr_chair_review
            SET overall_status = %s,
                overall_remarks = %s,
                reviewed_at = %s
            WHERE review_id = %s
            """,
            (new_status, overall_remarks, datetime.now(), review_id)
        )

        # Get the emp_id and term_id for this review
        cursor.execute(
            "SELECT emp_id, term_id FROM tbl_ipcr_chair_review WHERE review_id = %s",
            (review_id,)
        )
        row = cursor.fetchone()
        if row:
            emp_id, term_id = row
            if action == 'reject':
                cursor.execute(
                    """
                    UPDATE tbl_draft_targets dt
                    JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                    JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                    SET dt.review_status = 'Returned'
                    WHERE dt.emp_id = %s
                      AND mi.term_id = %s
                      AND tc.review_lane = 'CHAIR' AND tc.is_core = 1
                    """,
                    (emp_id, term_id)
                )
            elif action == 'approve':
                cursor.execute(
                    """
                    UPDATE tbl_draft_targets dt
                    JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                    JOIN tbl_ipcr_chair_review cr ON dt.emp_id = cr.emp_id AND cr.term_id = mi.term_id
                    JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
                    SET dt.proposed_quantity = ri.reviewed_quantity
                    WHERE dt.emp_id = %s AND mi.term_id = %s
                    """,
                    (emp_id, term_id)
                )

        conn.commit()
        msg = "IPCR successfully approved." if action == 'approve' else "IPCR successfully returned to faculty."
        return True, msg
    except Exception as e:
        conn.rollback()
        return False, str(e)


def lock_and_commit_ipcr(conn, cursor, emp_id, term_id):
    try:
        cursor.execute(
            "SELECT overall_status FROM tbl_ipcr_chair_review WHERE emp_id = %s AND term_id = %s",
            (emp_id, term_id)
        )
        review_row = cursor.fetchone()
        if not review_row or review_row[0] != 'Approved':
            return False, "Your IPCR must be approved by the Program Chair before locking."

        cursor.execute(
            """
            SELECT dt.indicator_id, COALESCE(ri.reviewed_quantity, dt.proposed_quantity), dt.target_description, dt.target_deadline,
                   dt.target_duration_value, dt.target_duration_unit, dt.is_auto_description
            FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            LEFT JOIN tbl_ipcr_chair_review cr ON cr.emp_id = dt.emp_id AND cr.term_id = mi.term_id
            LEFT JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
            WHERE dt.emp_id = %s AND mi.term_id = %s
            """,
            (emp_id, term_id)
        )
        drafts = cursor.fetchall()

        if not drafts:
            return False, "No draft targets found to commit."

        cursor.execute(
            """
            DELETE ct FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
            """,
            (emp_id, term_id)
        )

        for indicator_id, qty, target_desc, target_dead, dur_value, dur_unit, is_auto_description in drafts:
            if qty > 0:
                cursor.execute(
                    """
                    INSERT INTO tbl_committed_targets (emp_id, indicator_id, assigned_quantity, status, target_description, target_deadline,
                                                       target_duration_value, target_duration_unit, is_auto_description)
                    VALUES (%s, %s, %s, 'Approved', %s, %s, %s, %s, %s)
                    """,
                    (emp_id, indicator_id, qty, target_desc, target_dead, dur_value, dur_unit, is_auto_description)
                )

        cursor.execute(
            """
            UPDATE tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            SET dt.review_status = 'Approved'
            WHERE dt.emp_id = %s AND mi.term_id = %s
            """,
            (emp_id, term_id)
        )

        conn.commit()
        return True, "IPCR successfully locked and committed to evaluation targets."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def get_program_chair_evidence_faculty(cursor, specialization, term_id):
    from app.models.connection import timed_query
    from app.models.faculty import enrich_faculty_verification_status
    query = """
        SELECT ep.emp_id, ep.first_name, ep.last_name, ep.academic_rank, ep.specialization, ep.designation, sa.system_role,
               COUNT(DISTINCT ct.target_id) as total_targets,
               SUM(CASE WHEN ct.actual_quantity >= ct.assigned_quantity AND ct.assigned_quantity > 0 THEN 1 ELSE 0 END) as met_targets,
               MAX(CASE WHEN ct.status IN ('Submitted', 'Pending Verification', 'Verified', 'Submitted to Dean', 'Dean Approved') THEN 1 ELSE 0 END) as has_submitted
        FROM tbl_employee_profiles ep
        JOIN tbl_committed_targets ct ON ep.emp_id = ct.emp_id
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        LEFT JOIN tbl_system_access sa ON ep.emp_id = sa.emp_id
        -- Designated Faculty (plain or chair/Dean) evidence is reviewed by the Dean, not the
        -- Program Chair. Specialization alone isn't enough to scope this to Regular Faculty --
        -- designated faculty belong to a specialization too -- so their designations are
        -- explicitly excluded.
        WHERE ep.specialization = %s
          AND mi.term_id = %s
          AND (ep.designation IS NULL OR ep.designation = ''
               OR ep.designation NOT IN ('Designated Faculty', 'Program Chair', 'RET Chair', 'Dean'))
        GROUP BY ep.emp_id, ep.first_name, ep.last_name, ep.academic_rank, ep.specialization, ep.designation, sa.system_role
        HAVING MAX(CASE WHEN ct.status IN ('Submitted', 'Pending Verification', 'Verified', 'Submitted to Dean', 'Dean Approved') THEN 1 ELSE 0 END) = 1
        ORDER BY ep.last_name, ep.first_name
    """
    rows = timed_query(cursor, query, (specialization, term_id), label="get_program_chair_evidence_faculty")
    for r in rows:
        enrich_faculty_verification_status(cursor, r, term_id)
    return rows


def get_department_accomplishment_summary(cursor, specialization, term_id):
    """
    Department-wide progress on the indicators the Dean cascaded to this Program Chair's own
    specialization -- the same cascade rows that become the chair's own Departmental Oversight
    targets on their personal IPCR (see get_oversight_targets, app/models/designated.py). Quota
    vs. how much of it has actually cleared verification so far, summed across every member of
    the department who holds that indicator as their own personal committed target
    (is_admin_function = 0; a chair's own oversight copy of the same indicator is excluded,
    same as it is everywhere else this scoping is used).

    "Every member" deliberately includes the department's designated faculty -- the chair
    themselves, the RET Chair, the Dean and any plain Designated Faculty member -- because
    get_specialization_faculty allocates to them and this dashboard's own quota figure
    (assigned_per_faculty * all_faculty_count, routes/prog_chair.py) counts them. Excluding
    them here, as the review-routing queries do for their own separate reason, left this card
    reporting a fraction of a quota it had already handed out. Membership and specialization
    scoping are kept identical to get_oversight_evidence (app/models/designated.py) on
    purpose: this card and the chair's own Departmental Oversight row must never disagree
    about the same number. Scoping is specialization-only -- assigned_program holds the
    degree program ('BSIT'), never a department, so it is not a cascade target and must not
    widen this scope, whatever get_specialization_faculty does for allocation.

    "Verified Accomplished" is deliberately Approved-only, not the looser "not Rejected/
    Returned" convention a target's own actual_quantity uses for scoring (see
    recalculate_target_accomplished_quantity) -- this is a monitoring figure for the chair, not
    a score input, and the point is "how much is actually locked in," not "how much has been
    reported but might still come back." The quota/verified numbers are independent of whether
    the chair has locked their own IPCR for the term yet -- reads live off the cascade + faculty
    evidence directly; only the displayed description's duration clause depends on it (blank
    until the chair has submitted their own oversight row and its real deadline exists).
    """
    from app.models.connection import timed_query

    query = """
        SELECT cq.indicator_id, cq.total_target_value, mi.indicator_description,
               COALESCE(agg.verified_accomplished, 0) as verified_accomplished,
               COALESCE(chair_ct.target_duration_value, chair_dt.target_duration_value) as chair_duration_value,
               COALESCE(chair_ct.target_duration_unit, chair_dt.target_duration_unit) as chair_duration_unit
        FROM tbl_cascaded_quotas cq
        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
        LEFT JOIN (
            SELECT ct.indicator_id, SUM(er.actual_qty_Q) as verified_accomplished
            FROM tbl_committed_targets ct
            JOIN tbl_employee_profiles ep ON ct.emp_id = ep.emp_id
            JOIN tbl_evidence_repo er ON er.target_id = ct.target_id AND er.verification_status = 'Approved'
            WHERE ct.is_admin_function = 0
              AND ep.specialization = %s
            GROUP BY ct.indicator_id
        ) agg ON agg.indicator_id = cq.indicator_id
        -- The chair's own Departmental Oversight row for this same indicator (get_oversight_
        -- targets) already carries their real deadline input, once they've submitted their own
        -- IPCR -- pulled in purely for display, so this summary's description reads like a
        -- normal target sentence instead of a blank "____" placeholder before that happens.
        -- Committed wins over draft (locked/final beats a still-editable draft value).
        LEFT JOIN tbl_committed_targets chair_ct
               ON chair_ct.indicator_id = cq.indicator_id AND chair_ct.is_admin_function = 1
              AND EXISTS (
                  SELECT 1 FROM tbl_employee_profiles cep
                  WHERE cep.emp_id = chair_ct.emp_id AND cep.specialization = %s AND cep.designation = 'Program Chair'
              )
        LEFT JOIN tbl_draft_targets chair_dt
               ON chair_dt.indicator_id = cq.indicator_id AND chair_dt.is_admin_function = 1
              AND EXISTS (
                  SELECT 1 FROM tbl_employee_profiles dep
                  WHERE dep.emp_id = chair_dt.emp_id AND dep.specialization = %s AND dep.designation = 'Program Chair'
              )
        WHERE mi.term_id = %s
          AND cq.assigned_to_role = %s AND cq.total_target_value > 0
        ORDER BY mi.indicator_id
    """
    rows = timed_query(cursor, query,
                       (specialization, specialization, specialization, term_id, specialization),
                       label="get_department_accomplishment_summary")

    from app.models.ipcr_description import format_ipcr_target_description
    for r in rows:
        # Real duration once the chair has submitted their own oversight row this term;
        # format_ipcr_target_description's own blank-placeholder fallback only shows before
        # that (or if this Program Chair record is somehow missing), which is the accurate
        # "not yet set" state, not a display bug.
        r['target_description'] = format_ipcr_target_description(
            r['indicator_description'], r['total_target_value'],
            r.get('chair_duration_value'), r.get('chair_duration_unit'))
        quota = r['total_target_value'] or 0
        r['percent_verified'] = round(min(r['verified_accomplished'], quota) / quota * 100) if quota > 0 else 0
    return rows


def submit_evidence_package_to_dean(conn, cursor, emp_id, term_id):
    """
    Submits a fully approved evidence package for a faculty member to the Dean for final verification.

    Re-checks readiness server-side rather than trusting the caller -- the "Submit to Dean"
    button is only shown once is_both_approved reads true, but a stale page (or a second
    request racing an in-progress review) must not be able to forward a package that still
    has uploaded evidence sitting unapproved. A target with no evidence at all is not blocked
    -- an incomplete faculty submission is expected and fine; only evidence that was actually
    uploaded has to be reviewed before the package can move on.
    """
    from app.models.faculty import enrich_faculty_verification_status
    status = enrich_faculty_verification_status(cursor, {'emp_id': emp_id}, term_id)
    if not status.get('is_both_approved'):
        return False, "Not all evidence has been approved yet. Finish verifying every target before submitting to the Dean."
    try:
        query = """
            UPDATE tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            SET ct.status = 'Submitted to Dean'
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """
        cursor.execute(query, (emp_id, term_id))
        conn.commit()
        return True, "Evidence submission package successfully forwarded to the Dean for final verification."
    except Exception as e:
        conn.rollback()
        return False, str(e)

