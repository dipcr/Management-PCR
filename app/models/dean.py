def get_existing_cascaded_quotas(cursor, term_id):
    from app.models.connection import timed_query
    query = """
        SELECT cq.*, mi.indicator_description, tc.category_name
        FROM tbl_cascaded_quotas cq
        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE cq.term_id = %s
        ORDER BY mi.indicator_id
    """
    return timed_query(cursor, query, (term_id,), label="get_existing_cascaded_quotas")


def get_dean_dashboard_kpis(cursor, term_id):
    """
    Consolidated KPI query — replaces 3 separate round-trips
    (get_overall_completion + get_pending_approvals_count + get_top_performing_department)
    into a single query.
    """
    query = """
        SELECT
            COALESCE(
                ROUND(
                    (SUM(CASE WHEN ts.status = 'Approved' THEN 1 ELSE 0 END) 
                     / NULLIF(COUNT(*), 0)) * 100
                ), 0
            ) AS completion_rate,
            (SELECT COUNT(*) FROM tbl_final_scores fs2
             WHERE fs2.term_id = %s AND fs2.dean_approval_status = 'Pending') AS pending_count,
            COALESCE(
                (SELECT ep2.assigned_program
                 FROM tbl_final_scores fs3
                 JOIN tbl_employee_profiles ep2 ON fs3.emp_id = ep2.emp_id
                 WHERE fs3.term_id = %s AND fs3.dean_approval_status = 'Approved'
                 GROUP BY ep2.assigned_program
                 ORDER BY AVG(fs3.final_score) DESC
                 LIMIT 1),
                'N/A'
            ) AS top_dept
        FROM tbl_committed_targets ts
        JOIN tbl_master_indicators mi ON ts.indicator_id = mi.indicator_id
        WHERE mi.term_id = %s
    """
    from app.models.connection import timed_query
    result = timed_query(cursor, query, (term_id, term_id, term_id), label="dean_dashboard_kpis")
    if result:
        return result[0]['completion_rate'], result[0]['pending_count'], result[0]['top_dept']
    return 0, 0, "N/A"


def get_pending_final_approvals(cursor, term_id):
    from app.models.connection import timed_query
    query = """
        SELECT 
            fs.score_id,
            ep.emp_id,
            CONCAT(ep.first_name, ' ', ep.last_name) as faculty_name,
            ep.assigned_program as department,
            fs.final_score,
            fs.adjectival_rating,
            fs.dean_approval_status
        FROM tbl_final_scores fs
        JOIN tbl_employee_profiles ep ON fs.emp_id = ep.emp_id
        WHERE fs.term_id = %s AND fs.dean_approval_status = 'Pending'
        ORDER BY ep.last_name ASC
    """
    return timed_query(cursor, query, (term_id,), label="get_pending_final_approvals")


def save_cascaded_quotas(cursor, connection, term_id, quotas_data):
    try:
        cursor.execute("DELETE FROM tbl_cascaded_quotas WHERE term_id = %s", (term_id,))

        for quota in quotas_data:
            cursor.execute("""
                INSERT INTO tbl_cascaded_quotas (term_id, indicator_id, total_target_value, assigned_to_role, allow_chair_allocation)
                VALUES (%s, %s, %s, %s, %s)
            """, (term_id, quota['indicator_id'], quota['total_target'], quota['assigned_role'], quota['allow_chair_allocation']))

        connection.commit()
        return True, "Quotas cascaded successfully!"
    except Exception as e:
        connection.rollback()
        return False, f"Error saving quotas: {str(e)}"


def update_dean_approval_status(cursor, connection, score_ids, new_status):
    try:
        placeholders = ','.join(['%s'] * len(score_ids))
        cursor.execute(f"""
            UPDATE tbl_final_scores 
            SET dean_approval_status = %s 
            WHERE score_id IN ({placeholders})
        """, [new_status] + score_ids)
        connection.commit()
        return True, f"Successfully updated {cursor.rowcount} IPCR(s)"
    except Exception as e:
        connection.rollback()
        return False, f"Error updating approvals: {str(e)}"


# ──────────────────────────────────────────────
# Draft IPCR Review (Designated Faculty) — Program Chair UX style
# Requires tables:
#   tbl_ipcr_dean_review(review_id, emp_id, term_id, dean_id, overall_status, overall_remarks, reviewed_at)
#   tbl_ipcr_dean_review_items(item_id, review_id, draft_id, indicator_id, original_quantity, reviewed_quantity, item_remarks)
# ──────────────────────────────────────────────

def get_designated_draft_submissions(cursor, term_id):
    """
    Get all designated faculty who have submitted draft IPCRs,
    grouped by faculty with summary info.
    """
    from app.models.connection import timed_query
    query = """
        SELECT 
            dt.emp_id,
            CONCAT(ep.first_name, ' ', ep.last_name) AS faculty_name,
            ep.academic_rank,
            ep.assigned_program,
            ep.designation,
            COUNT(DISTINCT dt.draft_id) AS total_targets,
            COALESCE(MAX(dr.overall_status), 'Pending') AS review_status
        FROM tbl_draft_targets dt
        JOIN tbl_employee_profiles ep ON dt.emp_id = ep.emp_id
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        JOIN tbl_system_access sa ON dt.emp_id = sa.emp_id
        LEFT JOIN tbl_ipcr_dean_review dr ON dr.emp_id = dt.emp_id AND dr.term_id = %s
        WHERE mi.term_id = %s
          AND (sa.system_role IN ('PROGRAM_CHAIR', 'RET_CHAIR', 'DESIGNATED_FACULTY', 'DEAN')
               OR (ep.designation IS NOT NULL AND ep.designation <> ''
                    AND ep.designation NOT IN ('Regular Faculty', 'Admin')))
          AND mi.is_custom IN (0, 1)
        GROUP BY dt.emp_id, ep.first_name, ep.last_name, ep.academic_rank, ep.assigned_program, ep.designation, dr.overall_status
        ORDER BY ep.last_name ASC
    """
    return timed_query(cursor, query, (term_id, term_id), label="get_designated_draft_submissions")


def get_or_create_dean_review(conn, cursor, emp_id, term_id, dean_id):
    """
    Fetches existing tbl_ipcr_dean_review for emp_id+term_id, or creates one
    and pre-populates items from tbl_draft_targets + all master indicators.
    Returns review_id.
    """
    cursor.execute(
        "SELECT review_id FROM tbl_ipcr_dean_review WHERE emp_id = %s AND term_id = %s",
        (emp_id, term_id)
    )
    existing = cursor.fetchone()
    if existing:
        review_id = existing[0]
        # Sync: add any new draft targets that aren't in review items yet.
        # Scoped to the review's own term — an employee's drafts from earlier terms are
        # still on file and would otherwise be pulled into this review.
        cursor.execute("""
            INSERT IGNORE INTO tbl_ipcr_dean_review_items
                (review_id, draft_id, indicator_id, original_quantity, reviewed_quantity)
            SELECT %s, dt.draft_id, dt.indicator_id, dt.proposed_quantity, dt.proposed_quantity
            FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            WHERE dt.emp_id = %s
              AND mi.term_id = %s
              AND dt.draft_id NOT IN (
                  SELECT COALESCE(draft_id, 0) FROM tbl_ipcr_dean_review_items WHERE review_id = %s
              )
        """, (review_id, emp_id, term_id, review_id))
        conn.commit()
        return review_id

    # Create new review
    cursor.execute("""
        INSERT INTO tbl_ipcr_dean_review (emp_id, term_id, dean_id, overall_status)
        VALUES (%s, %s, %s, 'Pending')
    """, (emp_id, term_id, dean_id))
    review_id = cursor.lastrowid

    # Pre-populate review items from this term's draft targets only.
    cursor.execute("""
        INSERT INTO tbl_ipcr_dean_review_items
            (review_id, draft_id, indicator_id, original_quantity, reviewed_quantity)
        SELECT %s, dt.draft_id, dt.indicator_id, dt.proposed_quantity, dt.proposed_quantity
        FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        WHERE dt.emp_id = %s
          AND mi.term_id = %s
    """, (review_id, emp_id, term_id))
    conn.commit()
    return review_id


def get_dean_review_items(cursor, review_id):
    """Get all review items with indicator + category details, target description, deadline, and core flags."""
    from app.models.connection import timed_query
    from app.models.ipcr_description import format_ipcr_target_description
    query = """
        SELECT
            dri.item_id,
            dri.draft_id,
            dri.indicator_id,
            dri.original_quantity,
            dri.reviewed_quantity,
            dri.item_remarks,
            mi.indicator_description,
            tc.category_name,
            mi.efficiency_type,
            mi.is_custom,
            COALESCE(dt.target_description, da.custom_description, mi.indicator_description) as target_description,
            COALESCE(dt.target_deadline, da.target_deadline) as target_deadline,
            dt.target_duration_value,
            dt.target_duration_unit,
            dt.is_admin_function,
            dt.is_auto_description,
            CASE WHEN da.allocation_id IS NOT NULL THEN 1 ELSE 0 END as is_cascaded
        FROM tbl_ipcr_dean_review_items dri
        JOIN tbl_ipcr_dean_review dr ON dri.review_id = dr.review_id
        JOIN tbl_master_indicators mi ON dri.indicator_id = mi.indicator_id
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        LEFT JOIN tbl_draft_targets dt ON dri.draft_id = dt.draft_id
        LEFT JOIN tbl_draft_allocation da ON da.emp_id = dr.emp_id AND da.indicator_id = dri.indicator_id
        WHERE dri.review_id = %s
        ORDER BY tc.category_name, mi.indicator_id
    """
    items = timed_query(cursor, query, (review_id,), label="get_dean_review_items")
    from app.models.scoring import format_duration
    for item in items:
        if item.get('category_name') == 'Custom Target Items':
            item['category_name'] = 'Support Functions'
        if not item.get('target_deadline'):
            # A hardcoded '1 Semester' default here would silently mask a real data gap
            # (e.g. a row whose duration never got saved) behind a plausible-looking value.
            # Derive from the structured duration columns when present; '1 Semester' is only
            # the true last resort, when there's no duration data to derive from at all.
            item['target_deadline'] = (
                format_duration(item.get('target_duration_value'), item.get('target_duration_unit'))
                or '1 Semester'
            )
        is_admin_function = bool(item.get('is_admin_function'))
        is_tl = 'Teaching Load' in (item.get('indicator_description') or '')
        # da.allocation_id matches on emp_id + indicator_id alone, so a chair's Departmental
        # Oversight item (is_admin_function=1) for an indicator they also personally hold —
        # e.g. Instruction 1, both a personal Core Function share and the WST-wide oversight
        # quota — would otherwise be flagged as cascaded/Core too, same as the real personal
        # row. Only the non-oversight row can be Core Function.
        is_cascaded = bool(item.get('is_cascaded')) and not is_admin_function
        item['is_core'] = (not is_admin_function) and (is_tl or is_cascaded)
        item['is_cascaded'] = is_cascaded
        item['is_admin_function'] = is_admin_function
        # None (a plain cascaded/Core row with no is_auto_description of its own) and 1 both
        # mean "still auto-mirroring" — only an explicit 0 means the Dean customized it.
        item['is_auto_description'] = item.get('is_auto_description') is None or item.get('is_auto_description') == 1
        # A custom ad-hoc item's indicator_description IS its user-typed text — it has no
        # master indicator to mirror, so it must never be regenerated regardless of what its
        # is_auto_description flag says. (Historically that flag defaulted to 1/auto for
        # custom rows since the insert never set it explicitly — see submit_designated_ipcr.)
        if item['is_auto_description'] and not item.get('is_custom'):
            # Never trust the stored target_description for an auto row — regenerate from the
            # indicator and the item's own committed quantity/duration every time this is read.
            # Without this, a row saved before this substitution logic existed (or before a
            # since-changed Dean quota) keeps showing stale text indefinitely; a departmental
            # oversight row in particular has no description input of its own at all, so its
            # stored value can only ever be regenerated, never legitimately customized.
            item['target_description'] = format_ipcr_target_description(
                item['indicator_description'], item.get('original_quantity'),
                item.get('target_duration_value'), item.get('target_duration_unit'))
    return items



def get_available_master_indicators(cursor, term_id, emp_id=None):
    """Get selectable indicators relevant to the reviewee: Research and Extension for RET Chair; Instructions and Support for others."""
    from app.models.connection import timed_query
    
    is_ret = False
    if emp_id:
        cursor.execute("""
            SELECT ep.designation, sa.system_role
            FROM tbl_employee_profiles ep
            LEFT JOIN tbl_system_access sa ON ep.emp_id = sa.emp_id
            WHERE ep.emp_id = %s
        """, (emp_id,))
        row = cursor.fetchone()
        if row:
            desig, srole = (row[0] or '').strip(), (row[1] or '').strip()
            if desig == 'RET Chair' or srole == 'RET_CHAIR':
                is_ret = True

    if is_ret:
        query = """
            SELECT mi.indicator_id, mi.indicator_description, tc.category_name, mi.efficiency_type, mi.is_custom
            FROM tbl_master_indicators mi
            LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            WHERE mi.term_id = %s
              AND (tc.review_lane = 'RET' OR (mi.is_custom = 1 AND (tc.category_name LIKE '%%Research%%' OR tc.category_name LIKE '%%Extension%%')))
            ORDER BY tc.category_name, mi.indicator_id
        """
    else:
        query = """
            SELECT mi.indicator_id, mi.indicator_description, tc.category_name, mi.efficiency_type, mi.is_custom
            FROM tbl_master_indicators mi
            LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            WHERE mi.term_id = %s
              AND (mi.is_custom = 1 OR (tc.review_lane = 'CHAIR' AND tc.is_core = 1))
            ORDER BY tc.category_name, mi.indicator_id
        """
    return timed_query(cursor, query, (term_id,), label="get_available_master_indicators")


def save_dean_review_items(cursor, conn, review_id, items):
    """
    Batch save all review item changes (quantities + remarks).
    Items: [{'item_id': int, 'reviewed_quantity': int, 'item_remarks': str}, ...]
    For new items (is_new=True, no item_id), creates draft target + review item, using
    target_description/target_duration_value/target_duration_unit from the item dict when
    provided.
    Also syncs changes back to tbl_draft_targets so faculty see the update.
    Removes any items that were deleted from the review.
    """
    try:
        # Collect existing item_ids that are retained
        retained_item_ids = [item['item_id'] for item in items if item.get('item_id')]

        # Delete removed items from tbl_draft_targets and tbl_ipcr_dean_review_items
        if retained_item_ids:
            placeholders = ','.join(['%s'] * len(retained_item_ids))
            cursor.execute(f"""
                DELETE dt FROM tbl_draft_targets dt
                JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
                WHERE dri.review_id = %s AND dri.item_id NOT IN ({placeholders})
            """, [review_id] + retained_item_ids)

            cursor.execute(f"""
                DELETE FROM tbl_ipcr_dean_review_items
                WHERE review_id = %s AND item_id NOT IN ({placeholders})
            """, [review_id] + retained_item_ids)
        elif not items:
            cursor.execute("""
                DELETE dt FROM tbl_draft_targets dt
                JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
                WHERE dri.review_id = %s
            """, (review_id,))
            cursor.execute("DELETE FROM tbl_ipcr_dean_review_items WHERE review_id = %s", (review_id,))

        for item in items:
            reviewed_qty = item.get('reviewed_quantity', 0)
            item_remarks = item.get('item_remarks', '')

            if item.get('is_new') and not item.get('item_id'):
                # New item from unpicked indicators — insert draft target + review item
                indicator_id = item.get('indicator_id')
                if not indicator_id:
                    continue
                # Get emp_id from review
                cursor.execute(
                    "SELECT emp_id, term_id FROM tbl_ipcr_dean_review WHERE review_id = %s",
                    (review_id,)
                )
                r = cursor.fetchone()
                if not r:
                    continue
                emp_id, term_id = r
                # Duration comes from the Dean's quick-add input; falls back to 1 semester
                # if omitted — without it the target has no deadline at all, which
                # Timeliness scoring needs.
                from app.models.scoring import format_duration
                from app.models.ipcr_description import format_ipcr_target_description, get_indicator_description
                dur_value = item.get('target_duration_value') or 1
                dur_unit = item.get('target_duration_unit') or 'semesters'
                desc = item.get('target_description') or None
                # is_auto_description True (explicit, from the frontend) always regenerates,
                # even if non-blank text was submitted — protects against client-side drift
                # (Decision 1). A blank description always regenerates too, regardless.
                is_auto_description = 1 if (item.get('is_auto_description') is True or not desc) else 0
                if is_auto_description:
                    desc = format_ipcr_target_description(
                        get_indicator_description(cursor, indicator_id), reviewed_qty, dur_value, dur_unit)
                # Always Dean-added/oversight-originated -- never the designated faculty's
                # own personal teaching allocation -- so this rolls into Strategic
                # Priorities/Support like every other oversight row (get_oversight_targets,
                # submit_designated_ipcr), not Core Functions.
                cursor.execute("""
                    INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                                   target_description, target_duration_value, target_duration_unit,
                                                   target_deadline, is_admin_function, is_auto_description)
                    VALUES (%s, %s, %s, 'Pending Review', %s, %s, %s, %s, 1, %s)
                """, (emp_id, indicator_id, reviewed_qty, desc, dur_value, dur_unit,
                      format_duration(dur_value, dur_unit), is_auto_description))
                new_draft_id = cursor.lastrowid
                # Insert review item linked to new draft
                cursor.execute("""
                    INSERT INTO tbl_ipcr_dean_review_items
                        (review_id, draft_id, indicator_id, original_quantity, reviewed_quantity, item_remarks)
                    VALUES (%s, %s, %s, -1, %s, %s)
                """, (review_id, new_draft_id, indicator_id, reviewed_qty, item_remarks))
            else:
                # Existing item — update quantities and remarks
                item_id = item.get('item_id')
                if not item_id:
                    continue
                cursor.execute("""
                    UPDATE tbl_ipcr_dean_review_items
                    SET reviewed_quantity = %s, item_remarks = %s
                    WHERE item_id = %s
                """, (reviewed_qty, item_remarks, item_id))

                # Sync back to tbl_draft_targets so designated faculty sees the change
                cursor.execute("""
                    UPDATE tbl_draft_targets dt
                    JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
                    SET dt.proposed_quantity = %s
                    WHERE dri.item_id = %s
                """, (reviewed_qty, item_id))

                # A Dean-added item (original_quantity=-1) also exposes editable
                # description/duration inputs after its first save — apply any further
                # edit to those too, or it silently gets dropped on the next save.
                if item.get('target_duration_value') is not None or item.get('target_description') is not None:
                    from app.models.scoring import format_duration
                    from app.models.ipcr_description import format_ipcr_target_description
                    dur_value = item.get('target_duration_value') or 1
                    dur_unit = item.get('target_duration_unit') or 'semesters'
                    desc = item.get('target_description') or None
                    # is_auto_description True (explicit, from the frontend) always
                    # regenerates, even if non-blank text was submitted — protects against
                    # client-side drift (Decision 1). A blank description always regenerates
                    # too, regardless.
                    is_auto_description = 1 if (item.get('is_auto_description') is True or not desc) else 0
                    if is_auto_description:
                        cursor.execute("""
                            SELECT dri.indicator_id, mi.indicator_description
                            FROM tbl_ipcr_dean_review_items dri
                            JOIN tbl_master_indicators mi ON dri.indicator_id = mi.indicator_id
                            WHERE dri.item_id = %s
                        """, (item_id,))
                        ind_row = cursor.fetchone()
                        indicator_description = ind_row[1] if ind_row else ''
                        desc = format_ipcr_target_description(indicator_description, reviewed_qty, dur_value, dur_unit)
                    cursor.execute("""
                        UPDATE tbl_draft_targets dt
                        JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
                        SET dt.target_description = %s, dt.target_duration_value = %s,
                            dt.target_duration_unit = %s, dt.target_deadline = %s, dt.is_auto_description = %s
                        WHERE dri.item_id = %s
                    """, (desc, dur_value, dur_unit, format_duration(dur_value, dur_unit), is_auto_description, item_id))

        conn.commit()
        return True, "Review items saved successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def submit_dean_review_decision(cursor, conn, review_id, action, overall_remarks):
    """
    Finalize the Dean's review: approve or reject.
    Updates both tbl_ipcr_dean_review and tbl_draft_targets.
    """
    try:
        cursor.execute("""
            UPDATE tbl_ipcr_dean_review
            SET overall_status = %s, overall_remarks = %s, reviewed_at = NOW()
            WHERE review_id = %s
        """, (action, overall_remarks, review_id))

        # Update draft review status and sync proposed quantity to reviewed quantity
        cursor.execute("""
            UPDATE tbl_draft_targets dt
            JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
            JOIN tbl_ipcr_dean_review dr ON dri.review_id = dr.review_id
            SET dt.review_status = %s,
                dt.proposed_quantity = dri.reviewed_quantity
            WHERE dr.review_id = %s
        """, (action, review_id))

        conn.commit()
        return True, f"Draft IPCR {action.lower()} successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)


# ──────────────────────────────────────────────
# College-Wide Target Assignment (Designated Faculty) Mika
# ──────────────────────────────────────────────

def get_designated_faculty_list(cursor):
    """
    Every active designated faculty member.

    Keyed on designation, not system_role: a Program Chair, RET Chair or Dean is a designated
    faculty member with an IPCR of their own, but logs in under their own role. Filtering by
    system_role hid them from the Dean's assignment panel entirely.
    """
    from app.models.connection import timed_query
    from app.models.criteria import DESIGNATION_REGULAR, NON_FACULTY_DESIGNATIONS
    excluded = [DESIGNATION_REGULAR] + sorted(NON_FACULTY_DESIGNATIONS)
    placeholders = ','.join(['%s'] * len(excluded))
    query = f"""
        SELECT ep.emp_id, ep.first_name, ep.last_name, ep.academic_rank, ep.assigned_program, ep.specialization, ep.designation
        FROM tbl_employee_profiles ep
        WHERE ep.leave_status = 'Active'
          AND ep.designation IS NOT NULL AND ep.designation <> ''
          AND ep.designation NOT IN ({placeholders})
        ORDER BY ep.last_name ASC, ep.first_name ASC
    """
    return timed_query(cursor, query, tuple(excluded), label="get_designated_faculty_list")


def get_college_wide_cascaded_quotas(cursor, term_id):
    """
    Get indicators that have College-Wide quotas set in tbl_cascaded_quotas.
    """
    from app.models.connection import timed_query
    query = """
        SELECT cq.*, mi.indicator_description, tc.category_name, mi.efficiency_type
        FROM tbl_cascaded_quotas cq
        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE cq.term_id = %s AND cq.assigned_to_role = 'College-Wide' AND cq.total_target_value > 0
        ORDER BY tc.category_name, mi.indicator_id
    """
    return timed_query(cursor, query, (term_id,), label="get_college_wide_cascaded_quotas")


def get_designated_faculty_assignments(cursor, term_id, emp_id):
    """
    Get existing target assignments for a specific designated faculty member
    from tbl_draft_allocation.
    """
    from app.models.connection import timed_query
    query = """
        SELECT da.allocation_id, da.indicator_id, da.assigned_quantity,
               da.custom_description, da.target_deadline,
               da.target_duration_value, da.target_duration_unit, da.is_auto_description,
               mi.indicator_description, tc.category_name, tc.slug
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE mi.term_id = %s AND da.emp_id = %s
          AND da.indicator_id IN (
              SELECT indicator_id FROM tbl_cascaded_quotas
              WHERE term_id = %s AND assigned_to_role = 'College-Wide' AND total_target_value > 0
          )
        ORDER BY tc.category_name, mi.indicator_id
    """
    return timed_query(cursor, query, (term_id, emp_id, term_id), label="get_designated_faculty_assignments")


def get_designated_faculty_assignments_batch(cursor, term_id, emp_ids):
    """
    Get target assignments for MULTIPLE designated faculty members in ONE query.
    Returns a dict: {emp_id: {indicator_id: assignment_dict, ...}, ...}
    """
    if not emp_ids:
        return {}

    from app.models.connection import timed_query
    placeholders = ','.join(['%s'] * len(emp_ids))
    query = f"""
        SELECT da.emp_id, da.indicator_id, da.assigned_quantity,
               da.custom_description, da.target_deadline,
               da.target_duration_value, da.target_duration_unit,
               tc.slug
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE mi.term_id = %s AND da.emp_id IN ({placeholders})
          AND da.indicator_id IN (
              SELECT indicator_id FROM tbl_cascaded_quotas
              WHERE term_id = %s AND assigned_to_role = 'College-Wide' AND total_target_value > 0
          )
    """
    rows = timed_query(cursor, query, [term_id] + emp_ids + [term_id], label="get_designated_faculty_assignments_batch")

    result = {}
    for row in rows:
        emp_id = row['emp_id']
        if emp_id not in result:
            result[emp_id] = {}
        result[emp_id][row['indicator_id']] = row
    return result


def save_designated_faculty_assignments(conn, cursor, term_id, emp_id, assignments, assigned_by=None):
    """
    Replaces the Dean's College-Wide assignments for one designated faculty member / chair.
    Preserves any Program Chair instruction allocations in tbl_draft_allocation.

    `assignments` is a list of tuples:
    (indicator_id, assigned_quantity, custom_description, target_duration_value, target_duration_unit)
    """
    from app.models.scoring import format_duration
    from app.models.ipcr_description import format_ipcr_target_description
    try:
        # Get allowed College-Wide indicator IDs for this term
        cursor.execute("""
            SELECT cq.indicator_id, mi.indicator_description
            FROM tbl_cascaded_quotas cq
            JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
            WHERE cq.term_id = %s AND cq.assigned_to_role = 'College-Wide' AND cq.total_target_value > 0
        """, (term_id,))
        cw_rows = cursor.fetchall()
        allowed_cw_ids = {r[0] for r in cw_rows}
        cw_descriptions = {r[0]: r[1] for r in cw_rows}

        if allowed_cw_ids:
            cw_placeholders = ','.join(['%s'] * len(allowed_cw_ids))
            cursor.execute(f"""
                DELETE FROM tbl_draft_allocation
                WHERE emp_id = %s AND indicator_id IN ({cw_placeholders})
            """, [emp_id] + list(allowed_cw_ids))

        saved = 0
        skipped = 0
        for item in assignments:
            is_auto_flag = None
            if len(item) == 6:
                indicator_id, qty, desc, dur_val, dur_unit, is_auto_flag = item
            elif len(item) == 5:
                indicator_id, qty, desc, dur_val, dur_unit = item
            else:
                indicator_id, qty = item[0], item[1]
                desc, dur_val, dur_unit = None, None, None

            if indicator_id not in allowed_cw_ids:
                skipped += 1
                continue

            qty = qty if qty and int(qty) > 0 else 1
            deadline = format_duration(dur_val, dur_unit)

            # is_auto_flag True (explicit, from the frontend) always regenerates, even if
            # non-blank text was submitted — protects against client-side drift (Decision 1).
            # A blank description always regenerates too, regardless of the flag.
            is_auto_description = 1 if (is_auto_flag is True or not desc) else 0
            if is_auto_description:
                desc = format_ipcr_target_description(cw_descriptions.get(indicator_id, ''), qty, dur_val, dur_unit)

            cursor.execute("""
                INSERT INTO tbl_draft_allocation (emp_id, indicator_id, assigned_quantity,
                                                  custom_description, target_deadline,
                                                  target_duration_value, target_duration_unit, is_auto_description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (emp_id, indicator_id, int(qty), desc, deadline, dur_val, dur_unit, is_auto_description))
            saved += 1

        conn.commit()
        msg = f"Saved {saved} College-Wide target assignment(s)."
        if skipped:
            msg += f" {skipped} skipped (not in College-Wide quota pool)."
        return True, msg
    except Exception as e:
        conn.rollback()
        return False, f"Error saving assignments: {str(e)}"


def save_designated_faculty_assignment(cursor, conn, term_id, emp_id, indicator_id, quantity):
    """Save or update a single target assignment for a designated faculty member in tbl_draft_allocation."""
    try:
        # Check if an assignment already exists
        cursor.execute(
            "SELECT allocation_id FROM tbl_draft_allocation WHERE emp_id = %s AND indicator_id = %s",
            (emp_id, indicator_id)
        )
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                "UPDATE tbl_draft_allocation SET assigned_quantity = %s WHERE allocation_id = %s",
                (quantity, existing[0])
            )
        else:
            cursor.execute(
                "INSERT INTO tbl_draft_allocation (emp_id, indicator_id, assigned_quantity) VALUES (%s, %s, %s)",
                (emp_id, indicator_id, quantity)
            )
        conn.commit()
        return True, "Assignment saved successfully."
    except Exception as e:
        conn.rollback()
        return False, f"Error saving assignment: {str(e)}"


def get_college_wide_allocations_tracker(cursor, term_id):
    """
    Get actual target distributions (from tbl_draft_targets) for indicators
    that have a College-Wide quota set in tbl_cascaded_quotas.

    Includes Regular Faculty: a Program Chair can cascade a College-Wide Support indicator
    down to their own regular faculty (see get_chair_indicators), so their commitments count
    against the same quota as the Dean's direct Designated Faculty assignments.
    """
    from app.models.connection import timed_query
    query = """
        SELECT
            dt.indicator_id,
            dt.emp_id,
            CONCAT(ep.first_name, ' ', ep.last_name) AS faculty_name,
            ep.assigned_program,
            dt.proposed_quantity,
            dt.review_status
        FROM tbl_draft_targets dt
        JOIN tbl_employee_profiles ep ON dt.emp_id = ep.emp_id
        WHERE ep.designation IS NOT NULL AND ep.designation <> ''
          AND ep.designation NOT IN ('Admin')
          AND ep.leave_status = 'Active'
          AND dt.indicator_id IN (
              SELECT indicator_id 
              FROM tbl_cascaded_quotas 
              WHERE term_id = %s AND assigned_to_role = 'College-Wide' AND total_target_value > 0
          )
        ORDER BY ep.last_name, ep.first_name
    """
    return timed_query(cursor, query, (term_id,), label="get_college_wide_allocations_tracker")


def get_dean_evidence_faculty(cursor, term_id):
    """
    Returns faculty members submitted to the Dean for final evidence verification,
    categorized into pending_evidence_faculty_list and approved_evidence_faculty_list.
    """
    from app.models.connection import timed_query
    from app.models.faculty import enrich_faculty_verification_status

    query = """
        SELECT ep.emp_id, ep.first_name, ep.last_name, ep.academic_rank, ep.specialization, ep.assigned_program, ep.designation, sa.system_role,
               COUNT(DISTINCT ct.target_id) as total_targets,
               SUM(CASE WHEN ct.actual_quantity >= ct.assigned_quantity AND ct.assigned_quantity > 0 THEN 1 ELSE 0 END) as met_targets,
               MAX(CASE WHEN ct.status IN ('Submitted to Dean', 'Dean Approved') THEN 1 ELSE 0 END) as is_dean_context
        FROM tbl_employee_profiles ep
        JOIN tbl_committed_targets ct ON ep.emp_id = ct.emp_id
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        LEFT JOIN tbl_system_access sa ON ep.emp_id = sa.emp_id
        WHERE mi.term_id = %s
        GROUP BY ep.emp_id, ep.first_name, ep.last_name, ep.academic_rank, ep.specialization, ep.assigned_program, ep.designation, sa.system_role
        -- A plain Designated Faculty member's evidence must clear Program Chair review first
        -- (get_program_chair_evidence_faculty lists them there) and only reaches 'Submitted to
        -- Dean' once the Program Chair submits the package — same status transition Regular
        -- Faculty goes through. A Program Chair/RET Chair/Dean's own evidence has no one else
        -- to review it, so submit_designated_evidences sends theirs straight to 'Submitted to
        -- Dean' too. Either way, 'Submitted to Dean'/'Dean Approved' is the correct, sole gate
        -- for landing here — a prior broader OR-branch let anyone with a non-Regular-Faculty
        -- designation in at the earlier 'Submitted' status, before Program Chair sign-off.
        HAVING MAX(CASE WHEN ct.status IN ('Submitted to Dean', 'Dean Approved') THEN 1 ELSE 0 END) = 1
        ORDER BY ep.last_name, ep.first_name
    """
    rows = timed_query(cursor, query, (term_id,), label="get_dean_evidence_faculty")
    
    pending_list = []
    approved_list = []

    for r in rows:
        enrich_faculty_verification_status(cursor, r, term_id)
        # Check if all committed targets for this faculty member are marked 'Dean Approved'
        cursor.execute("""
            SELECT COUNT(*)
            FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s AND ct.status != 'Dean Approved'
        """, (r['emp_id'], term_id))
        non_approved_count = cursor.fetchone()[0]
        
        is_dean_approved = (non_approved_count == 0)
        r['is_dean_approved'] = is_dean_approved

        if is_dean_approved:
            approved_list.append(r)
        else:
            pending_list.append(r)

    return pending_list, approved_list


def get_dean_faculty_evidence_details(cursor, emp_id, term_id):
    """
    Fetches ALL committed targets and uploaded evidence files for a faculty member for the Dean.
    """
    from app.models.faculty import get_faculty_committed_targets, get_evidence_by_target
    targets = get_faculty_committed_targets(cursor, emp_id, term_id)
    for t in targets:
        ev_list = get_evidence_by_target(cursor, t['target_id'])
        t['evidence_list'] = ev_list
    return targets


