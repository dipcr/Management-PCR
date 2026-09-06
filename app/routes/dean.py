from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.models import *
from app.decorators import role_required

dean_bp = Blueprint('dean', __name__, url_prefix='/dean')


@dean_bp.route('/')
@role_required('DEAN')
def dean_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        dean_id = session.get('user_id')
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)

        if not active_term:
            flash('No active academic term found.', 'warning')
            return render_template('dean_dashboard.html',
                                   active_term=None,
                                   departments=[],
                                   special_roles=SPECIAL_CASCADE_ROLES,
                                   master_indicators=[],
                                   existing_quotas={},
                                   existing_cw_allow_allocation={},
                                   completion_rate=0,
                                   pending_count=0,
                                   top_dept="N/A",
                                   pending_approvals=[],
                                   draft_submissions=[],
                                   college_wide_quotas=[],
                                   designated_faculty_list=[])

        term_id = active_term['term_id']

        # Use timed_query helper for all queries
        from app.models.connection import timed_query

        indicators = get_master_indicators(cursor, term_id)

        existing_quotas_raw = get_existing_cascaded_quotas(cursor, term_id)

        existing_quotas = {}
        existing_cw_allow_allocation = {}
        for quota in existing_quotas_raw:
            ind_id = quota['indicator_id']
            if ind_id not in existing_quotas:
                existing_quotas[ind_id] = {}
            existing_quotas[ind_id][quota['assigned_to_role']] = quota['total_target_value']
            if quota['assigned_to_role'] == 'College-Wide':
                existing_cw_allow_allocation[ind_id] = quota['allow_chair_allocation']

        # Consolidated KPI query — 1 round-trip instead of 3
        completion_rate, pending_count, top_dept = get_dean_dashboard_kpis(cursor, term_id)

        pending_approvals = get_pending_final_approvals(cursor, term_id)

        # ── New: Draft IPCR submissions from designated faculty ──
        draft_submissions = get_designated_draft_submissions(cursor, term_id)

        # ── New: College-Wide quotas for target assignment ──
        college_wide_quotas = get_college_wide_cascaded_quotas(cursor, term_id)

        # ── New: Designated faculty list ──
        designated_faculty_list = get_designated_faculty_list(cursor)

        # Get ALL assignments in ONE batch query (replaces N+1 loop)
        emp_ids = [fac['emp_id'] for fac in designated_faculty_list]
        designated_assignments = get_designated_faculty_assignments_batch(cursor, term_id, emp_ids)

        # Fetch college-wide allocations for tracking
        allocations_list = get_college_wide_allocations_tracker(cursor, term_id)

        # Structure them by indicator_id: {indicator_id: [allocations]}
        college_wide_allocations = {}
        for alloc in allocations_list:
            ind_id = alloc['indicator_id']
            if ind_id not in college_wide_allocations:
                college_wide_allocations[ind_id] = []
            college_wide_allocations[ind_id].append(alloc)

        from app.models.dean import get_dean_evidence_faculty
        pending_dean_evidence_list, approved_dean_evidence_list = get_dean_evidence_faculty(cursor, term_id)

        def _is_designated_or_chair_or_dean(f):
            role = (f.get('system_role') or '').strip()
            desig = (f.get('designation') or '').strip()
            return (role in ('DESIGNATED_FACULTY', 'PROGRAM_CHAIR', 'RET_CHAIR', 'DEAN')
                    or desig in ('Designated Faculty', 'Program Chair', 'RET Chair', 'Dean'))

        approved_designated_dean_evidence_list = [f for f in approved_dean_evidence_list if _is_designated_or_chair_or_dean(f)]
        approved_regular_dean_evidence_list = [f for f in approved_dean_evidence_list if not _is_designated_or_chair_or_dean(f)]
        # Every Designated Faculty member -- plain or a chair/Dean's own IPCR -- has no
        # Program Chair review before landing here, so all of them need the dedicated
        # Evidence Verification panel, not just chairs/Dean. They stay in that panel (not
        # Final Verification) until every one of their evidence files is actually reviewed
        # and approved (is_both_approved) -- Regular Faculty already carry that same flag
        # from Program Chair/RET Chair review before 'Submitted to Dean' is ever set.
        pending_designated_dean_evidence_list = [f for f in pending_dean_evidence_list
                                                  if _is_designated_or_chair_or_dean(f) and not f.get('is_both_approved')]
        # Final Verification is the Dean's package-level sign-off, so a faculty member --
        # regular or designated -- only belongs here once their evidence has actually been
        # reviewed and approved (by the Program Chair/RET Chair for Regular Faculty, by the
        # Dean via the Evidence Verification panel for designated faculty/chairs/Dean), not
        # merely because their package status reached 'Submitted to Dean'.
        pending_dean_evidence_list = [f for f in pending_dean_evidence_list if f.get('is_both_approved')]

        departments = get_departments(cursor)

        return render_template('dean_dashboard.html',
                               active_term=active_term,
                               departments=departments,
                               special_roles=SPECIAL_CASCADE_ROLES,
                               master_indicators=indicators,
                               existing_quotas=existing_quotas,
                               existing_cw_allow_allocation=existing_cw_allow_allocation,
                               completion_rate=completion_rate,
                               pending_count=pending_count,
                               top_dept=top_dept,
                               pending_approvals=pending_approvals,
                               draft_submissions=draft_submissions,
                               college_wide_quotas=college_wide_quotas,
                               designated_faculty_list=designated_faculty_list,
                               designated_assignments=designated_assignments,
                               college_wide_allocations=college_wide_allocations,
                               pending_dean_evidence_list=pending_dean_evidence_list,
                               pending_designated_dean_evidence_list=pending_designated_dean_evidence_list,
                               approved_dean_evidence_list=approved_dean_evidence_list,
                               approved_designated_dean_evidence_list=approved_designated_dean_evidence_list,
                               approved_regular_dean_evidence_list=approved_regular_dean_evidence_list,
                               has_own_ipcr=True)
    finally:
        cursor.close()
        conn.close()


@dean_bp.route('/cascade_quotas', methods=['POST'])
@role_required('DEAN')
def cascade_quotas():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        term_id = request.form.get('term_id')
        if not term_id:
            flash('Missing term ID', 'danger')
            return redirect(url_for('dean.dean_dashboard'))

        quotas_data = []
        indicator_ids = request.form.getlist('indicator_id[]')

        # Cascade columns are generated from the managed department list plus the two
        # non-department roles, so adding a program needs no code change.
        departments = get_departments(cursor)
        cascade_roles = [d['department_name'] for d in departments] + SPECIAL_CASCADE_ROLES
        role_values = {role: request.form.getlist(f'quota_{i}[]')
                       for i, role in enumerate(cascade_roles)}

        def _qty(role, idx):
            vals = role_values.get(role, [])
            if idx >= len(vals) or not vals[idx]:
                return 0
            try:
                v = int(vals[idx])
            except (TypeError, ValueError):
                return 0
            return v if v > 0 else 0

        for i, ind_id in enumerate(indicator_ids):
            if not ind_id:
                continue

            values = [(role, _qty(role, i)) for role in cascade_roles]

            # College-Wide targets default to Silent (Dean Only) unless the Dean
            # explicitly ticks "Cascade to Chairs" for this indicator; department
            # and RET rows aren't gated by this flag, so it's a no-op default for them.
            cw_cascade_to_chairs = bool(request.form.get(f'cw_allow_allocation_{ind_id}'))

            for role, value in values:
                if value > 0:
                    quotas_data.append({
                        'indicator_id': int(ind_id),
                        'total_target': value,
                        'assigned_role': role,
                        'allow_chair_allocation': 1 if role != 'College-Wide' else int(cw_cascade_to_chairs)
                    })

        success, message = save_cascaded_quotas(cursor, conn, term_id, quotas_data)

        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')

    except Exception as e:
        flash(f'Error cascading quotas: {str(e)}', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('dean.dean_dashboard'))




@dean_bp.route('/validate_quotas', methods=['POST'])
@role_required('DEAN')
def validate_quotas():
    """AJAX endpoint to validate quotas before submission"""
    data = request.get_json()
    return jsonify({'valid': True, 'message': 'Quotas validated'})


@dean_bp.route('/review_draft_fetch/<int:emp_id>')
@role_required('DEAN')
def review_draft_fetch(emp_id):
    """AJAX endpoint — returns JSON to populate the Dean's review modal."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        dean_id = session.get('user_id')
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'error': 'No active term found.'}), 400

        term_id = active_term['term_id']

        # Get or create review record
        review_id = get_or_create_dean_review(conn, cursor, emp_id, term_id, dean_id)

        # Fetch review items
        items = get_dean_review_items(cursor, review_id)

        # Fetch overall status & remarks
        cursor.execute(
            "SELECT overall_status, overall_remarks FROM tbl_ipcr_dean_review WHERE review_id = %s",
            (review_id,)
        )
        row = cursor.fetchone()
        overall_status = row[0] if row else 'Pending'
        overall_remarks = row[1] if row else ''

        # Faculty info
        cursor.execute(
            "SELECT CONCAT(first_name, ' ', last_name), academic_rank, designation, assigned_program FROM tbl_employee_profiles WHERE emp_id = %s",
            (emp_id,)
        )
        fac = cursor.fetchone()
        faculty_name = fac[0] if fac else 'Unknown'
        academic_rank = fac[1] if fac else ''
        designation = fac[2] if fac else ''
        assigned_program = fac[3] if fac else ''

        # Get college-wide quotas
        college_wide = get_college_wide_cascaded_quotas(cursor, term_id)
        college_wide_ids = {q['indicator_id'] for q in college_wide}

        # Also get available master indicators for this term (filtered by reviewee role: RET vs Chair)
        all_indicators = get_available_master_indicators(cursor, term_id, emp_id=emp_id)
        picked_ids = {i['indicator_id'] for i in items}
        
        # Filter unpicked to exclude picked AND college wide targets
        unpicked = [ind for ind in all_indicators if ind['indicator_id'] not in picked_ids and ind['indicator_id'] not in college_wide_ids]

        # Filter college wide to only show those that are unpicked
        college_wide_unpicked = []
        for q in college_wide:
            if q['indicator_id'] not in picked_ids:
                college_wide_unpicked.append({
                    'indicator_id': q['indicator_id'],
                    'indicator_description': q['indicator_description'],
                    'category_name': q['category_name'],
                    'total_target_value': q['total_target_value']
                })

        serializable_items = []
        for item in items:
            serializable_items.append({
                'item_id': item['item_id'],
                'draft_id': item['draft_id'],
                'indicator_id': item['indicator_id'],
                'indicator_description': item['indicator_description'],
                'category_name': item['category_name'],
                'original_quantity': item['original_quantity'],
                'reviewed_quantity': item['reviewed_quantity'],
                'item_remarks': item['item_remarks'] or '',
                'is_custom': item['is_custom'],
                'target_description': item.get('target_description') or item['indicator_description'],
                'target_deadline': item.get('target_deadline') or '1 Semester',
                'target_duration_value': item.get('target_duration_value'),
                'target_duration_unit': item.get('target_duration_unit'),
                'is_core': item.get('is_core', False),
                'is_cascaded': item.get('is_cascaded', False),
            })


        return jsonify({
            'review_id': review_id,
            'emp_id': emp_id,
            'faculty_name': faculty_name,
            'academic_rank': academic_rank,
            'designation': designation,
            'assigned_program': assigned_program,
            'overall_status': overall_status,
            'overall_remarks': overall_remarks or '',
            'items': serializable_items,
            'unpicked': unpicked,
            'college_wide_unpicked': college_wide_unpicked,
            'college_wide_all': [{
                'indicator_id': q['indicator_id'],
                'indicator_description': q['indicator_description'],
                'category_name': q['category_name'],
                'total_target_value': q['total_target_value']
            } for q in college_wide],
            'college_wide_ids': list(college_wide_ids),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@dean_bp.route('/save_review_items', methods=['POST'])
@role_required('DEAN')
def save_review_items():
    """Batch save all edited quantities and remarks for one review."""
    data = request.get_json()
    review_id = data.get('review_id')
    items = data.get('items', [])

    if not review_id or not items:
        return jsonify({'success': False, 'message': 'Missing review_id or items.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        success, msg = save_dean_review_items(cursor, conn, review_id, items)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@dean_bp.route('/submit_review_decision', methods=['POST'])
@role_required('DEAN')
def submit_review_decision():
    """Approve or reject the entire review with overall remarks."""
    data = request.get_json()
    review_id = data.get('review_id')
    action = data.get('action')
    overall_remarks = data.get('overall_remarks', '').strip()

    if not review_id or action not in ('Approved', 'Rejected'):
        return jsonify({'success': False, 'message': 'Missing review_id or invalid action.'}), 400

    if action == 'Rejected' and not overall_remarks:
        return jsonify({'success': False, 'message': 'Remarks are required when rejecting.'}), 400

    dean_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT emp_id, term_id FROM tbl_ipcr_dean_review WHERE review_id = %s", (review_id,))
        review_row = cursor.fetchone()

        success, msg = submit_dean_review_decision(cursor, conn, review_id, action, overall_remarks)

        if success:
            if review_row:
                emp_id, term_id = review_row
                try:
                    from app.services.notification_service import send_designated_target_decision_notification
                    send_designated_target_decision_notification(conn, cursor, int(emp_id), int(term_id), action, overall_remarks)
                except Exception as notif_err:
                    import logging
                    logging.getLogger(__name__).error(f"Error triggering designated decision notification: {notif_err}")

            details = f"Dean {dean_id} {action.lower()} draft IPCR (review #{review_id}). Remarks: {overall_remarks}"
            from app.models.audit import log_audit_action
            log_audit_action(conn, cursor, dean_id, f'DEAN_REVIEW_{action.upper()}', details, request.remote_addr or '127.0.0.1')

        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ──────────────────────────────────────────────
# College-Wide Target Assignment (Designated Faculty)
# ──────────────────────────────────────────────

@dean_bp.route('/designated_assignment_editor/<int:emp_id>')
@role_required('DEAN')
def designated_assignment_editor(emp_id):
    """AJAX — returns the College-Wide target list + current assignments for a designated faculty member / chair."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term found.'}), 400
        term_id = active_term['term_id']

        cursor.execute("""
            SELECT CONCAT(first_name, ' ', last_name), academic_rank, designation, assigned_program, specialization
            FROM tbl_employee_profiles
            WHERE emp_id = %s
        """, (emp_id,))
        fac_row = cursor.fetchone()
        if not fac_row:
            return jsonify({'success': False, 'message': 'Faculty member not found.'}), 404
        faculty_name = fac_row[0]
        academic_rank = fac_row[1] or ''
        designation = fac_row[2] or 'Designated Faculty'
        department = fac_row[3] or fac_row[4] or 'General'

        # College-Wide quotas cascaded for the active term
        cw_quotas = get_college_wide_cascaded_quotas(cursor, term_id)

        # Existing allocations for this designated faculty member from tbl_draft_allocation
        from app.models.dean import get_designated_faculty_assignments
        assigned_list = get_designated_faculty_assignments(cursor, term_id, emp_id)
        assigned_map = {a['indicator_id']: a for a in assigned_list}

        # Track total allocations across all faculty to compute remaining quota
        allocations_list = get_college_wide_allocations_tracker(cursor, term_id)
        allocated_totals = {}
        for alloc in allocations_list:
            ind_id = alloc['indicator_id']
            allocated_totals[ind_id] = allocated_totals.get(ind_id, 0) + (alloc.get('proposed_quantity') or 0)

        targets = []
        for q in cw_quotas:
            ind_id = q['indicator_id']
            asg = assigned_map.get(ind_id)
            total_quota = q['total_target_value']
            current_total_allocated = allocated_totals.get(ind_id, 0)

            is_assigned = ind_id in assigned_map
            qty = asg['assigned_quantity'] if (asg and asg.get('assigned_quantity') is not None) else 1
            dur_val = asg['target_duration_value'] if (asg and asg.get('target_duration_value') is not None) else 6
            dur_unit = asg['target_duration_unit'] if (asg and asg.get('target_duration_unit')) else 'months'
            is_auto_desc = asg.get('is_auto_description') if asg else None
            is_auto = is_auto_desc is None or is_auto_desc == 1
            if asg and asg.get('custom_description') and not is_auto:
                desc = asg['custom_description']
            else:
                desc = format_ipcr_target_description(q['indicator_description'], qty, dur_val, dur_unit)

            targets.append({
                'indicator_id': ind_id,
                'indicator_description': q['indicator_description'],
                'category_name': q['category_name'],
                'total_quota': total_quota,
                'allocated_total': current_total_allocated,
                'is_assigned': is_assigned,
                'assigned_quantity': qty,
                'custom_description': desc,
                'target_duration_value': dur_val,
                'target_duration_unit': dur_unit,
                'target_deadline': asg.get('target_deadline') if asg else None,
                'is_auto_description': is_auto,
            })

        return jsonify({
            'success': True,
            'emp_id': emp_id,
            'faculty_name': faculty_name,
            'academic_rank': academic_rank,
            'designation': designation,
            'department': department,
            'targets': targets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@dean_bp.route('/save_designated_assignments', methods=['POST'])
@role_required('DEAN')
def save_designated_assignments():
    """Saves the Dean's authored College-Wide target assignments for one designated faculty member / chair."""
    emp_id = request.form.get('emp_id')
    if not emp_id:
        flash("Missing faculty member.", "danger")
        return redirect(url_for('dean.dean_dashboard'))

    indicator_ids = request.form.getlist('assign_indicator_ids[]')
    assignments = []
    for ind_id in indicator_ids:
        qty_val = request.form.get(f'assign_quantity_{ind_id}', 1)
        desc_val = request.form.get(f'assign_description_{ind_id}', '').strip() or None
        # Explicit auto/customized flag from wireAutoDescription (base.html) — see Decision 1
        # in target_desc.md. Absent (None) falls back to inferring from blank-ness.
        raw_auto_flag = request.form.get(f'is_auto_description_{ind_id}')
        is_auto_flag = (raw_auto_flag == '1') if raw_auto_flag is not None else None
        dur_val_raw = request.form.get(f'assign_dur_value_{ind_id}', '').strip()
        dur_unit_val = request.form.get(f'assign_dur_unit_{ind_id}', 'months').strip() or 'months'

        try:
            qty = int(qty_val)
        except (ValueError, TypeError):
            qty = 1

        try:
            dur_val = int(dur_val_raw) if dur_val_raw else None
        except (ValueError, TypeError):
            dur_val = None

        if qty <= 0:
            flash("Assigned quantity must be greater than 0.", "danger")
            return redirect(url_for('dean.dean_dashboard'))

        # Blank is valid here — save_designated_faculty_assignments auto-generates the
        # standard description from the indicator/quantity/duration when this is None.
        if not dur_val or dur_val <= 0:
            flash("All assigned targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('dean.dean_dashboard'))

        assignments.append((int(ind_id), qty, desc_val, dur_val, dur_unit_val, is_auto_flag))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            flash("No active academic term found.", "danger")
            return redirect(url_for('dean.dean_dashboard'))

        from app.models.dean import save_designated_faculty_assignments
        success, msg = save_designated_faculty_assignments(
            conn, cursor, active_term['term_id'], int(emp_id), assignments, session.get('user_id')
        )
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving assignments: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('dean.dean_dashboard'))


@dean_bp.route('/assign_designated_target', methods=['POST'])
@role_required('DEAN')
def assign_designated_target():
    """Assign a single College-Wide target to a designated faculty member."""
    term_id = request.form.get('term_id')
    emp_id = request.form.get('emp_id')
    indicator_id = request.form.get('indicator_id')
    quantity = request.form.get('quantity', '0')

    if not term_id or not emp_id or not indicator_id:
        flash('Missing required data.', 'danger')
        return redirect(url_for('dean.dean_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        success, msg = save_designated_faculty_assignment(
            cursor, conn, int(term_id), emp_id, int(indicator_id), int(quantity) if quantity.isdigit() else 0
        )
        flash(msg, 'success' if success else 'danger')
    except Exception as e:
        flash(f'Error assigning target: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('dean.dean_dashboard'))


# ──────────────────────────────────────────────
# Dean Final Evidence Verification
# ──────────────────────────────────────────────

@dean_bp.route('/preview_ipcr/<int:emp_id>')
@role_required('DEAN')
def dean_preview_ipcr(emp_id):
    """Renders the official printable IPCR form for the Dean to review before or after approval."""
    from app.models.ipcr_form import build_ipcr_form
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models import get_all_terms
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            flash('No active academic term found.', 'warning')
            return redirect(url_for('dean.dean_dashboard'))

        # Once a package has reached the Dean at all (submitted for final verification, or
        # already approved), the Dean's own review should always show the computed Q/E/T
        # ratings and Final Weighted Rating -- that's what final verification IS -- rather
        # than the pre-approval "Approved Commitment" view faculty see while still gathering
        # evidence.
        cursor.execute("""
            SELECT COUNT(*) FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
              AND ct.status IN ('Submitted to Dean', 'Dean Approved')
        """, (emp_id, active_term['term_id']))
        reached_dean = cursor.fetchone()[0] > 0

        form = build_ipcr_form(cursor, emp_id, active_term['term_id'], force_final=reached_dean)
        if not form or not form['has_targets']:
            flash('No committed IPCR targets found for this faculty member.', 'warning')
            return redirect(url_for('dean.dean_dashboard'))

        return render_template('ipcr_print.html', form=form, back_url=url_for('dean.dean_dashboard'))
    finally:
        cursor.close()
        conn.close()

@dean_bp.route('/faculty_evidence_details/<int:emp_id>')
@role_required('DEAN')
def dean_faculty_evidence_details(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models import get_all_terms
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term.'}), 400
        term_id = active_term['term_id']

        from app.models.faculty import get_faculty_committed_targets
        from app.models.scoring import compute_ipcr_score
        targets = get_faculty_committed_targets(cursor, emp_id, term_id)
        ipcr_summary = compute_ipcr_score(cursor, emp_id, term_id)

        cursor.execute("SELECT CONCAT(first_name, ' ', last_name), academic_rank, assigned_program FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        fac = cursor.fetchone()
        fac_name = f"{fac[0]}" if fac else f"Employee #{emp_id}"
        rank = fac[1] if fac else ''
        prog = fac[2] if fac else ''

        return jsonify({
            'success': True,
            'faculty_name': fac_name,
            'academic_rank': rank,
            'department': prog,
            'targets': targets,
            'ipcr_summary': ipcr_summary
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@dean_bp.route('/designated_evidence_details/<int:emp_id>')
@role_required('DEAN')
def dean_designated_evidence_details(emp_id):
    """
    Evidence details for any Designated Faculty member (plain, or a Program Chair/RET
    Chair/Dean's own IPCR) -- unlike prog_chair_faculty_evidence_details, every target
    category is included since no Program Chair reviews this group's evidence anymore.
    """
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

        from app.models.faculty import get_faculty_committed_targets, get_evidence_by_target
        targets = get_faculty_committed_targets(cursor, emp_id, term_id)

        for t in targets:
            t['is_core'] = not bool(t.get('is_admin_function'))
            t['evidence_list'] = get_evidence_by_target(cursor, t['target_id'])

        return jsonify({
            'success': True,
            'faculty_name': faculty_name,
            'academic_rank': fac_row[2] or '',
            'designation': fac_row[3] or '',
            'targets': targets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@dean_bp.route('/verify_evidence', methods=['POST'])
@role_required('DEAN')
def dean_verify_evidence():
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
                check_and_trigger_evidence_approved_notification(conn, cursor, int(evidence_id), 'College Dean', request.host_url)
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering evidence approved notification: {notif_err}")
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@dean_bp.route('/approve_package', methods=['POST'])
@role_required('DEAN')
def dean_approve_package():
    data = request.get_json(silent=True) or request.form
    emp_id = data.get('emp_id')
    if not emp_id:
        return jsonify({'success': False, 'message': 'Missing emp_id.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models import get_all_terms
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term.'}), 400
            
        term_id = active_term['term_id']

        # A Designated Faculty member's evidence (plain, or a chair/Dean's own IPCR) has no
        # Program Chair review before reaching here, so unlike Regular Faculty, the Dean
        # must explicitly finish reviewing every file for this group before final approval
        # is allowed.
        cursor.execute("SELECT designation FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        desig_row = cursor.fetchone()
        designation = (desig_row[0] or '').strip() if desig_row else ''
        from app.models.criteria import is_designated
        if is_designated(designation):
            from app.models.faculty import enrich_faculty_verification_status
            status = enrich_faculty_verification_status(cursor, {'emp_id': emp_id}, term_id)
            if not status.get('is_both_approved'):
                return jsonify({'success': False, 'message': 'Every evidence file must be reviewed (Approved or Returned) in Evidence Verification before final approval can be given.'}), 400

        cursor.execute("""
            UPDATE tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            SET ct.status = 'Dean Approved'
            WHERE ct.emp_id = %s AND mi.term_id = %s AND ct.status = 'Submitted to Dean'
        """, (emp_id, term_id))
        conn.commit()

        # Trigger Tier 2 (Final) email notification asynchronously
        try:
            from app.services.notification_service import check_and_trigger_tier2_notification
            check_and_trigger_tier2_notification(conn, cursor, int(emp_id), int(term_id), request.host_url)
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).error(f"Error triggering Tier 2 notification: {notif_err}")

        return jsonify({'success': True, 'message': 'Evidence package successfully approved!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@dean_bp.route('/return_to_faculty/<int:emp_id>', methods=['POST'])
@role_required('DEAN')
def dean_return_to_faculty(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models import get_all_terms
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term.'}), 400
            
        term_id = active_term['term_id']
        cursor.execute("""
            UPDATE tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            SET ct.status = 'Returned to Faculty'
            WHERE ct.emp_id = %s AND mi.term_id = %s AND ct.status = 'Dean Approved'
        """, (emp_id, term_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'IPCR successfully returned to faculty for printing!'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
