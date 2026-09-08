from flask import Blueprint, render_template, session, request, jsonify, redirect, url_for, flash
from app.models import *
from app.decorators import role_required, designated_ipcr_required
from app.models.designated import (
    get_designated_selectable_indicators, submit_designated_ipcr,
    lock_and_commit_designated_ipcr
)

designated_bp = Blueprint('designated', __name__, url_prefix='/designated')


@designated_bp.route('/')
@designated_ipcr_required
def designated_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    from app.models.connection import timed_query

    emp_id = session.get('user_id')

    emp_result = timed_query(cursor, """
        SELECT academic_rank, specialization, designation, first_name, last_name, assigned_program 
        FROM tbl_employee_profiles 
        WHERE emp_id = %s
    """, (emp_id,), label="designated_profile")
    
    academic_rank = emp_result[0]['academic_rank'] if emp_result else ''
    specialization = emp_result[0]['specialization'] if emp_result else ''
    designation = emp_result[0]['designation'] if emp_result else ''
    first_name = emp_result[0]['first_name'] if emp_result else ''
    last_name = emp_result[0]['last_name'] if emp_result else ''
    assigned_program = emp_result[0]['assigned_program'] if emp_result else ''

    # A Program Chair, RET Chair, or Dean's own IPCR is fully Dean-formulated (see
    # save_and_issue_designated_draft_ipcr in app/models/dean.py and CLAUDE.md's
    # designation/system_role note) -- issued and auto-approved by the Dean rather than
    # self-submitted. A Plain Designated Faculty still authors and submits their own (Decision 4).
    is_dean_formulated = (designation or '').strip() in ('Program Chair', 'RET Chair', 'Dean')

    terms = get_all_terms(cursor)
    active_term = next((t for t in terms if t['is_active'] == 1), None)

    dpcr_targets = []
    has_submitted = False
    can_edit = True
    dean_review = None
    is_returned = False
    # Only meaningful for a Dean-formulated draft that's approved but not yet committed --
    # see the gap this closes in lock_and_commit_designated_ipcr / get_core_instruction_allocation.
    instruction_ready = True
    awaiting_dean_formulation = False

    if active_term:
        term_id = active_term['term_id']
        
        # Check if committed targets exist for evidence gathering
        cursor.execute("""
            SELECT COUNT(*) FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))
        is_committed = cursor.fetchone()[0] > 0

        # Check if the user has already submitted
        sub_result = timed_query(cursor, """
            SELECT COUNT(*) as cnt FROM tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            WHERE dt.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id), label="designated_submit_check")
        has_submitted = sub_result[0]['cnt'] > 0 if sub_result else False

        # Fetch Dean's overall review status & remarks
        dr_result = timed_query(cursor, """
            SELECT overall_status, overall_remarks
            FROM tbl_ipcr_dean_review
            WHERE emp_id = %s AND term_id = %s
            ORDER BY reviewed_at DESC LIMIT 1
        """, (emp_id, term_id), label="designated_dean_review")
        if dr_result:
            dean_review = dr_result[0]

        # Determine editability. Editable before the first submit, and again after the Dean
        # returns it — a returned IPCR is returned *because* something needs changing, so
        # view-only plus a status-flipping "Re-submit" button left no way to act on the Dean's
        # remarks (targets couldn't be re-picked, quantities/deadlines couldn't be corrected,
        # and a custom target added on that screen was silently dropped, since the resubmit
        # route only touches review_status). Re-submitting a returned IPCR now goes through the
        # full submit path, which rebuilds tbl_draft_targets and resets the Dean review.
        # Still view-only while awaiting review, once approved, and once committed.
        is_returned = bool(dean_review and dean_review.get('overall_status') == 'Rejected')
        # A Dean-formulated draft (Program Chair/RET Chair/Dean, see save_and_issue_designated_
        # draft_ipcr in app/models/dean.py) is never self-submitted or self-edited -- it's
        # issued pre-approved by the Dean, so this person never gets the classic pick-your-own-
        # targets form, before or after issuance.
        can_edit = ((not has_submitted) or is_returned) and not is_dean_formulated
        # A Dean-formulated draft is never resubmitted by the person it belongs to -- there is
        # no self-edit path for them to correct anything, so "Returned by Dean" + a Re-submit
        # button (the classic Rejected-status UI) would be a dead end here. This treats a
        # rejection exactly like never having been issued: wait for the Dean to reissue via the
        # Draft IPCR Studio. In the normal auto-approve flow a chair's review never sits
        # Rejected -- this mainly guards a partial failure inside save_and_issue_designated_
        # draft_ipcr (issued but the final approve step errored) from stranding them.
        awaiting_dean_formulation = is_dean_formulated and (not has_submitted or is_returned)

        evidence_readiness = None
        ipcr_score = None
        has_final_ipcr = False
        ipcr_form_preview = None
        evidence_sections = []
        if is_committed:
            can_edit = False
            has_submitted = True
            from app.models.designated import get_designated_committed_targets, check_designated_evidence_readiness
            from app.models.faculty import get_evidence_by_target

            # Fetch cascaded instruction allocations from Program Chair (departmental CHAIR instruction, not Dean College-Wide) to flag as core
            cursor.execute("""
                SELECT da.indicator_id FROM tbl_draft_allocation da
                JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                JOIN tbl_cascaded_quotas cq ON mi.indicator_id = cq.indicator_id AND cq.term_id = mi.term_id
                WHERE da.emp_id = %s AND mi.term_id = %s 
                  AND tc.slug = 'instruction'
                  AND tc.review_lane = 'CHAIR'
                  AND cq.assigned_to_role != 'College-Wide'
            """, (emp_id, term_id))
            alloc_ids = {r[0] for r in cursor.fetchall()}

            dpcr_targets = get_designated_committed_targets(cursor, emp_id, term_id)
            for t in dpcr_targets:
                t['is_selected'] = True
                t['total_target_value'] = t['assigned_quantity']
                if t.get('category_name') == 'Custom Target Items':
                    t['category_name'] = 'Support Functions'
                # A chair's oversight row (is_admin_function) can share an indicator_id with
                # their own personal Core Function allocation of that same indicator — only
                # the personal row belongs in Core Functions; the oversight row stays a
                # Strategic Priorities/Support Function target regardless of alloc_ids.
                if not t.get('is_admin_function') and (
                        'Teaching Load' in (t.get('indicator_description') or '') or t['indicator_id'] in alloc_ids):
                    t['is_core'] = True
                    t['is_locked'] = True
                # is_oversight_cascade is already set by get_designated_committed_targets
                # (narrower than is_admin_function, which is also 1 for a freely-picked
                # Strategic Priorities/Support item, not just a genuine departmental
                # oversight quota — see get_oversight_indicator_ids).
                if not t.get('is_oversight_cascade'):
                    t['evidence_list'] = get_evidence_by_target(cursor, t['target_id'])
            evidence_readiness = check_designated_evidence_readiness(cursor, emp_id, term_id, dpcr_targets)
            has_final_ipcr = any(t.get('status') == 'Dean Approved' for t in dpcr_targets) if dpcr_targets else False
            # Live IPCR summary — uses the Designated Faculty weight table.
            from app.models.scoring import compute_ipcr_score
            ipcr_score = compute_ipcr_score(cursor, emp_id, term_id)
            # The "Print IPCR" preview below has to show the same category grouping the
            # actual printed form does (weighted category, not raw target type — an
            # is_admin_function row can belong to a different weighted category than its
            # own type, see ipcr_form.py), so it reuses the same builder as the real print
            # rather than re-deriving the grouping a third time.
            from app.models.ipcr_form import build_ipcr_form
            ipcr_form_preview = build_ipcr_form(cursor, emp_id, term_id)
            # Same category -> target-type grouping the printed IPCR uses, applied to
            # dpcr_targets (not get_faculty_committed_targets, the print form's source)
            # so the checklist keeps its pool-selection/oversight-cascade markers
            # (is_selected, is_oversight_cascade, is_custom) that the print form doesn't need.
            from app.models.ipcr_form import build_evidence_checklist_sections
            from app.models.criteria import resolve_designation_type, DESIGNATION_DESIGNATED
            checklist_designation_type = resolve_designation_type(designation) or DESIGNATION_DESIGNATED
            evidence_sections = build_evidence_checklist_sections(
                cursor, dpcr_targets, checklist_designation_type, term_id, academic_rank)

        elif can_edit:
            # Load standard selectable indicators and exclude 21 hours regular teaching load targets
            raw_standard_targets = get_designated_selectable_indicators(cursor, term_id, emp_id=emp_id)
            standard_targets = [
                t for t in raw_standard_targets 
                if '21 hours' not in t['indicator_description'] and '21 hrs' not in t['indicator_description']
            ]
            
            # Fetch cascaded allocations (Program Chair instruction + Dean College-Wide)
            cursor.execute("""
                SELECT da.indicator_id, da.assigned_quantity, da.custom_description, da.target_deadline,
                       da.target_duration_value, da.target_duration_unit, tc.slug, tc.review_lane,
                       (SELECT COUNT(*) FROM tbl_cascaded_quotas cq WHERE cq.indicator_id = mi.indicator_id AND cq.term_id = mi.term_id AND cq.assigned_to_role = 'College-Wide') as is_college_wide
                FROM tbl_draft_allocation da
                JOIN tbl_master_indicators mi ON da.indicator_id = mi.indicator_id
                JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                WHERE da.emp_id = %s AND mi.term_id = %s
            """, (emp_id, term_id))
            alloc_rows = cursor.fetchall()
            alloc_map = {r[0]: {'assigned_quantity': r[1], 'custom_description': r[2], 'target_deadline': r[3],
                                'target_duration_value': r[4], 'target_duration_unit': r[5], 'slug': r[6],
                                'review_lane': r[7], 'is_college_wide': r[8]} for r in alloc_rows}

            draft_targets = timed_query(cursor, """
                SELECT dt.draft_id as target_id, dt.indicator_id, dt.proposed_quantity as total_target_value, dt.review_status as status,
                       dt.target_description, dt.target_deadline, dt.target_duration_value, dt.target_duration_unit,
                       dt.is_auto_description,
                       mi.indicator_description, tc.category_name, mi.is_custom,
                       dri.item_remarks as dean_remarks, dri.original_quantity, dri.reviewed_quantity
                FROM tbl_draft_targets dt
                JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                LEFT JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
                WHERE dt.emp_id = %s AND mi.term_id = %s
                ORDER BY tc.category_name, mi.indicator_id
            """, (emp_id, term_id), label="designated_load_drafts")

            for d in draft_targets:
                # Kept before the display remap below: a custom row re-submitted from this
                # screen has to resolve back to the same tbl_target_categories row it was
                # filed under, and the remapped display name would not find it.
                d['custom_category_name'] = d['category_name']
                if d['category_name'] == 'Custom Target Items':
                    d['category_name'] = 'Support Functions'

            draft_map = {d['indicator_id']: d for d in draft_targets}

            # Configured teaching load, used as the fallback when a draft row has none.
            cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
            _tl_rank = cursor.fetchone()
            tl_default_hours, _tl_dv, _tl_du = resolve_teaching_load(
                cursor, term_id, 'Designated Faculty', _tl_rank[0] if _tl_rank else None)
            tl_default_desc = teaching_load_description(tl_default_hours)
            tl_default_deadline = format_duration(_tl_dv, _tl_du)

            dpcr_targets = []
            seen_indicator_ids = set()
            for t in standard_targets:
                ind_id = t['indicator_id']
                seen_indicator_ids.add(ind_id)
                is_tl = 'Teaching Load' in t['indicator_description']

                if is_tl:
                    t['total_target_value'] = draft_map[ind_id]['total_target_value'] if ind_id in draft_map else tl_default_hours
                    t['target_description'] = (draft_map[ind_id]['target_description'] if ind_id in draft_map else None) or tl_default_desc
                    t['target_deadline'] = (draft_map[ind_id]['target_deadline'] if ind_id in draft_map else None) or tl_default_deadline
                    t['status'] = draft_map[ind_id]['status'] if ind_id in draft_map else 'Draft'
                    t['is_selected'] = True
                    t['is_mandatory'] = True
                    t['is_core'] = True
                    t['is_locked'] = True
                elif ind_id in alloc_map and (alloc_map[ind_id].get('assigned_quantity') or 0) > 0:
                    is_chair_instruction = (
                        alloc_map[ind_id].get('slug') == 'instruction'
                        and alloc_map[ind_id].get('review_lane') == 'CHAIR'
                        and alloc_map[ind_id].get('is_college_wide', 0) == 0
                    )
                    t['total_target_value'] = draft_map[ind_id]['total_target_value'] if ind_id in draft_map else alloc_map[ind_id]['assigned_quantity']
                    t['target_description'] = (draft_map[ind_id]['target_description'] if ind_id in draft_map else None) or alloc_map[ind_id]['custom_description'] or t['indicator_description']
                    t['target_deadline'] = (draft_map[ind_id]['target_deadline'] if ind_id in draft_map else None) or alloc_map[ind_id]['target_deadline'] or ''
                    t['status'] = draft_map[ind_id]['status'] if ind_id in draft_map else 'Draft'
                    t['is_selected'] = True
                    t['is_cascaded'] = True
                    t['is_core'] = is_chair_instruction
                    t['is_locked'] = is_chair_instruction
                    t['is_auto_description'] = draft_map[ind_id].get('is_auto_description') if ind_id in draft_map else None
                elif ind_id in draft_map:
                    t['total_target_value'] = draft_map[ind_id]['total_target_value']
                    t['target_description'] = draft_map[ind_id]['target_description'] or t['indicator_description']
                    t['target_deadline'] = draft_map[ind_id]['target_deadline'] or ''
                    t['status'] = draft_map[ind_id]['status']
                    t['dean_remarks'] = draft_map[ind_id]['dean_remarks']
                    t['original_quantity'] = draft_map[ind_id]['original_quantity']
                    t['reviewed_quantity'] = draft_map[ind_id]['reviewed_quantity']
                    t['is_selected'] = True
                    t['is_core'] = False
                    t['is_locked'] = False
                    t['is_auto_description'] = draft_map[ind_id].get('is_auto_description')
                else:
                    t['total_target_value'] = 0
                    t['target_description'] = t['indicator_description']
                    t['target_deadline'] = ''
                    t['status'] = 'Draft'
                    t['is_selected'] = False
                    t['is_core'] = False
                    t['is_locked'] = False
                    t['is_auto_description'] = None

                # Structured duration (drives Timeliness): prefer the faculty's own draft,
                # else the Program Chair's cascaded allocation.
                _src = draft_map.get(ind_id) or {}
                _alloc = alloc_map.get(ind_id) or {}
                t['target_duration_value'] = _src.get('target_duration_value') or _alloc.get('target_duration_value')
                t['target_duration_unit'] = _src.get('target_duration_unit') or _alloc.get('target_duration_unit')
                dpcr_targets.append(t)
                
            # A chair answers for their department's (or RET's) whole cascaded quota as an
            # administrative function. These are appended even when the same indicator is
            # already listed above as their personal allocated work — the two rate under
            # different IPCR categories, which is what is_admin_function distinguishes.
            from app.models.designated import get_oversight_targets
            dpcr_targets.extend(get_oversight_targets(cursor, emp_id, term_id))

            # Add custom targets from drafts
            for d in draft_targets:
                if d['is_custom']:
                    d['is_selected'] = True
                    d['is_core'] = False
                    d['is_locked'] = False
                    dpcr_targets.append(d)

            # Ensure mandatory default Teaching Load target (10 hours) is present if not already added
            has_teaching_load = any(
                t.get('category_name') == 'A. Instructions' and 'Teaching Load' in str(t.get('indicator_description', ''))
                for t in dpcr_targets
            )
            if not has_teaching_load:
                # Hours/duration come from the Admin's teaching-load configuration.
                cursor.execute("SELECT academic_rank FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,))
                tl_rank_row = cursor.fetchone()
                tl_hours, tl_dur_value, tl_dur_unit = resolve_teaching_load(
                    cursor, term_id, 'Designated Faculty', tl_rank_row[0] if tl_rank_row else None)
                tl_desc = teaching_load_description(tl_hours)

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
                    'total_target_value': tl_hours,
                    'status': 'Draft',
                    'indicator_description': tl_desc,
                    'target_description': tl_desc,
                    'target_deadline': format_duration(tl_dur_value, tl_dur_unit),
                    'target_duration_value': tl_dur_value,
                    'target_duration_unit': tl_dur_unit,
                    'category_name': 'A. Instructions',
                    'is_custom': False,
                    'is_selected': True,
                    'is_mandatory': True,
                    'is_core': True,
                    'is_locked': True
                }
                dpcr_targets.insert(0, mandatory_target)
        else:
            # Fetch cascaded instruction allocations from Program Chair (departmental CHAIR instruction, not Dean College-Wide) to flag as core
            from app.models.designated import get_core_instruction_allocation
            core_instruction_rows = get_core_instruction_allocation(cursor, emp_id, term_id)
            alloc_ids = {r['indicator_id'] for r in core_instruction_rows}

            # See the is_committed branch above for why this is narrower than is_admin_function.
            from app.models.designated import get_oversight_indicator_ids
            oversight_ids = get_oversight_indicator_ids(cursor, emp_id, term_id)

            # If they cannot edit, we just load their submitted drafts
            dpcr_targets = timed_query(cursor, """
                SELECT dt.draft_id as target_id, dt.indicator_id, dt.proposed_quantity as total_target_value, dt.review_status as status,
                       dt.target_description, dt.target_deadline, dt.target_duration_value, dt.target_duration_unit,
                       dt.is_admin_function,
                       mi.indicator_description, tc.category_name, mi.is_custom,
                       dri.item_remarks as dean_remarks, dri.original_quantity, dri.reviewed_quantity
                FROM tbl_draft_targets dt
                JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                LEFT JOIN tbl_ipcr_dean_review_items dri ON dt.draft_id = dri.draft_id
                WHERE dt.emp_id = %s AND mi.term_id = %s
                ORDER BY tc.category_name, mi.indicator_id
            """, (emp_id, term_id), label="designated_load_drafts")
            from app.models.ipcr_description import format_ipcr_target_description
            for t in dpcr_targets:
                t['is_selected'] = True
                if t['category_name'] == 'Custom Target Items':
                    t['category_name'] = 'Support Functions'
                # See the is_committed branch above: an oversight row can share an
                # indicator_id with the chair's own personal Core Function allocation, so
                # alloc_ids membership alone isn't enough to call it Core.
                if not t.get('is_admin_function') and (
                        'Teaching Load' in t['indicator_description'] or t['indicator_id'] in alloc_ids):
                    t['is_core'] = True
                    t['is_locked'] = True
                t['is_oversight_cascade'] = bool(t.get('is_admin_function')) and t['indicator_id'] in oversight_ids
                if t['is_oversight_cascade']:
                    # Never trust the stored dt.target_description here — an oversight row has
                    # no description input of its own (see get_oversight_targets), so it can
                    # never legitimately hold customized text. Always regenerating means a
                    # draft saved before this quantity/unit substitution existed (or before a
                    # since-changed Dean quota) still renders correctly, with no backfill needed.
                    t['target_description'] = format_ipcr_target_description(
                        t['indicator_description'], t['total_target_value'],
                        t.get('target_duration_value'), t.get('target_duration_unit'))

            if is_dean_formulated and dean_review and dean_review.get('overall_status') == 'Approved':
                # This person's own Instruction share (tbl_draft_allocation) isn't inserted into
                # tbl_draft_targets until Lock & Commit (see lock_and_commit_designated_ipcr) --
                # a Dean-formulated draft can be issued before the Program Chair distributes it.
                # Show it here as a preview anyway, so a Chair can see their Core Functions are
                # complete before locking, not just after.
                #
                # Scoped to Core rows only (is_admin_function falsy): the same indicator can
                # already be present as this person's departmental oversight row
                # (is_admin_function=1, from get_oversight_targets) without that meaning their
                # personal Core share exists too -- see lock_and_commit_designated_ipcr for the
                # matching commit-time guard.
                existing_core_ids = {t['indicator_id'] for t in dpcr_targets if not t.get('is_admin_function')}
                from app.models.designated import describe_core_instruction_allocation
                for r in core_instruction_rows:
                    if r['indicator_id'] in existing_core_ids:
                        continue
                    desc, deadline, _ = describe_core_instruction_allocation(r)
                    dpcr_targets.append({
                        'target_id': f"pending_core_{r['indicator_id']}",
                        'indicator_id': r['indicator_id'],
                        'indicator_description': r['indicator_description'],
                        'target_description': desc,
                        'category_name': r.get('category_name') or 'Instruction',
                        'total_target_value': r['assigned_quantity'],
                        'target_deadline': deadline,
                        'target_duration_value': r.get('target_duration_value'),
                        'target_duration_unit': r.get('target_duration_unit'),
                        'is_selected': True,
                        'is_core': True,
                        'is_cascaded': True,
                        'is_locked': True,
                        'is_admin_function': False,
                        'is_oversight_cascade': False,
                    })

                # Gate Lock & Commit on this person's own Instruction share actually existing
                # (or not being required at all) -- otherwise a Chair could lock an incomplete
                # IPCR before the Program Chair has distributed it to them.
                if not alloc_ids:
                    cursor.execute("""
                        SELECT COUNT(*) FROM tbl_cascaded_quotas cq
                        JOIN tbl_master_indicators mi ON cq.indicator_id = mi.indicator_id
                        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
                        WHERE cq.term_id = %s AND mi.term_id = %s AND tc.slug = 'instruction'
                          AND tc.review_lane = 'CHAIR' AND cq.assigned_to_role = %s
                          AND cq.total_target_value > 0
                    """, (term_id, term_id, specialization or ''))
                    requires_instruction = cursor.fetchone()[0] > 0
                    instruction_ready = not requires_instruction

    cursor.close()
    conn.close()

    return render_template('designated_dashboard.html',
                           emp_name=f"{first_name} {last_name}",
                           academic_rank=academic_rank,
                           designation=designation,
                           is_dean_formulated=is_dean_formulated,
                           instruction_ready=instruction_ready,
                           awaiting_dean_formulation=awaiting_dean_formulation,
                           assigned_program=assigned_program,
                           active_term=active_term,
                           dpcr_targets=dpcr_targets,
                           has_submitted=has_submitted,
                           can_edit=can_edit,
                           is_returned=is_returned,
                           is_committed=is_committed,
                           is_locked=is_committed,
                           dean_review=dean_review,
                           evidence_readiness=evidence_readiness,
                           ipcr_score=ipcr_score,
                           has_final_ipcr=has_final_ipcr,
                           ipcr_form_preview=ipcr_form_preview,
                           evidence_sections=evidence_sections)


@designated_bp.route('/lock_ipcr', methods=['POST'])
@designated_ipcr_required
def designated_lock_ipcr():
    """Lock the approved draft IPCR and commit it to tbl_committed_targets."""
    emp_id = session.get('user_id')
    term_id = request.form.get('term_id')

    if not term_id:
        flash("No active academic term found.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        success, msg = lock_and_commit_designated_ipcr(conn, cursor, emp_id, int(term_id))
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error locking IPCR: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('designated.designated_dashboard'))


@designated_bp.route('/resubmit_ipcr', methods=['POST'])
@designated_ipcr_required
def designated_resubmit_ipcr():
    """Re-submit returned draft IPCR to Dean for approval."""
    emp_id = session.get('user_id')
    term_id = request.form.get('term_id')

    if not term_id:
        flash("No active academic term found.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE tbl_draft_targets dt
            JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
            SET dt.review_status = 'Pending Review'
            WHERE dt.emp_id = %s AND mi.term_id = %s
        """, (emp_id, int(term_id)))

        cursor.execute("""
            UPDATE tbl_ipcr_dean_review
            SET overall_status = 'Pending Review'
            WHERE emp_id = %s AND term_id = %s
        """, (emp_id, int(term_id)))

        conn.commit()
        try:
            from app.services.notification_service import send_designated_target_submission_notification
            send_designated_target_submission_notification(conn, cursor, emp_id, int(term_id), is_resubmission=True)
        except Exception as notif_err:
            import logging
            logging.getLogger(__name__).error(f"Error triggering designated resubmission notification: {notif_err}")
        flash("IPCR has been re-submitted for Dean's approval.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error re-submitting IPCR: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('designated.designated_dashboard'))


@designated_bp.route('/save_accomplishment', methods=['POST'])
@designated_ipcr_required
def designated_save_accomplishment():
    """AJAX — save Timeliness (and client-satisfaction Efficiency) inputs for one target."""
    emp_id = session.get('user_id')
    data = request.get_json(silent=True) or request.form
    target_id = data.get('target_id')
    if not target_id:
        return jsonify({'success': False, 'message': 'Missing target_id.'}), 400

    def _int_or_none(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.faculty import save_accomplishment_details
        success, msg = save_accomplishment_details(
            conn, cursor, emp_id, int(target_id),
            _int_or_none(data.get('actual_duration_value')),
            (data.get('completion_status') or '').strip() or None,
            _int_or_none(data.get('efficiency_rating_E')),
            data.get('print_remarks'),
        )
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@designated_bp.route('/save_oversight_deadline', methods=['POST'])
@designated_ipcr_required
def designated_save_oversight_deadline():
    """AJAX -- let a chair correct their own Departmental Oversight row's deadline pre-lock."""
    emp_id = session.get('user_id')
    data = request.get_json(silent=True) or request.form
    draft_id = data.get('draft_id')
    duration_unit = (data.get('duration_unit') or '').strip()
    if not draft_id:
        return jsonify({'success': False, 'message': 'Missing draft_id.'}), 400

    try:
        draft_id = int(draft_id)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid draft_id.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.designated import update_oversight_draft_deadline
        success, msg = update_oversight_draft_deadline(
            conn, cursor, emp_id, draft_id, data.get('duration_value'), duration_unit)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@designated_bp.route('/submit_evidence', methods=['POST'])
@designated_ipcr_required
def designated_submit_evidence():
    emp_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            flash("No active term.", "danger")
            return redirect(url_for('designated.designated_dashboard'))

        term_id = active_term['term_id']
        from app.models.designated import submit_designated_evidences
        success, msg = submit_designated_evidences(conn, cursor, emp_id, term_id)
        if success:
            try:
                from app.services.notification_service import send_evidence_submission_notification
                send_evidence_submission_notification(conn, cursor, emp_id, int(term_id))
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering designated evidence notification: {notif_err}")
            flash(msg, "success")
        else:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error submitting evidences: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('designated.designated_dashboard'))



@designated_bp.route('/submit', methods=['POST'])
@designated_ipcr_required
def submit_designated_ipcr_route():
    emp_id = session.get('user_id')
    term_id = request.form.get('term_id')
    
    if not term_id:
        flash("No active academic term found.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    # Departmental Oversight rows (get_oversight_targets) render an `admin_indicator_ids[]`
    # marker in the template. Their indicator_id can be the *same* as a personal Core
    # Function row above (e.g. the chair's own Instruction share) — Table 1 always submits
    # that personal row's own selected_indicators[]/target_qty_<id>, so the same id can
    # legitimately appear twice in the form. Quantity/category for the oversight instance is
    # never trusted from the form regardless — see submit_designated_ipcr.
    admin_ids = {int(x) for x in request.form.getlist('admin_indicator_ids[]') if x}

    # Parse baseline target checkboxes. dict.fromkeys dedupes while keeping order: an id
    # shared between a personal Core row (Table 1's hidden field) and an oversight row
    # (Table 2's checkbox) must produce exactly one entry here, built from the single
    # target_qty_<id>/target_desc_<id>/target_dur_value_<id> fields Table 1 rendered for it —
    # Table 2 no longer renders those for oversight rows, so there's no second, conflicting
    # source to accidentally merge in.
    selected_ids = list(dict.fromkeys(request.form.getlist('selected_indicators[]')))
    selected_targets = []
    for ind_id in selected_ids:
        qty_val = request.form.get(f'target_qty_{ind_id}', '0')
        desc_val = request.form.get(f'target_desc_{ind_id}', '')
        # Explicit auto/customized flag from wireAutoDescription (base.html) — see Decision 1
        # in target_desc.md. Absent (None) falls back to inferring from blank-ness.
        raw_auto_flag = request.form.get(f'is_auto_description_{ind_id}')
        is_auto_flag = (raw_auto_flag == '1') if raw_auto_flag is not None else None
        # Structured duration drives Timeliness; the text label is derived from it.
        dur_value, dur_unit, dead_label = parse_duration_fields(
            request.form, f'target_dur_value_{ind_id}', f'target_dur_unit_{ind_id}')
        selected_targets.append({
            'indicator_id': int(ind_id),
            'proposed_quantity': int(qty_val) if qty_val.isdigit() else 1,
            'target_description': desc_val.strip(),
            'target_deadline': dead_label,
            'target_duration_value': dur_value,
            'target_duration_unit': dur_unit,
            'is_auto_description': is_auto_flag,
        })

    # Departmental Oversight deadlines — the chair's own input, kept in the `_adm`-suffixed
    # fields (see the template) so they never collide with a same-indicator Core Function row.
    oversight_durations = {}
    for ind_id in admin_ids:
        dur_value, dur_unit, dead_label = parse_duration_fields(
            request.form, f'target_dur_value_{ind_id}_adm', f'target_dur_unit_{ind_id}_adm')
        oversight_durations[ind_id] = {
            'target_duration_value': dur_value,
            'target_duration_unit': dur_unit,
            'target_deadline': dead_label,
        }

    # Parse custom targets added on the frontend
    custom_descriptions = request.form.getlist('custom_descriptions[]')
    custom_quantities = request.form.getlist('custom_quantities[]')
    custom_categories = request.form.getlist('custom_categories[]')
    custom_dur_values = request.form.getlist('custom_duration_values[]')
    custom_dur_units = request.form.getlist('custom_duration_units[]')

    custom_targets = []
    for idx, (desc, qty, cat) in enumerate(zip(custom_descriptions, custom_quantities, custom_categories)):
        if desc.strip():
            dur_value, dur_unit, dead_label = parse_duration_fields(
                {'v': custom_dur_values[idx] if idx < len(custom_dur_values) else None,
                 'u': custom_dur_units[idx] if idx < len(custom_dur_units) else None}, 'v', 'u')
            custom_targets.append({
                'description': desc.strip(),
                'proposed_quantity': int(qty) if str(qty).isdigit() else 1,
                'category_name': cat.strip(),
                'target_deadline': dead_label,
                'target_duration_value': dur_value,
                'target_duration_unit': dur_unit
            })

    # Validate that every selected target has a positive quantity and a specified deadline.
    # Departmental Oversight ids are skipped here regardless of whether they also have a
    # personal Core Function counterpart: a pure-oversight id has no target_qty_<id>/
    # target_dur_value_<id> fields at all (Table 2 doesn't render them for admin rows), so
    # they'd always fail this check; a dual id's Core Function fields are already guaranteed
    # valid by construction (Table 1 only shows an id here when its allocation is > 0). The
    # oversight deadline itself is validated separately below, from oversight_durations.
    for t in selected_targets:
        if t['indicator_id'] in admin_ids:
            continue
        if t.get('proposed_quantity', 0) <= 0:
            flash("All selected targets must have a quantity greater than 0.", "danger")
            return redirect(url_for('designated.designated_dashboard'))
        if not t.get('target_duration_value') or int(t['target_duration_value']) <= 0:
            flash("All selected targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('designated.designated_dashboard'))

    for ct in custom_targets:
        if ct.get('proposed_quantity', 0) <= 0:
            flash("All custom targets must have a quantity greater than 0.", "danger")
            return redirect(url_for('designated.designated_dashboard'))
        if not ct.get('target_duration_value') or int(ct['target_duration_value']) <= 0:
            flash("All custom targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('designated.designated_dashboard'))

    for ov in oversight_durations.values():
        if not ov.get('target_duration_value') or int(ov['target_duration_value']) <= 0:
            flash("All Departmental Oversight targets must have a valid deadline (target duration) specified.", "danger")
            return redirect(url_for('designated.designated_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        success, msg = submit_designated_ipcr(conn, cursor, emp_id, int(term_id), selected_targets, custom_targets,
                                               oversight_durations=oversight_durations)
        if success:
            try:
                from app.services.notification_service import send_designated_target_submission_notification
                send_designated_target_submission_notification(conn, cursor, emp_id, int(term_id), is_resubmission=False)
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering designated submission notification: {notif_err}")
            flash(msg, "success")
        else:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error submitting IPCR: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('designated.designated_dashboard'))


# ──────────────────────────────────────────────
# Process 6: Evidence Management Routes
# ──────────────────────────────────────────────

from flask import current_app
import uuid
import os
from werkzeug.utils import secure_filename

@designated_bp.route('/target_evidence/<int:target_id>/<int:indicator_id>')
@designated_ipcr_required
def designated_target_evidence(target_id, indicator_id):
    emp_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT ct.is_admin_function, mi.term_id
            FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.target_id = %s AND ct.emp_id = %s
        """, (target_id, emp_id))
        row = cursor.fetchone()
        if not row:
            # Also closes a pre-existing gap: this route never checked ownership of
            # target_id before returning its evidence_list, so any authenticated
            # designated-flow user could read another user's evidence by guessing ids.
            return jsonify({'success': False, 'message': 'Target not found.'}), 404

        is_oversight = False
        if row[0]:
            from app.models.designated import get_oversight_indicator_ids
            is_oversight = indicator_id in get_oversight_indicator_ids(cursor, emp_id, row[1])

        if is_oversight:
            from app.models.designated import get_oversight_evidence
            agg = get_oversight_evidence(cursor, emp_id, row[1], indicator_id)
            return jsonify({
                'success': True,
                'is_oversight': True,
                'total_actual_quantity': agg['total_actual_quantity'],
                'max_actual_duration_value': agg['max_actual_duration_value'],
                'breakdown': agg['evidence_breakdown'],
            })

        from app.models.faculty import get_evidence_by_target
        evidence_list = get_evidence_by_target(cursor, target_id)
        return jsonify({'success': True, 'is_oversight': False, 'evidence_list': evidence_list})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@designated_bp.route('/upload_evidence', methods=['POST'])
@designated_ipcr_required
def designated_upload_evidence():
    emp_id = session.get('user_id')
    target_id = request.form.get('target_id')
    quantity = request.form.get('quantity', '1')
    is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
               'application/json' in request.headers.get('Accept', ''))
    
    if not target_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid target ID.'}), 400
        flash("Invalid target ID.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    try:
        target_id_int = int(target_id)
    except (TypeError, ValueError):
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid target ID.'}), 400
        flash("Invalid target ID.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    # This route never verified target_id belonged to the requesting user before saving a
    # file against it -- closing that here (pre-existing, not introduced by the oversight
    # check below) rather than leaving a direct POST able to attach evidence to, and inflate
    # the accomplished quantity of, another employee's committed target.
    conn_check = get_db_connection()
    cursor_check = conn_check.cursor()
    try:
        cursor_check.execute("""
            SELECT ct.emp_id, ct.indicator_id, ct.is_admin_function, mi.term_id
            FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.target_id = %s
        """, (target_id_int,))
        row = cursor_check.fetchone()
        if not row or row[0] != emp_id:
            msg = "Invalid target."
            if is_ajax:
                return jsonify({'success': False, 'message': msg}), 404
            flash(msg, "danger")
            return redirect(url_for('designated.designated_dashboard'))

        # A Departmental Oversight row has no upload slot of its own -- its evidence is
        # linked automatically from the scoped faculty who did the real work (see
        # get_oversight_evidence, app/models/designated.py). The UI already hides this row's
        # upload form; this is the actual enforcement so a direct POST can't bypass it.
        if row[2]:
            from app.models.designated import get_oversight_indicator_ids
            if row[1] in get_oversight_indicator_ids(cursor_check, emp_id, row[3]):
                msg = ("This is a Departmental Oversight target -- evidence is linked automatically "
                       "from your department's/RET's faculty, not uploaded here.")
                if is_ajax:
                    return jsonify({'success': False, 'message': msg}), 400
                flash(msg, "danger")
                return redirect(url_for('designated.designated_dashboard'))
    finally:
        cursor_check.close()
        conn_check.close()

    try:
        qty_val = max(0, int(quantity))
    except ValueError:
        qty_val = 1

    file = request.files.get('file')
    if not file or file.filename == '':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please select a file to upload.'}), 400
        flash("Please select a file to upload.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    # Check file extension
    allowed_extensions = {'pdf'}
    filename = file.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in allowed_extensions:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unsupported file format. Allowed format: .pdf'}), 400
        flash("Unsupported file format. Allowed format: .pdf", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    # Save the file
    upload_dir = current_app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir, exist_ok=True)

    unique_filename = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
    file_path = os.path.join(upload_dir, unique_filename)
    file.save(file_path)

    relative_path = unique_filename

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.faculty import upload_evidence_item
        upload_evidence_item(cursor, target_id_int, relative_path, qty_val)
        conn.commit()
        if is_ajax:
            return jsonify({'success': True, 'message': 'Evidence uploaded successfully!'})
        flash("Evidence uploaded successfully!", "success")
    except Exception as e:
        conn.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': f"Error uploading evidence: {str(e)}"}), 500
        flash(f"Error uploading evidence: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('designated.designated_dashboard'))


@designated_bp.route('/delete_evidence', methods=['POST'])
@designated_ipcr_required
def designated_delete_evidence():
    evidence_id = request.form.get('evidence_id')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not evidence_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid evidence ID.'}), 400
        flash("Invalid evidence ID.", "danger")
        return redirect(url_for('designated.designated_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.faculty import delete_evidence_item
        success = delete_evidence_item(cursor, int(evidence_id), session.get('user_id'))
        if success:
            conn.commit()
            if is_ajax:
                return jsonify({'success': True, 'message': 'Evidence removed successfully.'})
            flash("Evidence removed successfully.", "success")
        else:
            if is_ajax:
                return jsonify({'success': False, 'message': 'Evidence item not found.'}), 404
            flash("Evidence item not found.", "danger")
    except Exception as e:
        conn.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': f"Error deleting evidence: {str(e)}"}), 500
        flash(f"Error deleting evidence: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('designated.designated_dashboard'))

@designated_bp.route('/print_ipcr')
@designated_ipcr_required
def designated_print_ipcr():
    """
    Printable IPCR for any designated faculty member — including Program Chairs, the RET
    Chair and the Dean, who reach it from their own dashboards.
    """
    from app.routes.faculty import _render_ipcr_print
    return _render_ipcr_print(session.get('user_id'),
                              url_for('designated.designated_dashboard'))
