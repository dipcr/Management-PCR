from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.models import *
from app.decorators import role_required

prog_chair_bp = Blueprint('prog_chair', __name__, url_prefix='/prog_chair')


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────

@prog_chair_bp.route('/')
@role_required('PROGRAM_CHAIR')
def prog_chair_dashboard():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        specialization = session.get('specialization')
        if not specialization:
            cursor.execute(
                "SELECT specialization FROM tbl_employee_profiles WHERE emp_id = %s",
                (session.get('user_id'),)
            )
            spec_rows = cursor.fetchall()
            specialization = spec_rows[0][0] if spec_rows else ''
            session['specialization'] = specialization

        if not specialization:
            flash("Your account does not have a designated specialization. Please contact HR/Admin.", "warning")

        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)

        indicators = []
        faculty_count = 0
        pending_drafts = []
        pending_drafts_count = 0
        locked_drafts = []

        targets_saved = False
        if active_term and specialization:
            term_id = active_term['term_id']

            # Phase 1: Target allocation indicators
            indicators = get_chair_indicators(cursor, term_id, specialization)
            faculty_list = get_specialization_faculty(cursor, specialization)
            all_faculty_count = len(faculty_list)
            regular_faculty_list = [f for f in faculty_list if f.get('designation') == 'Regular Faculty']
            regular_faculty_count = len(regular_faculty_list)
            faculty_count = all_faculty_count
            faculty_ids = [f['emp_id'] for f in faculty_list]

            # Check if target allocations are already saved for this term & specialization
            targets_saved = check_chair_targets_saved(cursor, term_id, specialization)

            # Batch: get ALL assigned quantities in ONE query (replaces N+1 loop)
            indicator_ids = [ind['indicator_id'] for ind in indicators]
            assigned_quantities = get_assigned_quantity_batch(cursor, active_term['term_id'], indicator_ids, faculty_ids)

            for ind in indicators:
                alloc_info = assigned_quantities.get(ind['indicator_id'], {})
                if isinstance(alloc_info, dict):
                    assigned_qty = alloc_info.get('assigned_quantity', 0)
                    cust_desc = alloc_info.get('custom_description') or ''
                    t_dead = alloc_info.get('target_deadline') or ''
                    dur_value = alloc_info.get('target_duration_value')
                    dur_unit = alloc_info.get('target_duration_unit')
                    is_auto_desc = alloc_info.get('is_auto_description')
                else:
                    assigned_qty = alloc_info or 0
                    cust_desc = ''
                    t_dead = ''
                    dur_value, dur_unit = None, None
                    is_auto_desc = None

                ind['assigned_per_faculty'] = assigned_qty
                ind['custom_description'] = cust_desc
                ind['target_deadline'] = t_dead
                ind['target_duration_value'] = dur_value
                ind['target_duration_unit'] = dur_unit
                ind['is_auto_description'] = is_auto_desc

                if ind.get('slug') == SLUG_INSTRUCTION:
                    ind['applicable_faculty_count'] = all_faculty_count
                    ind['total_distributed'] = assigned_qty * all_faculty_count
                else:
                    ind['applicable_faculty_count'] = regular_faculty_count
                    ind['total_distributed'] = assigned_qty * regular_faculty_count

            # Phase 2: Commitments — live draft IPCR submissions scoped by specialization
            pending_drafts = get_pending_draft_ipcrs(cursor, specialization, term_id)
            # Enrich each draft with dynamically computed ipcr_status
            from app.models.connection import get_overall_ipcr_status
            for draft in pending_drafts:
                draft['ipcr_status'] = get_overall_ipcr_status(cursor, draft['emp_id'], term_id)
            pending_drafts_count = get_pending_drafts_count(cursor, specialization, term_id)
            
            # Fetch approved & locked IPCRs for the second table
            locked_drafts = get_locked_faculty_ipcrs(cursor, specialization, term_id)

            # get_program_chair_evidence_faculty already excludes every Designated Faculty
            # designation, so everyone here is Regular Faculty -- no further split needed.
            evidence_faculty_list = get_program_chair_evidence_faculty(cursor, specialization, term_id)
            pending_evidence_faculty_list = [f for f in evidence_faculty_list if not f.get('is_both_approved')]
            approved_evidence_faculty_list = [f for f in evidence_faculty_list if f.get('is_both_approved')]
            approved_regular_evidence_list = approved_evidence_faculty_list

        return render_template(
            'prog_chair_dashboard.html',
            active_term=active_term,
            specialization=specialization,
            indicators=indicators,
            faculty_count=all_faculty_count,
            all_faculty_count=all_faculty_count,
            regular_faculty_count=regular_faculty_count,
            targets_saved=targets_saved,
            pending_drafts=pending_drafts,
            pending_drafts_count=pending_drafts_count,
            locked_drafts=locked_drafts,
            evidence_faculty_list=evidence_faculty_list if 'evidence_faculty_list' in locals() else [],
            pending_evidence_faculty_list=pending_evidence_faculty_list if 'pending_evidence_faculty_list' in locals() else [],
            approved_evidence_faculty_list=approved_evidence_faculty_list if 'approved_evidence_faculty_list' in locals() else [],
            approved_regular_evidence_list=approved_regular_evidence_list if 'approved_regular_evidence_list' in locals() else [],
            has_own_ipcr=True
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@prog_chair_bp.route('/submit_to_dean', methods=['POST'])
@role_required('PROGRAM_CHAIR')
def prog_chair_submit_to_dean():
    data = request.get_json(silent=True) or request.form
    emp_id = data.get('emp_id')
    if not emp_id:
        return jsonify({'success': False, 'message': 'Missing faculty emp_id.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models import get_all_terms
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active academic term found.'}), 400

        term_id = active_term['term_id']
        from app.models.prog_chair import submit_evidence_package_to_dean
        success, msg = submit_evidence_package_to_dean(conn, cursor, int(emp_id), term_id)
        if success:
            try:
                from app.services.notification_service import send_evidence_package_to_dean_notification
                send_evidence_package_to_dean_notification(conn, cursor, int(emp_id), int(term_id), request.host_url)
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering evidence package to dean notification: {notif_err}")
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@prog_chair_bp.route('/verify_evidence', methods=['POST'])
@role_required('PROGRAM_CHAIR')
def prog_chair_verify_evidence():
    """AJAX — approve or return a single uploaded evidence file."""
    data = request.get_json(silent=True) or request.form
    evidence_id = data.get('evidence_id')
    status = (data.get('status') or '').strip()
    comment = data.get('comment') or ''
    if not evidence_id:
        return jsonify({'success': False, 'message': 'Missing evidence_id.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.faculty import set_evidence_verification
        success, msg = set_evidence_verification(conn, cursor, int(evidence_id), status, comment)
        if success and status == 'Approved':
            try:
                from app.services.notification_service import check_and_trigger_evidence_approved_notification
                check_and_trigger_evidence_approved_notification(conn, cursor, int(evidence_id), 'Program Chair', request.host_url)
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering evidence approved notification: {notif_err}")
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@prog_chair_bp.route('/faculty_evidence_details/<int:emp_id>')
@role_required('PROGRAM_CHAIR')
def prog_chair_faculty_evidence_details(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term found'}), 400

        term_id = active_term['term_id']

        cursor.execute("SELECT first_name, last_name, academic_rank, designation FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        fac_row = cursor.fetchone()
        if not fac_row:
            return jsonify({'success': False, 'message': 'Faculty member not found'}), 404
        faculty_name = f"{fac_row[0]} {fac_row[1]}"

        from app.models.criteria import is_designated
        from app.models.faculty import get_faculty_committed_targets, get_evidence_by_target
        targets = get_faculty_committed_targets(cursor, emp_id, term_id)
        designated = is_designated(fac_row[3])

        for t in targets:
            cat_name = t.get('category_name', '')
            t['is_ret'] = ('Research' in cat_name) or ('Extension' in cat_name)
            # A designated faculty/chair's Core Functions vs Strategic Priorities & Support
            # Functions split is driven by is_admin_function, not category — the same
            # indicator (e.g. Instruction) can be either depending on whether this is their
            # personal teaching share or their departmental oversight quota. See "My IPCR"
            # (designated_dashboard.html) for the same rule.
            if designated:
                t['is_core'] = not bool(t.get('is_admin_function'))

            # Program Chair now approves all evidence for regular faculty, Research &
            # Extension included.
            t['evidence_list'] = get_evidence_by_target(cursor, t['target_id'])

        return jsonify({
            'success': True,
            'faculty_name': faculty_name,
            'academic_rank': fac_row[2] or '',
            'is_designated': designated,
            'targets': targets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()



# ─────────────────────────────────────────────
# Phase 1: Target allocation
# ─────────────────────────────────────────────

@prog_chair_bp.route('/assign_target', methods=['POST'])
@role_required('PROGRAM_CHAIR')
def assign_chair_target():
    specialization = session.get('specialization')
    term_id = request.form.get('term_id')
    indicator_ids = request.form.getlist('indicator_ids')
    assigned_quantities = request.form.getlist('assigned_quantities')
    custom_descriptions = request.form.getlist('custom_descriptions')
    target_duration_values = request.form.getlist('target_duration_values')
    target_duration_units = request.form.getlist('target_duration_units')
    is_auto_descriptions = request.form.getlist('is_auto_descriptions')

    if not specialization or not term_id or not indicator_ids or not assigned_quantities:
        flash("Missing required data for assignment.", "danger")
        return redirect(url_for('prog_chair.prog_chair_dashboard'))

    if len(indicator_ids) != len(assigned_quantities):
        flash("Mismatch between indicators and quantities.", "danger")
        return redirect(url_for('prog_chair.prog_chair_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Constraint check: prevent re-saving if targets are already finalized
        if check_chair_targets_saved(cursor, int(term_id), specialization):
            flash("Target allocations for this term have already been finalized and cannot be modified.", "warning")
            return redirect(url_for('prog_chair.prog_chair_dashboard'))

        faculty_list = get_specialization_faculty(cursor, specialization)
        faculty_ids = [f['emp_id'] for f in faculty_list]

        allocations = []
        for idx, (ind_id, qty) in enumerate(zip(indicator_ids, assigned_quantities)):
            try:
                qty_val = int(qty)
                if qty_val > 0:
                    # Blank is valid here — save_chair_allocations_batch auto-generates the
                    # standard description from the indicator/quantity/duration when this is
                    # None, rather than rejecting the submission.
                    c_desc = custom_descriptions[idx].strip() if idx < len(custom_descriptions) and custom_descriptions[idx] else None
                    # Explicit auto/customized flag from wireAutoDescription (base.html) — see
                    # Decision 1 in target_desc.md. Absent (e.g. JS disabled) falls back to
                    # inferring from blank-ness in save_chair_allocations_batch.
                    is_auto_flag = is_auto_descriptions[idx] if idx < len(is_auto_descriptions) else None

                    raw_value = target_duration_values[idx] if idx < len(target_duration_values) else None
                    raw_unit = target_duration_units[idx] if idx < len(target_duration_units) else None
                    dur_value, dur_unit, t_dead = parse_duration_fields(
                        {'v': raw_value, 'u': raw_unit}, 'v', 'u')

                    if not dur_value or dur_value <= 0:
                        flash("All allocated targets must have a valid deadline (target duration) specified.", "danger")
                        return redirect(url_for('prog_chair.prog_chair_dashboard'))

                    allocations.append((int(ind_id), qty_val, c_desc, t_dead, dur_value, dur_unit, is_auto_flag == '1'))
                else:
                    allocations.append((int(ind_id), 0, None, None, None, None))
            except ValueError:
                continue

        if not any(a[1] > 0 for a in allocations):
            flash("No valid allocations to save.", "warning")
            return redirect(url_for('prog_chair.prog_chair_dashboard'))

        success, msg = save_chair_allocations_batch(
            conn, cursor, int(term_id), allocations, faculty_ids
        )
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving allocations: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('prog_chair.prog_chair_dashboard'))


# ─────────────────────────────────────────────
# Phase 2: IPCR Review — AJAX fetch for modal
# ─────────────────────────────────────────────

@prog_chair_bp.route('/review_ipcr/<int:emp_id>')
@role_required('PROGRAM_CHAIR')
def review_ipcr(emp_id):
    """
    AJAX endpoint — returns JSON payload used to populate the review modal.
    Creates a tbl_ipcr_chair_review record (and pre-populates items) if one
    doesn't exist yet for this faculty + active term.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        chair_emp_id = session.get('user_id')
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)

        if not active_term:
            return jsonify({'error': 'No active term found.'}), 400

        term_id = active_term['term_id']

        # Check overall IPCR status for sequential tracking guardrails
        from app.models.connection import get_overall_ipcr_status
        ipcr_status = get_overall_ipcr_status(cursor, emp_id, term_id)

        if ipcr_status not in ('waiting_for_program_chair_review', 'approved_by_program_chair', 'completed'):
            return jsonify({'error': 'RET Chair approval is required before Program Chair verification.'}), 403

        # Fetch or create the review record
        review_id = get_or_create_chair_review(conn, cursor, emp_id, term_id, chair_emp_id)

        # Fetch review items with indicator details
        items = get_review_items(cursor, review_id)

        # Fetch current overall status and remarks
        cursor.execute(
            "SELECT overall_status, overall_remarks FROM tbl_ipcr_chair_review WHERE review_id = %s",
            (review_id,)
        )
        review_row = cursor.fetchone()
        overall_status = review_row[0] if review_row else 'Pending'
        overall_remarks = review_row[1] if review_row else ''

        # Check draft status to see if it is Waiting for Approval
        cursor.execute("""
            SELECT MAX(review_status) FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            WHERE dt.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))
        draft_status_row = cursor.fetchone()
        draft_status = draft_status_row[0] if draft_status_row else 'Pending Review'

        # If Pending overall review but resubmitted, elevate overall_status to Waiting for Approval
        if overall_status == 'Pending' and draft_status == 'Waiting for Approval':
            overall_status = 'Waiting for Approval'

        # Check if locked
        cursor.execute(
            """
            SELECT COUNT(*) FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
            """,
            (emp_id, term_id)
        )
        is_locked = cursor.fetchone()[0] > 0
        if is_locked:
            overall_status = 'Locked'

        # Fetch faculty name for the modal header
        cursor.execute(
            "SELECT CONCAT(first_name, ' ', last_name), academic_rank FROM tbl_employee_profiles WHERE emp_id = %s",
            (emp_id,)
        )
        fac_row = cursor.fetchone()
        faculty_name = fac_row[0] if fac_row else 'Unknown'
        academic_rank = fac_row[1] if fac_row else ''

        # Serialize datetime fields or load committed/approved targets
        serializable_items = []
        if is_locked:
            cursor.execute("""
                SELECT 
                    ct.target_id AS item_id,
                    0 AS draft_id,
                    ct.indicator_id,
                    COALESCE(ct.target_description, mi.indicator_description) AS indicator_description,
                    ct.target_deadline,
                    tc.category_name,
                    COALESCE(
                        CASE WHEN tc.review_lane = 'CHAIR' AND tc.is_core = 1 THEN ri.original_quantity ELSE NULL END,
                        CASE WHEN tc.review_lane = 'RET' THEN rri.original_quantity ELSE NULL END,
                        ct.assigned_quantity
                    ) AS original_quantity,
                    ct.assigned_quantity AS reviewed_quantity,
                    COALESCE(ri.item_remarks, rri.item_remarks, '') AS item_remarks,
                    'Locked' AS draft_status
                FROM tbl_committed_targets ct
                JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                LEFT JOIN tbl_ipcr_chair_review cr ON cr.emp_id = ct.emp_id AND cr.term_id = mi.term_id
                LEFT JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.indicator_id = ct.indicator_id
                LEFT JOIN tbl_ipcr_ret_review rr ON rr.emp_id = ct.emp_id AND rr.term_id = mi.term_id
                LEFT JOIN tbl_ipcr_ret_review_items rri ON rri.review_id = rr.review_id AND rri.indicator_id = ct.indicator_id
                WHERE ct.emp_id = %s AND mi.term_id = %s
            """, (emp_id, term_id))
            rows = cursor.fetchall()
            for row in rows:
                serializable_items.append({
                    'item_id': row[0],
                    'draft_id': row[1],
                    'indicator_id': row[2],
                    'indicator_description': row[3],
                    'target_deadline': row[4] or '',
                    'category_name': row[5],
                    'original_quantity': max(0, row[6]) if row[6] is not None else 0,
                    'reviewed_quantity': row[7],
                    'item_remarks': row[8],
                    'draft_status': row[9],
                })
        elif overall_status == 'Approved':
            cursor.execute("""
                SELECT 
                    dt.draft_id AS item_id,
                    dt.draft_id,
                    dt.indicator_id,
                    COALESCE(dt.target_description, mi.indicator_description) AS indicator_description,
                    dt.target_deadline,
                    tc.category_name,
                    COALESCE(
                        CASE WHEN tc.review_lane = 'CHAIR' AND tc.is_core = 1 THEN ri.original_quantity ELSE NULL END,
                        CASE WHEN tc.review_lane = 'RET' THEN rri.original_quantity ELSE NULL END,
                        dt.proposed_quantity
                    ) AS original_quantity,
                    COALESCE(
                        CASE WHEN tc.review_lane = 'CHAIR' AND tc.is_core = 1 THEN ri.reviewed_quantity ELSE NULL END,
                        CASE WHEN tc.review_lane = 'RET' THEN rri.reviewed_quantity ELSE NULL END,
                        dt.proposed_quantity
                    ) AS reviewed_quantity,
                    COALESCE(ri.item_remarks, rri.item_remarks, '') AS item_remarks,
                    dt.review_status AS draft_status
                FROM tbl_draft_targets dt
                JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                LEFT JOIN tbl_ipcr_chair_review cr ON cr.emp_id = dt.emp_id AND cr.term_id = mi.term_id
                LEFT JOIN tbl_ipcr_chair_review_items ri ON ri.review_id = cr.review_id AND ri.draft_id = dt.draft_id
                LEFT JOIN tbl_ipcr_ret_review rr ON rr.emp_id = dt.emp_id AND rr.term_id = mi.term_id
                LEFT JOIN tbl_ipcr_ret_review_items rri ON rri.review_id = rr.review_id AND rri.indicator_id = dt.indicator_id
                WHERE dt.emp_id = %s AND mi.term_id = %s
                  AND (
                      ((tc.review_lane = 'CHAIR' AND tc.is_core = 1) AND dt.proposed_quantity > 0)
                      OR (tc.review_lane = 'RET' AND rri.reviewed_quantity > 0)
                  )
            """, (emp_id, term_id))
            rows = cursor.fetchall()
            for row in rows:
                serializable_items.append({
                    'item_id': row[0],
                    'draft_id': row[1],
                    'indicator_id': row[2],
                    'indicator_description': row[3],
                    'target_deadline': row[4] or '',
                    'category_name': row[5],
                    'original_quantity': max(0, row[6]) if row[6] is not None else 0,
                    'reviewed_quantity': row[7],
                    'item_remarks': row[8],
                    'draft_status': row[9],
                })
        else:
            for item in items:
                serializable_items.append({
                    'item_id': item['item_id'],
                    'draft_id': item['draft_id'],
                    'indicator_id': item['indicator_id'],
                    'indicator_description': item['indicator_description'],
                    'target_deadline': item.get('target_deadline') or '',
                    'category_name': item['category_name'],
                    'original_quantity': max(0, item['original_quantity']) if item['original_quantity'] is not None else 0,
                    'reviewed_quantity': item['reviewed_quantity'],
                    'item_remarks': item['item_remarks'] or '',
                    'draft_status': item['draft_status'],
                })

        return jsonify({
            'review_id': review_id,
            'emp_id': emp_id,
            'faculty_name': faculty_name,
            'academic_rank': academic_rank,
            'overall_status': overall_status,
            'overall_remarks': overall_remarks or '',
            'items': serializable_items,
        })

    except Exception as e:
        import traceback
        with open("error_log.txt", "w") as f:
            traceback.print_exc(file=f)
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────────
# Phase 2: Edit a single review item
# ─────────────────────────────────────────────

@prog_chair_bp.route('/edit_review_item', methods=['POST'])
@role_required('PROGRAM_CHAIR')
def edit_review_item():
    """
    Saves an edited quantity and optional remark for one review item row.
    Returns JSON so the modal can update inline without a page reload.
    """
    data = request.get_json()
    item_id = data.get('item_id')
    reviewed_quantity = data.get('reviewed_quantity')
    item_remarks = data.get('item_remarks', '').strip()

    if item_id is None or reviewed_quantity is None:
        return jsonify({'success': False, 'message': 'Missing item_id or reviewed_quantity.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if locked
        cursor.execute(
            "SELECT review_id FROM tbl_ipcr_chair_review_items WHERE item_id = %s",
            (item_id,)
        )
        review_row = cursor.fetchone()
        if review_row:
            review_id = review_row[0]
            cursor.execute(
                "SELECT emp_id, term_id FROM tbl_ipcr_chair_review WHERE review_id = %s",
                (review_id,)
            )
            row = cursor.fetchone()
            if row:
                emp_id, term_id = row
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM tbl_committed_targets ct
                    JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
                    WHERE ct.emp_id = %s AND mi.term_id = %s
                    """,
                    (emp_id, term_id)
                )
                if cursor.fetchone()[0] > 0:
                    return jsonify({'success': False, 'message': 'This IPCR is locked and cannot be edited.'}), 403

        success, msg = update_review_item(conn, cursor, int(item_id), int(reviewed_quantity), item_remarks)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────────
# Phase 2: Approve or Reject a draft IPCR
# ─────────────────────────────────────────────

@prog_chair_bp.route('/decide_ipcr', methods=['POST'])
@role_required('PROGRAM_CHAIR')
def decide_ipcr():
    """
    Approves or rejects the full draft IPCR for a faculty member.
    On rejection, the faculty's tbl_draft_targets rows are set to 'Returned'
    so they can re-submit after making corrections.
    """
    import json
    review_id = request.form.get('review_id')
    action = request.form.get('action')           # 'approve' or 'reject'
    overall_remarks = request.form.get('overall_remarks', '').strip()
    items_json = request.form.get('items_json')

    if not review_id or action not in ('approve', 'reject'):
        flash("Invalid decision parameters.", "danger")
        return redirect(url_for('prog_chair.prog_chair_dashboard'))

    if action == 'reject' and not overall_remarks:
        flash("Remarks / Reason is required when returning the IPCR to faculty.", "danger")
        return redirect(url_for('prog_chair.prog_chair_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if locked
        cursor.execute(
            "SELECT emp_id, term_id FROM tbl_ipcr_chair_review WHERE review_id = %s",
            (review_id,)
        )
        row = cursor.fetchone()
        if row:
            emp_id, term_id = row

            # Check overall IPCR status for sequential tracking guardrails
            from app.models.connection import get_overall_ipcr_status
            ipcr_status = get_overall_ipcr_status(cursor, emp_id, term_id)

            if ipcr_status not in ('waiting_for_program_chair_review', 'approved_by_program_chair', 'completed'):
                flash("RET Chair approval is required before Program Chair verification.", "danger")
                return redirect(url_for('prog_chair.prog_chair_dashboard'))

            cursor.execute(
                """
                SELECT COUNT(*) FROM tbl_committed_targets ct
                JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
                WHERE ct.emp_id = %s AND mi.term_id = %s
                """,
                (emp_id, term_id)
            )
            if cursor.fetchone()[0] > 0:
                flash("This IPCR is locked and cannot be modified.", "warning")
                return redirect(url_for('prog_chair.prog_chair_dashboard'))

        # If items are submitted inline, save them first inside the same transaction
        if items_json:
            try:
                items = json.loads(items_json)
                from app.models.prog_chair import save_chair_review_items
                save_success, save_msg = save_chair_review_items(cursor, conn, int(review_id), items)
                if not save_success:
                    flash(f"Failed to save targets: {save_msg}", "danger")
                    return redirect(url_for('prog_chair.prog_chair_dashboard'))
            except Exception as json_err:
                flash(f"Invalid target items format: {str(json_err)}", "danger")
                return redirect(url_for('prog_chair.prog_chair_dashboard'))

        success, msg = decide_chair_review(conn, cursor, int(review_id), action, overall_remarks)
        if success and row:
            if action == 'approve':
                try:
                    from app.services.notification_service import send_chair_approval_notification
                    send_chair_approval_notification(conn, cursor, int(emp_id), int(term_id))
                except Exception as notif_err:
                    import logging
                    logging.getLogger(__name__).error(f"Error triggering Chair approval notification: {notif_err}")
            elif action == 'reject':
                try:
                    from app.services.notification_service import send_return_notification
                    send_return_notification(conn, cursor, "Program Chair", int(review_id), int(emp_id), int(term_id), overall_remarks)
                except Exception as notif_err:
                    import logging
                    logging.getLogger(__name__).error(f"Error triggering Return notification: {notif_err}")

        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error processing decision: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('prog_chair.prog_chair_dashboard'))



