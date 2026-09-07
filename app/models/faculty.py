# Trigger reload 19
from app.models.criteria import SLUG_RESEARCH, SLUG_EXTENSION, rank_band
from app.models.scoring import format_duration


def get_faculty_assigned_targets(cursor, emp_id, term_id):
    from app.models.connection import timed_query
    
    # Sync reviewed quantities from the Program Chair review back to draft targets
    cursor.execute("""
        UPDATE tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        JOIN tbl_ipcr_chair_review cr ON dt.emp_id = cr.emp_id AND cr.term_id = mi.term_id
        JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
        SET dt.proposed_quantity = ri.reviewed_quantity
        WHERE dt.emp_id = %s
    """, (emp_id,))
    
    # Check if this user has already submitted their targets to the review registry
    count_result = timed_query(cursor, """
        SELECT COUNT(*) as cnt FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        WHERE dt.emp_id = %s AND mi.term_id = %s
    """, (emp_id, term_id), label="get_faculty_assigned_targets_check")
    has_submitted = count_result[0]['cnt'] > 0 if count_result else False

    if has_submitted:
        query = """
            SELECT dt.draft_id as target_id, dt.indicator_id,
                   COALESCE(
                       CASE WHEN cr.overall_status IN ('Approved', 'Rejected') THEN ri.reviewed_quantity ELSE NULL END,
                       CASE WHEN rr.overall_status IN ('Approved', 'Rejected', 'Pending') THEN rri.reviewed_quantity ELSE NULL END,
                       dt.proposed_quantity
                   ) as assigned_quantity,
                   dt.review_status as status,
                   COALESCE(dt.target_description, da.custom_description, mi.indicator_description) as indicator_description,
                   mi.indicator_description as raw_indicator_description,
                   COALESCE(dt.is_auto_description, da.is_auto_description) as is_auto_description,
                   COALESCE(dt.target_duration_value, da.target_duration_value) as target_duration_value,
                   COALESCE(dt.target_duration_unit, da.target_duration_unit) as target_duration_unit,
                   COALESCE(dt.target_deadline, da.target_deadline) as target_deadline,
                   tc.category_name,
                   ri.item_remarks as chair_item_remarks,
                   ri.reviewed_quantity as chair_reviewed_quantity,
                   rri.item_remarks as ret_item_remarks,
                   rri.reviewed_quantity as ret_reviewed_quantity
            FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            LEFT JOIN tbl_draft_allocation da ON da.emp_id = dt.emp_id AND da.indicator_id = dt.indicator_id
            LEFT JOIN tbl_ipcr_chair_review cr
                ON cr.emp_id = dt.emp_id AND cr.term_id = mi.term_id
            LEFT JOIN tbl_ipcr_chair_review_items ri
                ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
            LEFT JOIN tbl_ipcr_ret_review rr
                ON rr.emp_id = dt.emp_id AND rr.term_id = mi.term_id
            LEFT JOIN tbl_ipcr_ret_review_items rri
                ON rri.review_id = rr.review_id AND rri.draft_id = dt.draft_id
            WHERE dt.emp_id = %s AND mi.term_id = %s
            ORDER BY tc.category_name, mi.indicator_id
        """
    else:
        query = """
            SELECT MIN(da.allocation_id) as target_id, da.indicator_id, MAX(da.assigned_quantity) as assigned_quantity, 'Draft' as status,
                   COALESCE(MAX(da.custom_description), mi.indicator_description) as indicator_description,
                   mi.indicator_description as raw_indicator_description,
                   MAX(da.is_auto_description) as is_auto_description,
                   MAX(da.target_duration_value) as target_duration_value,
                   MAX(da.target_duration_unit) as target_duration_unit,
                   MAX(da.target_deadline) as target_deadline,
                   tc.category_name,
                   NULL as chair_item_remarks, NULL as chair_reviewed_quantity
            FROM tbl_draft_allocation da
            JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
            LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            JOIN tbl_employee_profiles ep ON da.emp_id = ep.emp_id
            WHERE ep.specialization = (SELECT specialization FROM tbl_employee_profiles WHERE emp_id = %s)
              AND ep.designation = 'Regular Faculty'
              AND mi.term_id = %s
            GROUP BY da.indicator_id, mi.indicator_description, tc.category_name
            ORDER BY tc.category_name, da.indicator_id
        """
    targets = timed_query(cursor, query, (emp_id, term_id), label="get_faculty_assigned_targets_load")
    # Filter out designated 10 hours teaching load target for Regular Faculty
    targets = [t for t in targets if '10 hours' not in str(t.get('indicator_description', '')) and '10 hrs' not in str(t.get('indicator_description', ''))]

    # Never trust a stored description for an auto row — regenerate from the raw indicator and
    # the actually-assigned quantity/duration every time this is read. Regular Faculty never
    # type this field themselves (it's filled in upstream by Program Chair/RET Chair), so
    # there's nothing to lose by always recomputing it, and it self-corrects any row saved
    # before this substitution logic existed.
    from app.models.ipcr_description import format_ipcr_target_description
    for t in targets:
        is_auto = t.get('is_auto_description') is None or t.get('is_auto_description') == 1
        if is_auto and t.get('raw_indicator_description'):
            t['indicator_description'] = format_ipcr_target_description(
                t.get('raw_indicator_description'), t.get('assigned_quantity'),
                t.get('target_duration_value'), t.get('target_duration_unit'))

    # Ensure the mandatory Teaching Load target is present. Hours and duration come from
    # the Admin's teaching-load configuration rather than a hardcoded literal.
    from app.models.institution import resolve_teaching_load, teaching_load_description
    cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
    rank_row = cursor.fetchone()
    tl_hours, tl_dur_value, tl_dur_unit = resolve_teaching_load(
        cursor, term_id, 'Regular Faculty', rank_row[0] if rank_row else None)
    tl_desc = teaching_load_description(tl_hours)

    has_teaching_load = any(
        t.get('category_name') == 'A. Instructions' and 'Teaching Load' in str(t.get('indicator_description', ''))
        for t in targets
    )
    if not has_teaching_load:
        cursor.execute("SELECT category_id FROM tbl_target_categories WHERE slug = 'instruction'")
        cat_row = cursor.fetchone()
        cat_id = cat_row[0] if cat_row else 1
        cursor.execute("""
            SELECT indicator_id FROM tbl_master_indicators
            WHERE indicator_description = %s AND term_id = %s
        """, (tl_desc, term_id))
        ind_row = cursor.fetchone()
        if ind_row:
            tl_ind_id = ind_row[0]
        else:
            cursor.execute("""
                INSERT INTO tbl_master_indicators (category_id, indicator_description, efficiency_type, term_id, is_custom)
                VALUES (%s, %s, 'Output-Based', %s, 0)
            """, (cat_id, tl_desc, term_id))
            tl_ind_id = cursor.lastrowid

        mandatory_target = {
            'target_id': f'tl_{tl_ind_id}',
            'indicator_id': tl_ind_id,
            'assigned_quantity': tl_hours,
            'status': 'Draft',
            'indicator_description': tl_desc,
            'target_deadline': format_duration(tl_dur_value, tl_dur_unit),
            'category_name': 'A. Instructions',
            'chair_item_remarks': None,
            'chair_reviewed_quantity': None,
            'is_mandatory': True
        }
        targets.insert(0, mandatory_target)
    else:
        for t in targets:
            if t.get('category_name') == 'A. Instructions' and 'Teaching Load' in str(t.get('indicator_description', '')):
                t['is_mandatory'] = True
                if not t.get('assigned_quantity'):
                    t['assigned_quantity'] = tl_hours

    return targets


def get_faculty_chair_review_status(cursor, emp_id, term_id):
    """
    Returns the Program Chair's current review record for this faculty member,
    or None if no review has been started yet.
    Used by the faculty dashboard to display the 'Returned' alert with remarks.
    """
    cursor.execute("""
        SELECT review_id, overall_status, overall_remarks, reviewed_at
        FROM tbl_ipcr_chair_review
        WHERE emp_id = %s AND term_id = %s
    """, (emp_id, term_id))
    row = cursor.fetchone()
    if row:
        return {
            'review_id':      row[0],
            'overall_status': row[1],
            'overall_remarks': row[2],
            'reviewed_at':    row[3],
        }
    return None


def get_faculty_ret_menu(cursor, academic_rank, term_id):
    from app.models.connection import timed_query
    # Rules are configured against the canonical Academic Rank Band ('Instructor'), not a
    # faculty member's specific sub-rank ('Instructor II') — normalize before matching.
    band = rank_band(academic_rank)
    query = """
        SELECT r.required_selections, mi.indicator_id, mi.indicator_description, tc.category_name, tc.slug,
               rri.target_quantity, rri.target_description, rri.target_duration_value, rri.target_duration_unit
        FROM tbl_ret_rules r
        JOIN tbl_ret_rule_indicators rri ON r.rule_id = rri.rule_id
        JOIN tbl_master_indicators mi ON rri.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE r.academic_rank = %s AND mi.term_id = %s
    """
    results = timed_query(cursor, query, (band, term_id), label="get_faculty_ret_menu")

    ret_menu = {
        'research_required': 0,
        'extension_required': 0,
        'research_indicators': [],
        'extension_indicators': []
    }

    for r in results:
        if r['slug'] == SLUG_RESEARCH:
            ret_menu['research_required'] = int(r['required_selections'])
            ret_menu['research_indicators'].append(r)
        elif r['slug'] == SLUG_EXTENSION:
            ret_menu['extension_required'] = int(r['required_selections'])
            ret_menu['extension_indicators'].append(r)

    return ret_menu


def save_faculty_ret_selections(conn, cursor, emp_id, term_id, selected_indicator_ids):
    # This helper is deprecated as RET selections are processed inside the submit pipeline,
    # but we keep a dummy return for backward compatibility.
    return True, "RET selections processed."


def is_faculty_ret_eligible(cursor, emp_id, term_id):
    """
    Option B: every regular faculty may take Research targets (optional self-select).
    There is no per-faculty enable gate anymore — eligibility simply means the faculty's
    rank has a Research menu configured for the term (otherwise there is nothing to show).
    """
    if not term_id:
        return False
    cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
    row = cursor.fetchone()
    academic_rank = row[0] if row else None
    if not academic_rank:
        return False
    band = rank_band(academic_rank)
    cursor.execute("""
        SELECT COUNT(*)
        FROM tbl_ret_rules r
        JOIN tbl_ret_rule_indicators rri ON r.rule_id = rri.rule_id
        JOIN tbl_master_indicators mi ON rri.indicator_id = mi.indicator_id
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE r.academic_rank = %s AND (mi.term_id = %s OR mi.term_id IS NULL)
          AND (
              LOWER(COALESCE(tc.slug, '')) = 'research'
              OR LOWER(COALESCE(tc.category_name, '')) LIKE '%%research%%'
              OR LOWER(COALESCE(tc.review_lane, '')) = 'ret'
          )
    """, (band, term_id))
    return cursor.fetchone()[0] > 0


def is_faculty_resubmission(cursor, emp_id, term_id):
    """
    True once a Program Chair review record exists for this faculty/term — i.e. this is
    at least the faculty member's second pass through the submit pipeline (a first
    submission already happened, or was returned for corrections). Shared by the dashboard
    gating check, the submit route, and submit_faculty_ipcr so all three agree on what
    counts as a resubmission.
    """
    cursor.execute("""
        SELECT 1 FROM tbl_ipcr_chair_review
        WHERE emp_id = %s AND term_id = %s
        LIMIT 1
    """, (emp_id, term_id))
    return cursor.fetchone() is not None


def check_faculty_draft_gating(cursor, emp_id, term_id):
    """
    Regular Faculty may only submit an *initial* draft IPCR once the Program Chair has
    allocated their department's baseline Instruction/Support targets and the RET Chair
    has configured Research/Extension rules for their rank band. Without this, a faculty
    member in an unallocated department gets nothing but the mandatory Teaching Load
    target synthesized, is_faculty_ret_eligible() evaluates False for lack of any RET
    rule, and the submission silently skips RET review entirely, delivering a crippled
    single-item IPCR straight to the Program Chair.

    Bypassed for non-Regular-Faculty designations (they don't use this submit pipeline)
    and for resubmissions — by the time a return/resubmit cycle exists the prerequisites
    were already met once, and re-blocking on a later change (e.g. the chair adjusting an
    allocation) would strand a returned IPCR with no way to resubmit.
    """
    result = {
        'can_submit': True,
        'has_chair_instruction': True,
        'has_chair_support': True,
        'has_ret_extension': True,
        'has_ret_research': True,
        'missing_reasons': [],
    }
    if not term_id:
        return result

    cursor.execute(
        "SELECT designation, academic_rank, specialization FROM tbl_employee_profiles WHERE emp_id = %s",
        (emp_id,))
    row = cursor.fetchone()
    designation = row[0] if row else None
    academic_rank = row[1] if row else None
    specialization = row[2] if row else None

    if designation != 'Regular Faculty':
        return result

    if is_faculty_resubmission(cursor, emp_id, term_id):
        return result

    # Scoped by specialization (not just this emp_id) to match how submit_faculty_ipcr
    # itself pulls chair allocations — a faculty member who joined after the Program
    # Chair's batch save has no tbl_draft_allocation row of their own yet, but the
    # department-wide allocation still applies to them.
    cursor.execute("""
        SELECT DISTINCT tc.slug
        FROM tbl_draft_allocation da
        JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        JOIN tbl_employee_profiles ep ON da.emp_id = ep.emp_id
        WHERE mi.term_id = %s
          AND ep.specialization = %s
          AND ep.designation = 'Regular Faculty'
          AND tc.slug IN ('instruction', 'support')
          AND da.assigned_quantity > 0
    """, (term_id, specialization))
    chair_slugs = {r[0] for r in cursor.fetchall()}
    result['has_chair_instruction'] = 'instruction' in chair_slugs
    result['has_chair_support'] = 'support' in chair_slugs

    if not academic_rank:
        result['has_ret_extension'] = False
        result['has_ret_research'] = False
    else:
        ret_menu = get_faculty_ret_menu(cursor, academic_rank, term_id)
        result['has_ret_extension'] = len(ret_menu['extension_indicators']) > 0
        result['has_ret_research'] = ret_menu['research_required'] > 0

    band = rank_band(academic_rank)
    if not result['has_chair_instruction']:
        result['missing_reasons'].append("Program Chair has not allocated Strategic Priorities (Instruction) targets for your specialization")
    if not result['has_chair_support']:
        result['missing_reasons'].append("Program Chair has not allocated Support Function targets for your specialization")
    if not academic_rank:
        result['missing_reasons'].append("Your profile has no academic rank set, so RET Chair rules cannot be matched")
    else:
        if not result['has_ret_extension']:
            result['missing_reasons'].append(f"RET Chair has not configured Extension targets for your rank ({band})")
        if not result['has_ret_research']:
            result['missing_reasons'].append(f"RET Chair has not configured a Research target pool for your rank ({band})")

    result['can_submit'] = len(result['missing_reasons']) == 0
    return result


def submit_faculty_ipcr(conn, cursor, emp_id, term_id, selected_research_targets):
    """
    selected_research_targets parameter format:
    [
        {'indicator_id': 12, 'proposed_quantity': 1},
        ...
    ]
    """
    if not term_id:
        return False, "No active term specified."

    active_term_id = int(term_id)
    conn.autocommit = False
    try:
        # Resolve once: RET rank rules are keyed by canonical Academic Rank Band, not a
        # faculty member's specific sub-rank — every rank-band lookup below uses this.
        cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        rank_row = cursor.fetchone()
        emp_rank_band = rank_band(rank_row[0] if rank_row else None)

        is_resubmission = is_faculty_resubmission(cursor, emp_id, active_term_id)
        if not is_resubmission:
            gating = check_faculty_draft_gating(cursor, emp_id, active_term_id)
            if not gating['can_submit']:
                return False, "Cannot submit draft IPCR. Prerequisites not met: " + "; ".join(gating['missing_reasons'])

        ret_eligible = is_faculty_ret_eligible(cursor, emp_id, active_term_id)
        ret_editable = False
        if not ret_eligible:
            # Non-RET faculty bypass RET review stage completely -> target_status is immediately 'Waiting for Approval' (for Program Chair)
            target_status = 'Waiting for Approval'
        else:
            target_status = 'Waiting for Approval' if is_resubmission else 'Pending Review'
            ret_editable = True


        # 1. Sync any reviewed quantities from the chair's decision back into tbl_draft_targets FIRST
        # to preserve any adjustments made by the Program Chair on standard workloads.
        cursor.execute("""
            UPDATE tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            JOIN tbl_ipcr_chair_review cr ON dt.emp_id = cr.emp_id AND cr.term_id = mi.term_id
            JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
            SET dt.proposed_quantity = ri.reviewed_quantity
            WHERE dt.emp_id = %s
        """, (emp_id,))

        # 2. Gather all assigned regular workloads distributed by the Program Chair for this specialization (if any)
        cursor.execute("""
            SELECT da.indicator_id, MAX(da.assigned_quantity), MAX(da.custom_description), MAX(da.target_deadline),
                   MAX(da.target_duration_value), MAX(da.target_duration_unit)
            FROM tbl_draft_allocation da
            JOIN tbl_employee_profiles ep ON da.emp_id = ep.emp_id
            WHERE ep.specialization = (SELECT specialization FROM tbl_employee_profiles WHERE emp_id = %s)
              AND ep.designation = 'Regular Faculty'
            GROUP BY da.indicator_id
        """, (emp_id,))
        chair_allocations = cursor.fetchall()

        # 3. Process and migrate standard workloads into tbl_draft_targets
        for ind_id, qty, cust_desc, t_dead, dur_value, dur_unit in chair_allocations:
            cursor.execute("""
                SELECT draft_id FROM tbl_draft_targets
                WHERE emp_id = %s AND indicator_id = %s
            """, (emp_id, ind_id))
            existing_draft = cursor.fetchone()

            if existing_draft:
                cursor.execute("""
                    UPDATE tbl_draft_targets
                    SET proposed_quantity = %s, review_status = %s, target_description = %s, target_deadline = %s,
                        target_duration_value = %s, target_duration_unit = %s
                    WHERE draft_id = %s
                """, (qty, target_status, cust_desc, t_dead, dur_value, dur_unit, existing_draft[0]))
            else:
                cursor.execute("""
                    INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status, target_description, target_deadline,
                                                   target_duration_value, target_duration_unit)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (emp_id, ind_id, qty, target_status, cust_desc, t_dead, dur_value, dur_unit))

        # Ensure the mandatory Teaching Load target is saved, using the Admin's configured
        # hours and duration so it can be scored for Timeliness like any other target.
        from app.models.institution import resolve_teaching_load, teaching_load_description
        cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        tl_rank_row = cursor.fetchone()
        tl_hours, tl_dur_value, tl_dur_unit = resolve_teaching_load(
            cursor, active_term_id, 'Regular Faculty', tl_rank_row[0] if tl_rank_row else None)
        tl_desc = teaching_load_description(tl_hours)
        tl_deadline = format_duration(tl_dur_value, tl_dur_unit)

        cursor.execute("SELECT category_id FROM tbl_target_categories WHERE slug = 'instruction'")
        cat_row = cursor.fetchone()
        cat_id = cat_row[0] if cat_row else 1
        cursor.execute("SELECT indicator_id FROM tbl_master_indicators WHERE indicator_description = %s AND term_id = %s",
                       (tl_desc, active_term_id))
        tl_row = cursor.fetchone()
        if tl_row:
            tl_ind_id = tl_row[0]
        else:
            cursor.execute("INSERT INTO tbl_master_indicators (category_id, indicator_description, efficiency_type, term_id, is_custom) VALUES (%s, %s, 'Output-Based', %s, 0)",
                           (cat_id, tl_desc, active_term_id))
            tl_ind_id = cursor.lastrowid

        cursor.execute("SELECT draft_id FROM tbl_draft_targets WHERE emp_id = %s AND indicator_id = %s", (emp_id, tl_ind_id))
        tl_draft = cursor.fetchone()
        if not tl_draft:
            cursor.execute("""
                INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                               target_description, target_deadline,
                                               target_duration_value, target_duration_unit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (emp_id, tl_ind_id, tl_hours, target_status, tl_desc, tl_deadline,
                  tl_dur_value, tl_dur_unit))

        # 4. If this is a re-submission or non-RET submission, update status of existing standard workloads to target_status
        cursor.execute("""
            UPDATE tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            SET dt.review_status = %s
            WHERE dt.emp_id = %s
              AND tc.review_lane <> 'RET'
        """, (target_status, emp_id))

        if not ret_eligible:
            # No Research menu for this rank: clear any existing Research targets.
            # Extension is distributed independently and is not touched here.
            cursor.execute("""
                DELETE dt FROM tbl_draft_targets dt
                JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                WHERE dt.emp_id = %s
                  AND tc.slug = 'research'
            """, (emp_id,))
        else:
            # RET-eligible faculty: check if Research & Extension targets are editable
            ret_editable = True
            if active_term_id:
                cursor.execute(
                    """
                    SELECT overall_status FROM tbl_ipcr_ret_review 
                    WHERE emp_id = %s AND term_id = %s
                    """,
                    (emp_id, active_term_id)
                )
                ret_row = cursor.fetchone()
                if ret_row:
                    ret_status = ret_row[0]
                    if ret_status == 'Approved':
                        ret_editable = False

            if ret_editable:
                # Rewrite only Research selections. Extension is distributed separately
                # and must survive this rewrite (scoped to slug='research').
                cursor.execute("""
                    DELETE dt FROM tbl_draft_targets dt
                    JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                    JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                    WHERE dt.emp_id = %s
                      AND tc.slug = 'research'
                """, (emp_id,))

                # Process and write faculty-selected Research targets
                for target in selected_research_targets:
                    res_ind_id = target['indicator_id']

                    # Pull the rank menu's quantity, IPCR description and target duration
                    # so research targets are scorable for Timeliness like any other target.
                    cursor.execute("""
                        SELECT rri.target_quantity, rri.target_description,
                               rri.target_duration_value, rri.target_duration_unit
                        FROM tbl_ret_rule_indicators rri
                        JOIN tbl_ret_rules r ON rri.rule_id = r.rule_id
                        WHERE r.academic_rank = %s AND rri.indicator_id = %s
                        LIMIT 1
                    """, (emp_rank_band, res_ind_id))
                    row = cursor.fetchone()
                    res_qty = row[0] if (row and row[0] is not None) else 1
                    res_desc = row[1] if row else None
                    res_dur_value = row[2] if row else None
                    res_dur_unit = row[3] if row else None
                    res_deadline = format_duration(res_dur_value, res_dur_unit)

                    cursor.execute("""
                        INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                                       target_description, target_deadline,
                                                       target_duration_value, target_duration_unit)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (emp_id, res_ind_id, res_qty, target_status, res_desc, res_deadline,
                          res_dur_value, res_dur_unit))

                # Materialize the RET Chair's direct Research assignments (locked — always
                # present regardless of self-selection). Chair-assigned quantities are
                # authoritative if the same indicator was also self-selected.
                # Assigned research inherits any rank-menu description/duration unless overridden by the chair.
                cursor.execute("""
                    SELECT ra.indicator_id, ra.target_quantity,
                           COALESCE(ra.target_description, rri.target_description),
                           COALESCE(ra.target_duration_value, rri.target_duration_value),
                           COALESCE(ra.target_duration_unit, rri.target_duration_unit)
                    FROM tbl_ret_assignments ra
                    LEFT JOIN tbl_ret_rule_indicators rri ON rri.indicator_id = ra.indicator_id
                    LEFT JOIN tbl_ret_rules r ON rri.rule_id = r.rule_id
                        AND r.academic_rank = %s
                    WHERE ra.emp_id = %s AND ra.term_id = %s
                """, (emp_rank_band, emp_id, active_term_id))
                for assign_ind_id, assign_qty, a_desc, a_dur_value, a_dur_unit in cursor.fetchall():
                    a_deadline = format_duration(a_dur_value, a_dur_unit)
                    cursor.execute("""
                        SELECT draft_id FROM tbl_draft_targets
                        WHERE emp_id = %s AND indicator_id = %s
                    """, (emp_id, assign_ind_id))
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute("""
                            UPDATE tbl_draft_targets
                            SET proposed_quantity = %s, review_status = %s, target_description = %s,
                                target_deadline = %s, target_duration_value = %s, target_duration_unit = %s
                            WHERE draft_id = %s
                        """, (assign_qty, target_status, a_desc, a_deadline, a_dur_value, a_dur_unit, existing[0]))
                    else:
                        cursor.execute("""
                            INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                                           target_description, target_deadline,
                                                           target_duration_value, target_duration_unit)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (emp_id, assign_ind_id, assign_qty, target_status, a_desc, a_deadline,
                              a_dur_value, a_dur_unit))
            else:
                # RET review already decided: Research is locked from further self-editing.
                #
                # Only a *rejected* research selection goes back into review. An approved
                # one must keep its 'Approved' status — resetting it made the Program Chair
                # show "Awaiting RET Chair Approval" and refuse to approve, while the RET
                # Chair's own review still read Approved so nothing appeared in their queue.
                # The faculty member could not move in either direction.
                if ret_status == 'Rejected':
                    cursor.execute("""
                        UPDATE tbl_draft_targets dt
                        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                        SET dt.review_status = %s
                        WHERE dt.emp_id = %s
                          AND tc.slug = 'research'
                    """, (target_status, emp_id))

        # 7b. Materialize rank-band Extension targets — locked (not self-selectable),
        # independent of Research eligibility. Rewrite from the rank band's configured menu
        # so a removed/reconfigured indicator disappears on resubmit. Extension auto-flows to
        # the Program Chair (it never enters RET review).
        if active_term_id:
            cursor.execute("""
                DELETE dt FROM tbl_draft_targets dt
                JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                WHERE dt.emp_id = %s AND tc.slug = 'extension'
            """, (emp_id,))
            cursor.execute("""
                SELECT rri.indicator_id, rri.target_quantity, rri.target_description,
                       rri.target_duration_value, rri.target_duration_unit
                FROM tbl_ret_rules r
                JOIN tbl_ret_rule_indicators rri ON r.rule_id = rri.rule_id
                JOIN tbl_master_indicators mi ON rri.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                WHERE r.academic_rank = %s AND mi.term_id = %s AND tc.slug = 'extension'
            """, (emp_rank_band, active_term_id))
            for ext_ind_id, ext_qty, ext_desc, ext_dur_value, ext_dur_unit in cursor.fetchall():
                # Extension is RET-Chair-configured per rank band and auto-flows (never enters
                # RET review), so it is materialized already 'Approved' — this lets the Program
                # Chair see it as RET-approved and covers faculty who have extension but no
                # research. The duration carries over so Timeliness can be scored.
                cursor.execute("""
                    INSERT INTO tbl_draft_targets (emp_id, indicator_id, proposed_quantity, review_status,
                                                   target_description, target_deadline,
                                                   target_duration_value, target_duration_unit)
                    VALUES (%s, %s, %s, 'Approved', %s, %s, %s, %s)
                """, (emp_id, ext_ind_id, ext_qty, ext_desc,
                      format_duration(ext_dur_value, ext_dur_unit), ext_dur_value, ext_dur_unit))

        # 8. Update existing Program Chair review records for active term to 'Pending' and clear items/remarks
        if active_term_id and is_resubmission:
            cursor.execute("""
                SELECT review_id FROM tbl_ipcr_chair_review 
                WHERE emp_id = %s AND term_id = %s
            """, (emp_id, active_term_id))
            existing_review = cursor.fetchone()
            if existing_review:
                review_id = existing_review[0]
                # Delete ONLY Research and Extension review items to preserve standard workload adjustments
                cursor.execute("""
                    DELETE ri FROM tbl_ipcr_chair_review_items ri
                    JOIN tbl_master_indicators mi ON ri.indicator_id = mi.indicator_id
                    JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                    WHERE ri.review_id = %s
                      AND tc.review_lane = 'RET'
                """, (review_id,))

                # Sync/update the standard workload review items to match the new draft proposed quantities.
                # We conditionally update reviewed_quantity: if it matches original_quantity (meaning
                # it was not custom edited by the Program Chair), we sync it. Otherwise, we preserve
                # the custom edited value.
                cursor.execute("""
                    UPDATE tbl_ipcr_chair_review_items ri
                    JOIN tbl_draft_targets dt ON ri.draft_id = dt.draft_id
                    JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                    JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                    SET ri.reviewed_quantity = CASE 
                            WHEN ri.reviewed_quantity = ri.original_quantity THEN dt.proposed_quantity 
                            ELSE ri.reviewed_quantity 
                        END,
                        ri.original_quantity = dt.proposed_quantity
                    WHERE ri.review_id = %s
                      AND tc.review_lane = 'CHAIR' AND tc.is_core = 1
                """, (review_id,))

                cursor.execute("""
                    UPDATE tbl_ipcr_chair_review
                    SET overall_status = 'Pending',
                        overall_remarks = NULL,
                        reviewed_at = NULL
                    WHERE review_id = %s
                """, (review_id,))

        # 8b. Reset RET Chair review record status if it exists for active term
        if active_term_id:
            cursor.execute("""
                SELECT review_id, overall_status FROM tbl_ipcr_ret_review
                WHERE emp_id = %s AND term_id = %s
            """, (emp_id, active_term_id))
            existing_ret_review = cursor.fetchone()
            if existing_ret_review:
                ret_review_id = existing_ret_review[0]
                ret_status = existing_ret_review[1]
                if ret_editable or ret_status == 'Rejected':
                    if ret_editable:
                        # If editable, delete items so they rebuild from scratch
                        cursor.execute("DELETE FROM tbl_ipcr_ret_review_items WHERE review_id = %s", (ret_review_id,))
                    
                    # Reset review header status to Pending so RET Chair can review it again
                    cursor.execute("""
                        UPDATE tbl_ipcr_ret_review
                        SET overall_status = 'Pending',
                            overall_remarks = NULL,
                            reviewed_at = NULL
                        WHERE review_id = %s
                    """, (ret_review_id,))

        conn.commit()
        if not ret_editable or is_resubmission:
            return True, "IPCR successfully submitted for approval."
        return True, "IPCR successfully submitted for review."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.autocommit = True


# ──────────────────────────────────────────────
# Process 6: Evidence Gathering Helpers
# ──────────────────────────────────────────────

def get_faculty_committed_targets(cursor, emp_id, term_id):
    from app.models.connection import timed_query
    from app.models.scoring import build_actual_accomplishment, client_satisfaction_label
    query = """
        SELECT ct.target_id, ct.indicator_id, ct.assigned_quantity, ct.actual_quantity, ct.status,
               COALESCE(ct.target_description, mi.indicator_description) as indicator_description,
               mi.indicator_description as raw_indicator_description, ct.is_auto_description,
               ct.target_deadline, ct.target_duration_value, ct.target_duration_unit,
               ct.actual_duration_value, ct.completion_status, ct.efficiency_rating_E,
               ct.is_admin_function, ct.print_remarks,
               mi.efficiency_type,
               tc.category_name, tc.category_id,
               COALESCE(ev.evidence_count, 0) as evidence_count
        FROM tbl_committed_targets ct
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        LEFT JOIN (
            SELECT target_id, COUNT(*) as evidence_count FROM tbl_evidence_repo GROUP BY target_id
        ) ev ON ev.target_id = ct.target_id
        WHERE ct.emp_id = %s AND mi.term_id = %s AND ct.assigned_quantity > 0
        ORDER BY tc.category_name, mi.indicator_id
    """
    rows = timed_query(cursor, query, (emp_id, term_id), label="get_faculty_committed_targets")
    # Compose the IPCR "Actual Accomplishments" sentence and derive Q/E/T for each target.
    from app.models.scoring import compute_target_rating
    from app.models.ipcr_description import format_ipcr_target_description
    for r in rows:
        is_auto = r.get('is_auto_description') is None or r.get('is_auto_description') == 1
        if is_auto:
            # Never trust the stored description for an auto row — regenerate from the raw
            # indicator and the actually-assigned quantity/duration every time this is read.
            # A row saved before this substitution logic existed (or one whose allocation
            # later changed) would otherwise keep showing stale text indefinitely; Regular
            # Faculty never type this field themselves, so there's nothing to lose by always
            # recomputing it.
            r['indicator_description'] = format_ipcr_target_description(
                r.get('raw_indicator_description'), r.get('assigned_quantity'),
                r.get('target_duration_value'), r.get('target_duration_unit'))
        r['actual_accomplishment'] = build_actual_accomplishment(
            r.get('indicator_description'),
            r.get('actual_quantity'),
            r.get('actual_duration_value'),
            r.get('target_duration_unit'),
            client_satisfaction_label(r.get('efficiency_rating_E')),
            raw_indicator_description=r.get('raw_indicator_description'),
            is_auto_description=r.get('is_auto_description'),
        )
        r['rating'] = compute_target_rating(r)
    return rows


def save_accomplishment_details(conn, cursor, emp_id, target_id, actual_duration_value,
                                completion_status, efficiency_rating_E, print_remarks=None):
    """
    Save the per-target accomplishment inputs used for Timeliness (T) and, where the
    indicator is client-satisfaction rated, Efficiency (E). Ownership is enforced so a
    faculty member can only update their own committed targets.

    print_remarks is the free-text note that appears in the printed IPCR's Remarks column.
    """
    from app.models.scoring import COMPLETION_STATUSES
    try:
        cursor.execute(
            "SELECT emp_id FROM tbl_committed_targets WHERE target_id = %s", (target_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Target not found."
        if row[0] != emp_id:
            return False, "You can only update your own targets."

        if completion_status and completion_status not in COMPLETION_STATUSES:
            return False, "Invalid completion status."
        completion_status = completion_status or 'COMPLETED'

        remarks = (print_remarks or '').strip()[:255] or None
        cursor.execute("""
            UPDATE tbl_committed_targets
            SET actual_duration_value = %s, completion_status = %s, efficiency_rating_E = %s,
                print_remarks = %s
            WHERE target_id = %s
        """, (actual_duration_value, completion_status, efficiency_rating_E,
              remarks, target_id))
        conn.commit()
        return True, "Accomplishment details saved."
    except Exception as e:
        conn.rollback()
        return False, str(e)


def recalculate_target_accomplished_quantity(cursor, target_id):
    # 1. Confirm the target exists
    cursor.execute("SELECT target_id FROM tbl_committed_targets WHERE target_id = %s", (target_id,))
    if not cursor.fetchone():
        return

    # 2. Sum direct uploads (exclude Rejected evidence)
    cursor.execute("""
        SELECT COALESCE(SUM(actual_qty_Q), 0) FROM tbl_evidence_repo
        WHERE target_id = %s AND verification_status NOT IN ('Rejected', 'Returned')
    """, (target_id,))
    direct_sum = cursor.fetchone()[0]
    
    # 3. Update the target's actual_quantity
    total = direct_sum
    cursor.execute("""
        UPDATE tbl_committed_targets
        SET actual_quantity = %s
        WHERE target_id = %s
    """, (total, target_id))
    return total


def _clear_accomplishment_details_if_unaccomplished(cursor, target_id, total):
    """
    Removing evidence can drop a target back to zero accomplished -- when it does, the
    previously-reported "Completed in"/completion status/efficiency rating no longer
    describe anything real and would otherwise sit there stale. Only called from paths that
    *remove* evidence (delete, unclaim); upload/claim only ever add quantity, so a fresh
    zero there means nothing was ever reported yet, and clearing would risk wiping out a
    completion status the faculty member deliberately set before uploading a qty-0 file.
    """
    if total == 0:
        cursor.execute("""
            UPDATE tbl_committed_targets
            SET actual_duration_value = NULL, completion_status = NULL, efficiency_rating_E = NULL
            WHERE target_id = %s
        """, (target_id,))


def upload_evidence_item(cursor, target_id, file_path, quantity):
    cursor.execute("""
        INSERT INTO tbl_evidence_repo (target_id, file_path, actual_qty_Q, verification_status)
        VALUES (%s, %s, %s, 'Pending')
    """, (target_id, file_path, quantity))
    evidence_id = cursor.lastrowid
    recalculate_target_accomplished_quantity(cursor, target_id)
    return evidence_id


def delete_evidence_item(cursor, evidence_id, emp_id):
    """
    Delete one uploaded evidence file.

    emp_id is required and checked against the owner of the target the evidence hangs off.
    Without it, anyone could delete anyone else's evidence by posting an arbitrary
    evidence_id — the id is the only thing the request carries.
    """
    cursor.execute("""
        SELECT er.target_id, ct.emp_id
        FROM tbl_evidence_repo er
        JOIN tbl_committed_targets ct ON er.target_id = ct.target_id
        WHERE er.evidence_id = %s
    """, (evidence_id,))
    row = cursor.fetchone()
    if not row:
        return False
    target_id, owner_emp_id = row
    if owner_emp_id != emp_id:
        return False

    # Delete evidence item
    cursor.execute("DELETE FROM tbl_evidence_repo WHERE evidence_id = %s", (evidence_id,))

    total = recalculate_target_accomplished_quantity(cursor, target_id)
    _clear_accomplishment_details_if_unaccomplished(cursor, target_id, total)
    return True


def get_evidence_by_target(cursor, target_id):
    from app.models.connection import timed_query
    query = """
        SELECT er.evidence_id, er.file_path, er.actual_qty_Q,
               er.verification_status, er.supervisor_comment
        FROM tbl_evidence_repo er
        WHERE er.target_id = %s
    """
    return timed_query(cursor, query, (target_id,), label="get_evidence_by_target")


def check_faculty_evidence_readiness(cursor, emp_id, term_id, assigned_targets):
    if not assigned_targets:
        return {
            'all_evidence_ready': False,
            'evidence_submitted': False,
            'has_returned_evidence': False,
            'has_missing_timeliness': False,
            'targets_missing_timeliness': [],
            'total_targets': 0,
            'targets_with_evidence': 0,
            'targets_met_qty': 0
        }

    total_targets = len(assigned_targets)
    targets_with_evidence = 0
    targets_met_qty = 0
    submitted_count = 0
    has_returned_evidence = False
    targets_missing_timeliness = []

    for t in assigned_targets:
        ev_list = t.get('evidence_list')
        if ev_list is None:
            ev_list = get_evidence_by_target(cursor, t['target_id'])
            t['evidence_list'] = ev_list

        valid_evs = [e for e in ev_list if e.get('verification_status') not in ('Returned', 'Rejected')]
        if len(valid_evs) > 0:
            targets_with_evidence += 1
            # Evidence exists but there's nothing to compute Timeliness from -- would
            # otherwise resolve to a silently-dropped None instead of a real score. 0 is
            # a legitimate "completed instantly" value (rate_timeliness treats it as
            # valid too) -- only a genuinely blank duration counts as missing.
            if t.get('actual_duration_value') is None:
                targets_missing_timeliness.append(t.get('indicator_description') or f"target #{t.get('target_id')}")

        if any(e.get('verification_status') in ('Returned', 'Rejected') for e in ev_list):
            has_returned_evidence = True

        actual_q = t.get('actual_quantity') or 0
        assigned_q = t.get('assigned_quantity') or 0
        if actual_q >= assigned_q and assigned_q > 0:
            targets_met_qty += 1

        if t.get('status') in ('Submitted', 'Pending Verification', 'Verified', 'Submitted to Dean', 'Dean Approved') and not any(e.get('verification_status') in ('Returned', 'Rejected') for e in ev_list):
            submitted_count += 1

    has_missing_timeliness = len(targets_missing_timeliness) > 0

    # Neither quantity nor evidence needs to be present to submit -- a target a faculty
    # member never accomplished at all is still a valid target to report; scoring.py
    # already handles zero accomplishment gracefully (lowest band, not an error). What still
    # blocks submission is an unresolved Returned/Rejected file (a verifier waiting on a fix)
    # or evidence uploaded with no "Completed in" duration to score Timeliness from.
    all_ready = (total_targets > 0) and not has_returned_evidence and not has_missing_timeliness
    evidence_submitted = (submitted_count == total_targets) and (total_targets > 0) and not has_returned_evidence

    return {
        'all_evidence_ready': all_ready,
        'evidence_submitted': evidence_submitted,
        'has_returned_evidence': has_returned_evidence,
        'has_missing_timeliness': has_missing_timeliness,
        'targets_missing_timeliness': targets_missing_timeliness,
        'total_targets': total_targets,
        'targets_with_evidence': targets_with_evidence,
        'targets_met_qty': targets_met_qty
    }


# Evidence verification states. 'Pending' is set on upload; a verifier moves it to
# 'Approved' or 'Returned'. Returned evidence is excluded from the accomplished
# quantity and re-opens uploading for the faculty member.
EVIDENCE_PENDING = 'Pending'
EVIDENCE_APPROVED = 'Approved'
EVIDENCE_RETURNED = 'Returned'
EVIDENCE_STATUSES = [EVIDENCE_PENDING, EVIDENCE_APPROVED, EVIDENCE_RETURNED]


def set_evidence_verification(conn, cursor, evidence_id, status, comment=None):
    """
    Approve or return a single uploaded evidence file.

    Returning requires a reason, stores it as the supervisor comment, and unlocks the
    owning target so the faculty member can upload a replacement. The accomplished
    quantity is recalculated either way, since returned evidence no longer counts.
    """
    if status not in (EVIDENCE_APPROVED, EVIDENCE_RETURNED):
        return False, "Invalid verification status."
    if status == EVIDENCE_RETURNED and not (comment or '').strip():
        return False, "A reason is required when returning evidence."

    try:
        cursor.execute("SELECT target_id, verification_status FROM tbl_evidence_repo WHERE evidence_id = %s", (evidence_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Evidence not found."
        target_id, current_status = row[0], row[1]
        if current_status == EVIDENCE_APPROVED and status == EVIDENCE_RETURNED:
            return False, "Approved evidence cannot be returned."

        cursor.execute("""
            UPDATE tbl_evidence_repo
            SET verification_status = %s, supervisor_comment = %s
            WHERE evidence_id = %s
        """, (status, (comment or '').strip() or None, evidence_id))

        # Returned evidence re-opens the target for re-upload.
        if status == EVIDENCE_RETURNED:
            cursor.execute(
                "UPDATE tbl_committed_targets SET status = 'Approved' WHERE target_id = %s",
                (target_id,))

        recalculate_target_accomplished_quantity(cursor, target_id)
        conn.commit()
        msg = ("Evidence approved." if status == EVIDENCE_APPROVED
               else "Evidence returned to the faculty member for re-upload.")
        return True, msg
    except Exception as e:
        conn.rollback()
        return False, str(e)


def submit_faculty_evidences(conn, cursor, emp_id, term_id):
    targets = get_faculty_committed_targets(cursor, emp_id, term_id)
    if not targets:
        return False, "No committed targets found."

    readiness = check_faculty_evidence_readiness(cursor, emp_id, term_id, targets)
    if readiness['evidence_submitted']:
        return False, "Evidences have already been submitted for verification."

    if readiness.get('has_missing_timeliness'):
        names = ', '.join(readiness['targets_missing_timeliness'])
        return False, f"Provide a completion duration for evidence already uploaded on: {names}."

    if not readiness['all_evidence_ready']:
        return False, "One or more targets have evidence returned for revision. Please address it before resubmitting."

    try:
        update_sql = "UPDATE tbl_committed_targets ct JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id SET ct.status = 'Submitted' WHERE ct.emp_id = %s AND mi.term_id = %s"
        cursor.execute(update_sql, (emp_id, term_id))
        conn.commit()

        # Snapshot the IPCR rating at submission — this is the record the Dean approves,
        # and it preserves the weights in force at the time even if they change later.
        # A missing weight configuration must not block submission, so failures here are
        # reported alongside success rather than rolling the submission back.
        from app.models.scoring import save_final_score
        scored, score_msg, _ = save_final_score(conn, cursor, emp_id, term_id)
        if scored:
            return True, f"Evidences submitted successfully for verification. {score_msg}"
        return True, f"Evidences submitted successfully for verification. (Rating not computed: {score_msg})"
    except Exception as e:
        conn.rollback()
        return False, f"Error submitting evidences: {str(e)}"


def enrich_faculty_verification_status(cursor, faculty_dict, term_id):
    """
    Computes the verification status for a faculty member across Program Chair (CHAIR) and RET Chair (RET).
    Sets:
      - verification_status_code: 'APPROVED', 'WAITING_CHAIR', 'WAITING_RET', 'SUBMITTED'
      - evidence_status: Human-readable status label
      - is_both_approved: True if both Program Chair and RET Chair have approved all respective evidence items
      - chair_finished: True if Program Chair target evidences are all approved (or no Chair targets exist)
      - ret_finished: True if RET target evidences are all approved, or there are no RET targets /
        no RET evidence was uploaded (nothing for the RET Chair to verify)

    Regular Faculty bypass the RET gate entirely: RET Chair no longer verifies their
    evidence, Program Chair approves everything (Instruction, Support, Research, Extension
    alike), so ret_finished is forced True for them regardless of RET-categorized evidence
    state. Designated faculty keep the full dual-gate — this isn't about RET Chair review
    (they never review designated faculty's evidence either; the Dean does, directly), it's
    so Dean's own final-approval gate still requires every evidence file, R&E-categorized
    ones included, to be explicitly reviewed before a designated faculty's package clears.
    """
    emp_id = faculty_dict['emp_id']
    cursor.execute("SELECT designation FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
    desig_row = cursor.fetchone()
    designation = (desig_row[0] or '').strip() if desig_row else ''
    from app.models.criteria import is_designated
    is_regular_faculty = not is_designated(designation)

    cursor.execute("""
        SELECT 
            tc.category_name,
            er.evidence_id,
            er.verification_status,
            ct.status
        FROM tbl_committed_targets ct
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        LEFT JOIN tbl_evidence_repo er ON er.target_id = ct.target_id
        WHERE ct.emp_id = %s AND mi.term_id = %s
    """, (emp_id, term_id))
    rows = cursor.fetchall()

    chair_targets_has_ev = False
    chair_all_approved = True
    chair_has_targets = False

    ret_targets_has_ev = False
    ret_all_approved = True
    ret_has_targets = False
    is_submitted_to_dean = any(r[3] in ('Submitted to Dean', 'Dean Approved') for r in rows) if rows else False

    for cat_name, ev_id, ev_status, ct_status in rows:
        cat_str = (cat_name or '')
        is_ret = ('Research' in cat_str or 'Extension' in cat_str)
        if is_ret:
            ret_has_targets = True
            if ev_id is not None:
                ret_targets_has_ev = True
                if ev_status != 'Approved':
                    ret_all_approved = False
        else:
            chair_has_targets = True
            if ev_id is not None:
                chair_targets_has_ev = True
                if ev_status != 'Approved':
                    chair_all_approved = False

    if not chair_has_targets:
        chair_finished = True
    else:
        chair_finished = chair_targets_has_ev and chair_all_approved

    if is_regular_faculty:
        ret_finished = True
    elif not ret_has_targets:
        ret_finished = True
    elif not ret_targets_has_ev:
        ret_finished = True
    else:
        ret_finished = ret_all_approved

    is_both_approved = chair_finished and ret_finished and (chair_has_targets or ret_has_targets)

    if is_both_approved:
        status_code = 'APPROVED'
        status_label = 'Approved'
    elif ret_finished and not chair_finished:
        status_code = 'WAITING_CHAIR'
        status_label = 'Waiting for Program Chair Approval'
    elif chair_finished and not ret_finished:
        status_code = 'WAITING_RET'
        status_label = 'Waiting for RET Chair Approval'
    else:
        status_code = 'SUBMITTED'
        status_label = 'Evidences Submitted'

    faculty_dict['verification_status_code'] = status_code
    faculty_dict['evidence_status'] = status_label
    faculty_dict['is_both_approved'] = is_both_approved
    faculty_dict['chair_finished'] = chair_finished
    faculty_dict['ret_finished'] = ret_finished
    faculty_dict['is_submitted_to_dean'] = is_submitted_to_dean
    return faculty_dict



