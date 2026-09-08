from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.models import *
from app.models.criteria import rank_band
from app.decorators import role_required

ret_chair_bp = Blueprint('ret_chair', __name__, url_prefix='/ret_chair')
@ret_chair_bp.route('/')
@role_required('RET_CHAIR')
def ret_chair_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    from app.models.connection import timed_query

    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)

        ret_indicators = []
        ret_rules = []
        pending_ret_drafts = []
        ret_assignments = []
        assignment_faculty = []
        rank_bands = RANK_BANDS
        faculty_rank_counts = {band: 0 for band in RANK_BANDS}
        total_regular_faculty = 0
        pending_ret_count = 0

        ranks_result = timed_query(cursor,
            "SELECT DISTINCT academic_rank FROM tbl_employee_profiles WHERE academic_rank IS NOT NULL AND academic_rank != '' ORDER BY academic_rank",
            label="ret_academic_ranks")
        academic_ranks = [row['academic_rank'] for row in ranks_result]

        if active_term:
            term_id = active_term['term_id']
            ret_indicators = get_ret_indicators(cursor, term_id)
            ret_rules = get_ret_rules(cursor, term_id)
            pending_ret_drafts = get_pending_ret_draft_ipcrs(cursor, term_id)
            ret_assignments = get_ret_target_assignments(cursor, term_id)
            assignment_faculty = get_ret_assignment_faculty(cursor, term_id)
            faculty_rank_counts = get_faculty_counts_by_rank(cursor, term_id)
            total_regular_faculty = get_total_regular_faculty_count(cursor)
            # Enrich each draft with dynamically computed ipcr_status
            from app.models.connection import get_overall_ipcr_status
            for draft in pending_ret_drafts:
                draft['ipcr_status'] = get_overall_ipcr_status(cursor, draft['emp_id'], term_id)
            pending_ret_count = sum(1 for d in pending_ret_drafts if d['ipcr_status'] in ('waiting_for_ret_chair_review', 'pending_ret_review'))
            # Read-only monitor: regular faculty with R&E targets, once Program Chair has
            # approved all their evidence. RET Chair no longer verifies anyone's evidence.
            evidence_faculty_list = get_ret_chair_evidence_faculty(cursor, term_id)

        return render_template('ret_chair_dashboard.html',
                               active_term=active_term,
                               ret_indicators=ret_indicators,
                               ret_rules=ret_rules,
                               academic_ranks=academic_ranks,
                               pending_ret_drafts=pending_ret_drafts,
                               ret_assignments=ret_assignments,
                               assignment_faculty=assignment_faculty,
                               rank_bands=rank_bands,
                               faculty_rank_counts=faculty_rank_counts,
                               total_regular_faculty=total_regular_faculty,
                               pending_ret_count=pending_ret_count,
                               evidence_faculty_list=evidence_faculty_list if 'evidence_faculty_list' in locals() else [],
                               has_own_ipcr=True)
    finally:
        cursor.close()
        conn.close()


@ret_chair_bp.route('/assignment_editor/<int:emp_id>')
@role_required('RET_CHAIR')
def assignment_editor(emp_id):
    """AJAX — returns the rank-eligible RET menu + current assignments for a faculty member."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term found.'}), 400
        term_id = active_term['term_id']

        cursor.execute(
            "SELECT CONCAT(first_name, ' ', last_name), academic_rank FROM tbl_employee_profiles WHERE emp_id = %s",
            (emp_id,)
        )
        fac_row = cursor.fetchone()
        if not fac_row:
            return jsonify({'success': False, 'message': 'Faculty member not found.'}), 404
        faculty_name, academic_rank = fac_row[0], (fac_row[1] or '')

        menu = get_faculty_ret_menu(cursor, academic_rank, term_id) if academic_rank else \
            {'research_indicators': [], 'extension_indicators': []}

        assigned_map = {
            a['indicator_id']: a
            for a in get_ret_faculty_assignments(cursor, term_id, emp_id)
        }

        def shape(items):
            from app.models.scoring import format_duration
            out = []
            for ind in items:
                ind_id = ind['indicator_id']
                asg = assigned_map.get(ind_id)

                qty = asg['target_quantity'] if (asg and asg.get('target_quantity') is not None) else (ind.get('target_quantity') or 1)
                desc = asg['target_description'] if (asg and asg.get('target_description')) else (ind.get('target_description') or '')
                dur_val = asg['target_duration_value'] if (asg and asg.get('target_duration_value') is not None) else (ind.get('target_duration_value') or '')
                dur_unit = asg['target_duration_unit'] if (asg and asg.get('target_duration_unit')) else (ind.get('target_duration_unit') or 'months')
                deadline = format_duration(dur_val, dur_unit)
                is_auto_description = asg.get('is_auto_description') if asg else None

                out.append({
                    'indicator_id': ind_id,
                    'indicator_description': ind['indicator_description'],
                    'default_quantity': ind.get('target_quantity') or 1,
                    'assigned_quantity': qty,
                    'target_description': desc,
                    'target_duration_value': dur_val,
                    'target_duration_unit': dur_unit,
                    'target_deadline': deadline,
                    'is_assigned': ind_id in assigned_map,
                    # None (never assigned yet) and 1 both mean "still auto-mirroring" —
                    # only an explicit 0 means the RET Chair customized it.
                    'is_auto_description': is_auto_description is None or is_auto_description == 1,
                })
            return out

        return jsonify({
            'success': True,
            'emp_id': emp_id,
            'faculty_name': faculty_name,
            'academic_rank': academic_rank,
            'research': shape(menu['research_indicators']),
            'extension': shape(menu['extension_indicators']),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@ret_chair_bp.route('/save_assignments', methods=['POST'])
@role_required('RET_CHAIR')
def save_assignments():
    """Saves the RET Chair's authored target assignments for one faculty member."""
    emp_id = request.form.get('emp_id')
    if not emp_id:
        flash("Missing faculty member.", "danger")
        return redirect(url_for('ret_chair.ret_chair_dashboard'))

    indicator_ids = request.form.getlist('assign_indicator_ids[]')
    assignments = []
    for ind_id in indicator_ids:
        qty_val = request.form.get(f'assign_quantity_{ind_id}', 1)
        desc_val = request.form.get(f'assign_description_{ind_id}', '').strip() or None
        # Explicit auto/customized flag from wireAutoDescription (base.html) — see Decision 1
        # in target_desc.md. Absent (None) falls back to inferring from blank-ness in
        # save_ret_assignments.
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
            return redirect(url_for('ret_chair.ret_chair_dashboard'))

        # Blank is valid here — save_ret_assignments auto-generates the standard description
        # from the indicator/quantity/duration when this is None.
        if not dur_val or dur_val <= 0:
            flash("All assigned targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('ret_chair.ret_chair_dashboard'))

        assignments.append((int(ind_id), qty, desc_val, dur_val, dur_unit_val, is_auto_flag))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            flash("No active academic term found.", "danger")
            return redirect(url_for('ret_chair.ret_chair_dashboard'))

        success, msg = save_ret_assignments(conn, cursor, active_term['term_id'],
                                            int(emp_id), assignments, session.get('user_id'))
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving assignments: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('ret_chair.ret_chair_dashboard'))


@ret_chair_bp.route('/faculty_evidence_details/<int:emp_id>')
@role_required('RET_CHAIR')
def ret_chair_faculty_evidence_details(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            return jsonify({'success': False, 'message': 'No active term found'}), 400

        term_id = active_term['term_id']

        cursor.execute("SELECT first_name, last_name, academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
        fac_row = cursor.fetchone()
        if not fac_row:
            return jsonify({'success': False, 'message': 'Faculty member not found'}), 404
        faculty_name = f"{fac_row[0]} {fac_row[1]}"

        from app.models.faculty import get_faculty_committed_targets, get_evidence_by_target
        all_targets = get_faculty_committed_targets(cursor, emp_id, term_id)

        # RET Chair ONLY sees Research & Extension targets and their uploaded evidence files
        ret_targets = []
        for t in all_targets:
            cat_name = t.get('category_name', '')
            if ('Research' in cat_name) or ('Extension' in cat_name):
                ev_list = get_evidence_by_target(cursor, t['target_id'])
                t['evidence_list'] = ev_list
                t['is_ret'] = True
                ret_targets.append(t)

        return jsonify({
            'success': True,
            'faculty_name': faculty_name,
            'academic_rank': fac_row[2] or '',
            'targets': ret_targets
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()



@ret_chair_bp.route('/save_rule', methods=['POST'])
@role_required('RET_CHAIR')
def ret_chair_save_rule():
    term_id = request.form.get('term_id')
    academic_rank = request.form.get('academic_rank')

    research_selections = request.form.get('research_selections', 0)
    research_indicator_ids = request.form.getlist('research_indicator_ids[]')
    extension_indicator_ids = request.form.getlist('extension_indicator_ids[]')

    if not term_id or not academic_rank:
        flash("Please fill all required fields.", "warning")
        return redirect(url_for('ret_chair.ret_chair_dashboard'))

    # Parse quantity, IPCR description and target duration for each checked Research indicator.
    research_indicators = []
    for r_id in research_indicator_ids:
        qty_val = request.form.get(f'research_quantity_{r_id}', 1)
        try:
            qty = int(qty_val)
            if qty < 1:
                qty = 1
        except ValueError:
            qty = 1
        # Blank is valid here — save_ret_rule auto-generates the standard description from
        # the indicator/quantity/duration when this is None.
        desc = (request.form.get(f'research_description_{r_id}', '') or '').strip() or None
        # Explicit auto/customized flag from wireAutoDescription (base.html) — see Decision 1
        # in target_desc.md. Absent (None) falls back to inferring from blank-ness in save_ret_rule.
        raw_auto_flag = request.form.get(f'research_auto_{r_id}')
        is_auto_flag = (raw_auto_flag == '1') if raw_auto_flag is not None else None
        dur_value, dur_unit, _ = parse_duration_fields(
            request.form, f'research_dur_value_{r_id}', f'research_dur_unit_{r_id}')

        if not dur_value or dur_value <= 0:
            flash("All selected research targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('ret_chair.ret_chair_dashboard'))

        research_indicators.append((int(r_id), qty, desc, dur_value, dur_unit, is_auto_flag))

    # Parse the same fields for Extension indicators (locked/mandatory rank-band targets,
    # not self-selected). Every configured Extension indicator is required for that rank band,
    # so the "required selections" count is simply how many were configured.
    extension_indicators = []
    for e_id in extension_indicator_ids:
        qty_val = request.form.get(f'extension_quantity_{e_id}', 1)
        try:
            qty = int(qty_val)
            if qty < 1:
                qty = 1
        except ValueError:
            qty = 1
        desc = (request.form.get(f'extension_description_{e_id}', '') or '').strip() or None
        raw_auto_flag = request.form.get(f'extension_auto_{e_id}')
        is_auto_flag = (raw_auto_flag == '1') if raw_auto_flag is not None else None
        dur_value, dur_unit, _ = parse_duration_fields(
            request.form, f'extension_dur_value_{e_id}', f'extension_dur_unit_{e_id}')

        if not dur_value or dur_value <= 0:
            flash("All Extension targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('ret_chair.ret_chair_dashboard'))

        extension_indicators.append((int(e_id), qty, desc, dur_value, dur_unit, is_auto_flag))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = save_ret_rule(conn, cursor, int(term_id), academic_rank,
                                     int(research_selections), len(extension_indicators),
                                     research_indicators, extension_indicators)

        if success:
            flash(msg, "success")
        else:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error saving rule: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('ret_chair.ret_chair_dashboard'))


@ret_chair_bp.route('/delete_rule', methods=['POST'])
@role_required('RET_CHAIR')
def ret_chair_delete_rule():
    term_id = request.form.get('term_id')
    rule_id = request.form.get('rule_id')
    category_type = request.form.get('category_type')
    if not term_id:
        flash("Missing term.", "warning")
        return redirect(url_for('ret_chair.ret_chair_dashboard'))
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success = delete_ret_rule(conn, cursor, int(term_id), rule_id, category_type)
        if success:
            flash("Rule deleted successfully.", "success")
        else:
            flash("Failed to delete rule.", "danger")
    except Exception as e:
        flash(f"Error deleting rule: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('ret_chair.ret_chair_dashboard'))


@ret_chair_bp.route('/unlock_extension_rule', methods=['POST'])
@role_required('RET_CHAIR')
def ret_chair_unlock_extension_rule():
    """Unlocks a rank band's Extension configuration so it can be edited and re-saved."""
    term_id = request.form.get('term_id')
    academic_rank = request.form.get('academic_rank')
    if not academic_rank or not term_id:
        flash("Missing rank band or term.", "warning")
        return redirect(url_for('ret_chair.ret_chair_dashboard'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = unlock_ret_extension_rule(conn, cursor, int(term_id), academic_rank)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error unlocking Extension configuration: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('ret_chair.ret_chair_dashboard'))


@ret_chair_bp.route('/review_ipcr/<int:emp_id>')
@role_required('RET_CHAIR')
def review_ipcr(emp_id):
    """
    AJAX endpoint — returns JSON payload of Research/Extension targets for RET review.
    Creates a tbl_ipcr_ret_review record if one doesn't exist.
    """
    import time
    print(f"\n[DEBUG] === Entered review_ipcr for emp_id={emp_id} ===")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        ret_chair_emp_id = session.get('user_id')
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)

        if not active_term:
            print("[DEBUG] No active term found.")
            return jsonify({'error': 'No active term found.'}), 400

        term_id = active_term['term_id']
        print(f"[DEBUG] Active term_id={term_id}")

        # Check overall IPCR status for sequential tracking guardrails
        from app.models.connection import get_overall_ipcr_status
        ipcr_status = get_overall_ipcr_status(cursor, emp_id, term_id)

        # Fetch overall status of review header if it exists
        cursor.execute(
            "SELECT overall_status FROM tbl_ipcr_ret_review WHERE emp_id = %s AND term_id = %s",
            (emp_id, term_id)
        )
        review_row = cursor.fetchone()
        existing_status = review_row[0] if review_row else None

        # Block if unsubmitted and not already reviewed/returned
        if ipcr_status == 'draft' and existing_status not in ('Approved', 'Rejected'):
            return jsonify({'error': 'Faculty has not submitted their choices for review yet.'}), 403

        # Fetch or create RET review record
        t0 = time.time()
        review_id = get_or_create_ret_review(conn, cursor, emp_id, term_id, ret_chair_emp_id)
        print(f"[DEBUG] get_or_create_ret_review took {time.time() - t0:.4f}s. review_id={review_id}")

        # Fetch RET review items
        t0 = time.time()
        items = get_ret_review_items(cursor, review_id)
        print(f"[DEBUG] get_ret_review_items took {time.time() - t0:.4f}s. Found {len(items)} items.")

        # Fetch overall status and remarks
        cursor.execute(
            "SELECT overall_status, overall_remarks FROM tbl_ipcr_ret_review WHERE review_id = %s",
            (review_id,)
        )
        review_row = cursor.fetchone()
        overall_status = review_row[0] if review_row else 'Pending'
        overall_remarks = review_row[1] if review_row else ''

        # Fetch faculty details
        cursor.execute(
            "SELECT CONCAT(first_name, ' ', last_name), academic_rank FROM tbl_employee_profiles WHERE emp_id = %s",
            (emp_id,)
        )
        fac_row = cursor.fetchone()
        faculty_name = fac_row[0] if fac_row else 'Unknown'
        academic_rank = fac_row[1] if fac_row else ''
        faculty_rank_band = rank_band(academic_rank)
        print(f"[DEBUG] Faculty: {faculty_name}, Rank: {academic_rank} (band: {faculty_rank_band})")

        # Fetch available Research indicators for this rank band (Extension is rank-band
        # locked, not self-selected, so it is excluded from the selectable/unpicked pool).
        t0 = time.time()
        cursor.execute("""
            SELECT mi.indicator_id, mi.indicator_description, tc.category_name, rri.target_quantity
            FROM tbl_ret_rules r
            JOIN tbl_ret_rule_indicators rri ON r.rule_id = rri.rule_id
            JOIN tbl_master_indicators mi ON rri.indicator_id = mi.indicator_id
            JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
            WHERE r.academic_rank = %s AND mi.term_id = %s AND tc.slug = 'research'
        """, (faculty_rank_band, term_id))
        rules_indicators = cursor.fetchall()
        print(f"[DEBUG] Fetch rules indicators query took {time.time() - t0:.4f}s. Found {len(rules_indicators)} indicators.")

        all_ret_indicators = []
        for ind_id, desc, cat, qty in rules_indicators:
            all_ret_indicators.append({
                'indicator_id': ind_id,
                'indicator_description': desc,
                'category_name': cat,
                'target_quantity': qty
            })

        serializable_items = []
        selected_ids = set()
        for item in items:
            rev_qty = item['reviewed_quantity']
            if rev_qty is not None and rev_qty > 0:
                serializable_items.append({
                    'item_id': item['item_id'],
                    'draft_id': item['draft_id'],
                    'indicator_id': item['indicator_id'],
                    'indicator_description': item['indicator_description'],
                    'category_name': item['category_name'],
                    'original_quantity': item['original_quantity'],
                    'reviewed_quantity': rev_qty,
                    'item_remarks': item['item_remarks'] or '',
                    'target_duration_value': item.get('target_duration_value'),
                    'target_duration_unit': item.get('target_duration_unit'),
                })
                selected_ids.add(item['indicator_id'])

        unpicked = []
        inactive_item_ids = {item['indicator_id']: item['item_id'] for item in items if item['reviewed_quantity'] is None or item['reviewed_quantity'] <= 0}
        for ind in all_ret_indicators:
            if ind['indicator_id'] not in selected_ids:
                ind_copy = ind.copy()
                ind_copy['item_id'] = inactive_item_ids.get(ind['indicator_id'])
                unpicked.append(ind_copy)

        # Rank-band Extension targets — shown read-only in the Submitted Targets table
        # (RET-Chair-configured per rank band; not editable and not in the unpicked pool).
        extension_menu = get_faculty_ret_menu(cursor, academic_rank, term_id)
        extension_items = [{
            'indicator_id': e['indicator_id'],
            'indicator_description': e['indicator_description'],
            'category_name': 'Extension Services / Training / Advisory',
            'reviewed_quantity': e['target_quantity'],
        } for e in extension_menu['extension_indicators']]

        print(f"[DEBUG] review_ipcr returning JSON payload successfully. Review ID={review_id}")
        return jsonify({
            'review_id': review_id,
            'emp_id': emp_id,
            'faculty_name': faculty_name,
            'academic_rank': academic_rank,
            'overall_status': overall_status,
            'overall_remarks': overall_remarks or '',
            'items': serializable_items,
            'extension': extension_items,
            'unpicked': unpicked
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@ret_chair_bp.route('/edit_review_item', methods=['POST'])
@role_required('RET_CHAIR')
def edit_review_item():
    """
    Saves an edited quantity and optional remark for one RET review item row.
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
        success, msg = update_ret_review_item(conn, cursor, int(item_id), int(reviewed_quantity), item_remarks)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@ret_chair_bp.route('/save_review_items', methods=['POST'])
@role_required('RET_CHAIR')
def save_review_items():
    data = request.get_json()
    review_id = data.get('review_id')
    items = data.get('items')

    if not review_id or items is None:
        return jsonify({'success': False, 'message': 'Missing review_id or items.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.ret_chair import save_ret_review_items
        success, msg = save_ret_review_items(cursor, conn, int(review_id), items)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@ret_chair_bp.route('/decide_ipcr', methods=['POST'])
@role_required('RET_CHAIR')
def decide_ipcr():
    """
    Approves or rejects the RET selections.
    """
    import json
    review_id = request.form.get('review_id')
    action = request.form.get('action')           # 'approve' or 'reject'
    overall_remarks = request.form.get('overall_remarks', '').strip()
    items_json = request.form.get('items_json')

    if not review_id or action not in ('approve', 'reject'):
        flash("Invalid decision parameters.", "danger")
        return redirect(url_for('ret_chair.ret_chair_dashboard'))

    if action == 'reject' and not overall_remarks:
        flash("Remarks / Reason is required when returning the IPCR to faculty.", "danger")
        return redirect(url_for('ret_chair.ret_chair_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check overall IPCR status for sequential tracking guardrails
        cursor.execute(
            "SELECT emp_id, term_id FROM tbl_ipcr_ret_review WHERE review_id = %s",
            (review_id,)
        )
        row = cursor.fetchone()
        if row:
            emp_id, term_id = row
            from app.models.connection import get_overall_ipcr_status
            ipcr_status = get_overall_ipcr_status(cursor, emp_id, term_id)

            if ipcr_status == 'draft':
                flash("Faculty has not submitted their choices for review yet.", "danger")
                return redirect(url_for('ret_chair.ret_chair_dashboard'))

        # If items are submitted inline, save them first inside the same transaction
        if items_json:
            try:
                items = json.loads(items_json)
                from app.models.ret_chair import save_ret_review_items
                save_success, save_msg = save_ret_review_items(cursor, conn, int(review_id), items)
                if not save_success:
                    flash(f"Failed to save targets: {save_msg}", "danger")
                    return redirect(url_for('ret_chair.ret_chair_dashboard'))
            except Exception as json_err:
                flash(f"Invalid target items format: {str(json_err)}", "danger")
                return redirect(url_for('ret_chair.ret_chair_dashboard'))

        success, msg = decide_ret_review(conn, cursor, int(review_id), action, overall_remarks)
        if success and row:
            if action == 'approve':
                try:
                    from app.services.notification_service import send_ret_approval_notifications
                    send_ret_approval_notifications(conn, cursor, int(emp_id), int(term_id))
                except Exception as notif_err:
                    import logging
                    logging.getLogger(__name__).error(f"Error triggering RET approval notification: {notif_err}")
            elif action == 'reject':
                try:
                    from app.services.notification_service import send_return_notification
                    send_return_notification(conn, cursor, "RET Chair", int(review_id), int(emp_id), int(term_id), overall_remarks)
                except Exception as notif_err:
                    import logging
                    logging.getLogger(__name__).error(f"Error triggering Return notification: {notif_err}")

        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error processing decision: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('ret_chair.ret_chair_dashboard'))
