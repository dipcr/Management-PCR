from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.models import *
from app.decorators import role_required

faculty_bp = Blueprint('faculty', __name__, url_prefix='/faculty')


@faculty_bp.route('/')
@role_required('FACULTY')
def faculty_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    from app.models.connection import timed_query

    try:
        emp_id = session.get('user_id')

        emp_result = timed_query(cursor, "SELECT academic_rank, specialization FROM tbl_employee_profiles WHERE emp_id = %s", (emp_id,), label="faculty_profile")
        academic_rank = emp_result[0]['academic_rank'] if emp_result else ''
        specialization = emp_result[0]['specialization'] if emp_result else ''

        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)

        assigned_targets = []
        ret_menu = {'required_selections': 0, 'indicators': []}
        has_submitted = False
        is_locked = False
        chair_review = None
        is_ret_eligible = False
        ret_assigned_ids = []
        extension_targets = []
        evidence_readiness = None
        ipcr_score = None
        has_final_ipcr = False
        gating_status = None
        evidence_sections = []

        if active_term:
            term_id = active_term['term_id']
            is_ret_eligible = is_faculty_ret_eligible(cursor, emp_id, term_id)
            if not is_faculty_resubmission(cursor, emp_id, term_id):
                gating_status = check_faculty_draft_gating(cursor, emp_id, term_id)
            assigned_targets = get_faculty_assigned_targets(cursor, emp_id, term_id)
            # Extension targets are locked/mandatory for the faculty's rank band, read-only,
            # and independent of Research eligibility — so the menu is fetched whenever the
            # faculty member has a rank, regardless of is_ret_eligible.
            if academic_rank:
                full_ret_menu = get_faculty_ret_menu(cursor, academic_rank, term_id)
                extension_targets = full_ret_menu['extension_indicators']
                if is_ret_eligible:
                    ret_menu = full_ret_menu
                    # Research targets directly assigned by the RET Chair — locked on the faculty side
                    cursor.execute(
                        """
                        SELECT ra.indicator_id FROM tbl_ret_assignments ra
                        JOIN tbl_master_indicators mi ON mi.indicator_id = ra.indicator_id
                        WHERE ra.emp_id = %s AND mi.term_id = %s
                        """,
                        (emp_id, term_id)
                    )
                    ret_assigned_ids = [r[0] for r in cursor.fetchall()]

            # Check if the faculty member has submitted
            sub_result = timed_query(cursor, """
                SELECT COUNT(*) as cnt
                FROM tbl_draft_targets dt
                JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
                WHERE dt.emp_id = %s AND mi.term_id = %s AND dt.review_status IN ('Pending Review', 'Waiting for Approval')
            """, (emp_id, term_id), label="faculty_submit_check")
            has_submitted = sub_result[0]['cnt'] > 0 if sub_result else False
            # Fetch the Program Chair's review decision (if any)
            chair_review = get_faculty_chair_review_status(cursor, emp_id, term_id)
            # Fetch the RET Chair's review decision (if any)
            ret_review = get_faculty_ret_review_status(cursor, emp_id, term_id)
            # Fetch the overall IPCR status (dynamically computed)
            from app.models.connection import get_overall_ipcr_status
            ipcr_status = get_overall_ipcr_status(cursor, emp_id, term_id)

            # Check if locked
            cursor.execute("""
                SELECT COUNT(*) FROM tbl_committed_targets ct
                JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
                WHERE ct.emp_id = %s AND mi.term_id = %s
            """, (emp_id, term_id))
            is_locked = cursor.fetchone()[0] > 0

            # Determine submission state based on overall status
            if ipcr_status == 'draft':
                has_submitted = False
            else:
                has_submitted = True

            if is_locked:
                has_submitted = True
                from app.models.faculty import get_faculty_committed_targets, get_evidence_by_target, check_faculty_evidence_readiness
                assigned_targets = get_faculty_committed_targets(cursor, emp_id, term_id)
                has_final_ipcr = any(t.get('status') == 'Dean Approved' for t in assigned_targets)
                # Fetch evidence for each target
                for target in assigned_targets:
                    target['evidence_list'] = get_evidence_by_target(cursor, target['target_id'])
                evidence_readiness = check_faculty_evidence_readiness(cursor, emp_id, term_id, assigned_targets)
                # Live IPCR summary (computed, not persisted — the record is written on finalize)
                from app.models.scoring import compute_ipcr_score
                ipcr_score = compute_ipcr_score(cursor, emp_id, term_id)
                # Same category -> target-type grouping as the printed IPCR, so the checklist
                # reads like the real form (Regular Faculty's own designation is always
                # 'Regular Faculty' -- chairs/Dean use the shared /designated/ flow instead).
                from app.models.ipcr_form import build_evidence_checklist_sections
                from app.models.criteria import DESIGNATION_REGULAR
                evidence_sections = build_evidence_checklist_sections(
                    cursor, assigned_targets, DESIGNATION_REGULAR, term_id, academic_rank)

        return render_template('faculty_dashboard.html',
                               active_term=active_term,
                               assigned_targets=assigned_targets,
                               ret_menu=ret_menu,
                               academic_rank=academic_rank,
                               specialization=specialization,
                               has_submitted=has_submitted,
                               is_locked=is_locked,
                               is_ret_eligible=is_ret_eligible,
                               ret_assigned_ids=ret_assigned_ids,
                               extension_targets=extension_targets,
                               chair_review=chair_review,
                               ret_review=ret_review,
                               ipcr_status=ipcr_status,
                               evidence_readiness=evidence_readiness,
                               ipcr_score=ipcr_score,
                               has_final_ipcr=has_final_ipcr,
                               gating_status=gating_status,
                               evidence_sections=evidence_sections)
    finally:
        cursor.close()
        conn.close()



@faculty_bp.route('/save_accomplishment', methods=['POST'])
@role_required('FACULTY')
def faculty_save_accomplishment():
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


@faculty_bp.route('/submit_evidence', methods=['POST'])
@role_required('FACULTY')
def faculty_submit_evidence():
    emp_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            flash("No active term.", "danger")
            return redirect(url_for('faculty.faculty_dashboard'))

        term_id = active_term['term_id']
        from app.models.faculty import submit_faculty_evidences
        success, msg = submit_faculty_evidences(conn, cursor, emp_id, term_id)
        if success:
            try:
                from app.services.notification_service import send_evidence_submission_notification
                send_evidence_submission_notification(conn, cursor, emp_id, int(term_id))
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering evidence submission notification: {notif_err}")
            flash(msg, "success")
        else:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error submitting evidences: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('faculty.faculty_dashboard'))

@faculty_bp.route('/submit_ipcr', methods=['POST'])
@role_required('FACULTY')
def faculty_submit_ipcr():
    emp_id = session.get('user_id')
    term_id = request.form.get('term_id')
    selected_indicators = request.form.getlist('ret_indicators[]')

    if not term_id:
        flash("No active term.", "danger")
        return redirect(url_for('faculty.faculty_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check if already locked or approved
        cursor.execute("""
            SELECT COUNT(*) FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))
        is_locked = cursor.fetchone()[0] > 0

        cursor.execute("""
            SELECT overall_status FROM tbl_ipcr_chair_review
            WHERE emp_id = %s AND term_id = %s
        """, (emp_id, term_id))
        review_row = cursor.fetchone()
        is_approved = review_row and review_row[0] == 'Approved'

        if is_locked or is_approved:
            flash("Your IPCR has already been approved/locked and cannot be re-submitted.", "danger")
            return redirect(url_for('faculty.faculty_dashboard'))

        if not is_faculty_resubmission(cursor, emp_id, int(term_id)):
            gating_status = check_faculty_draft_gating(cursor, emp_id, int(term_id))
            if not gating_status['can_submit']:
                flash("Submission blocked: " + "; ".join(gating_status['missing_reasons']), "warning")
                return redirect(url_for('faculty.faculty_dashboard'))

        # Construct research targets payload (proposed_quantity=1 per selection)
        selected_ret_targets = [{'indicator_id': int(x), 'proposed_quantity': 1} for x in selected_indicators]

        # Call submit pipeline (handles writing both chair allocations and RET selections to tbl_draft_targets)
        success, msg = submit_faculty_ipcr(conn, cursor, emp_id, int(term_id), selected_ret_targets)
        print(f"[SUBMIT IPCR ROUTE] submit_faculty_ipcr result: success={success}, msg={msg}, emp_id={emp_id}, term_id={term_id}", flush=True)

        if success:
            try:
                from app.services.notification_service import send_target_submission_notification
                send_target_submission_notification(conn, cursor, emp_id, int(term_id))
            except Exception as notif_err:
                import logging
                logging.getLogger(__name__).error(f"Error triggering target submission notification: {notif_err}")
                print(f"[SUBMIT IPCR NOTIF ERR] {notif_err}", flush=True)
            flash(msg, "success")
        else:
            flash(msg, "danger")

    except Exception as e:
        flash(f"Error submitting IPCR: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('faculty.faculty_dashboard'))


@faculty_bp.route('/lock_ipcr', methods=['POST'])
@role_required('FACULTY')
def faculty_lock_ipcr():
    emp_id = session.get('user_id')
    term_id = request.form.get('term_id')

    if not term_id:
        flash("No active term.", "danger")
        return redirect(url_for('faculty.faculty_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if already locked
        cursor.execute("""
            SELECT COUNT(*) FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
            WHERE ct.emp_id = %s AND mi.term_id = %s
        """, (emp_id, term_id))
        is_locked = cursor.fetchone()[0] > 0
        if is_locked:
            flash("Your IPCR is already locked.", "warning")
            return redirect(url_for('faculty.faculty_dashboard'))

        # Verify it is approved by chair before locking
        cursor.execute("""
            SELECT overall_status FROM tbl_ipcr_chair_review
            WHERE emp_id = %s AND term_id = %s
        """, (emp_id, term_id))
        row = cursor.fetchone()
        is_approved = row and row[0] == 'Approved'
        if not is_approved:
            flash("Your IPCR must be approved by the Program Chair before locking.", "danger")
            return redirect(url_for('faculty.faculty_dashboard'))

        success, msg = lock_and_commit_ipcr(conn, cursor, emp_id, int(term_id))
        if success:
            flash("IPCR locked successfully and committed to evaluation targets.", "success")
        else:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error locking IPCR: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('faculty.faculty_dashboard'))


# ──────────────────────────────────────────────
# Process 6: Evidence Management Routes
# ──────────────────────────────────────────────

from flask import current_app, jsonify
import uuid
import os
from werkzeug.utils import secure_filename

@faculty_bp.route('/upload_evidence', methods=['POST'])
@role_required('FACULTY')
def faculty_upload_evidence():
    emp_id = session.get('user_id')
    target_id = request.form.get('target_id')
    quantity = request.form.get('quantity', '1')
    is_ajax = (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
               'application/json' in request.headers.get('Accept', ''))
    
    if not target_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid target ID.'}), 400
        flash("Invalid target ID.", "danger")
        return redirect(url_for('faculty.faculty_dashboard'))
        
    try:
        qty_val = max(0, int(quantity))
    except ValueError:
        qty_val = 1

    file = request.files.get('file')
    if not file or file.filename == '':
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please select a file to upload.'}), 400
        flash("Please select a file to upload.", "danger")
        return redirect(url_for('faculty.faculty_dashboard'))

    # Check file extension
    allowed_extensions = {'pdf'}
    filename = file.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in allowed_extensions:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Unsupported file format. Allowed format: .pdf'}), 400
        flash("Unsupported file format. Allowed format: .pdf", "danger")
        return redirect(url_for('faculty.faculty_dashboard'))

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
        upload_evidence_item(cursor, int(target_id), relative_path, qty_val)
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

    return redirect(url_for('faculty.faculty_dashboard'))


@faculty_bp.route('/delete_evidence', methods=['POST'])
@role_required('FACULTY')
def faculty_delete_evidence():
    evidence_id = request.form.get('evidence_id')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
    if not evidence_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Invalid evidence ID.'}), 400
        flash("Invalid evidence ID.", "danger")
        return redirect(url_for('faculty.faculty_dashboard'))

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
                return jsonify({'success': False, 'message': 'Evidence item not found.'}), 44
            flash("Evidence item not found.", "danger")
    except Exception as e:
        conn.rollback()
        if is_ajax:
            return jsonify({'success': False, 'message': str(e)}), 500
        flash(f"Error deleting evidence: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('faculty.faculty_dashboard'))


@faculty_bp.route('/target_evidence/<int:target_id>/<int:indicator_id>')
@role_required('FACULTY')
def faculty_target_evidence(target_id, indicator_id):
    emp_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.models.faculty import get_evidence_by_target
        evidence_list = get_evidence_by_target(cursor, target_id)
        return jsonify({'success': True, 'evidence_list': evidence_list})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@faculty_bp.route('/print_ipcr')
@role_required('FACULTY')
def faculty_print_ipcr():
    """Printable IPCR for the logged-in faculty member's active term."""
    return _render_ipcr_print(session.get('user_id'), url_for('faculty.faculty_dashboard'))


def _render_ipcr_print(emp_id, back_url):
    from app.models.ipcr_form import build_ipcr_form
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        if not active_term:
            flash('No active academic term.', 'warning')
            return redirect(back_url)

        form = build_ipcr_form(cursor, emp_id, active_term['term_id'])
        if not form or not form['has_targets']:
            flash('No committed IPCR to print yet — lock your IPCR first.', 'warning')
            return redirect(back_url)

        return render_template('ipcr_print.html', form=form, back_url=back_url)
    finally:
        cursor.close()
        conn.close()


@faculty_bp.route('/test_ret_mail')
def test_ret_mail():
    """Diagnostic route to test sending email directly to RET Chair."""
    from app.services.mail_service import _send_email_sync
    recipient = "corazonlopez062041@gmail.com"
    subject = "[D-IPCR TEST] Action Required: Review IPCR Research Targets - RET Chair Test"
    html_body = """
    <div style="font-family: Arial, sans-serif; padding: 20px; color: #333;">
        <h3 style="color: #2b6cb0;">[D-IPCR] Direct Delivery Verification</h3>
        <p>Dear RET Chair,</p>
        <p>This is a real-time diagnostic test confirming that your inbox <strong>corazonlopez062041@gmail.com</strong> receives D-IPCR system notifications properly.</p>
        <p>If you see this email, notification delivery to the RET Chair is fully operational!</p>
    </div>
    """
    text_body = "This is a direct test email confirming delivery to corazonlopez062041@gmail.com."
    
    success, message = _send_email_sync(
        subject=subject,
        recipients=[recipient],
        html_body=html_body,
        text_body=text_body
    )
    return {
        'status': 'SUCCESS' if success else 'FAILED',
        'recipient': recipient,
        'message': message
    }


@faculty_bp.route('/rollback_faculty/<email>')
def rollback_faculty(email):
    """Rolls back a faculty account to the pristine target-selection state."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Find employee ID
        cursor.execute("""
            SELECT emp_id FROM tbl_auth_credentials 
            WHERE corporate_email = %s
        """, (email,))
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': f'Account {email} not found.'}
        
        emp_id = row[0]

        # 2. Delete review items & headers
        cursor.execute("DELETE ri FROM tbl_ipcr_chair_review_items ri JOIN tbl_ipcr_chair_review cr ON ri.review_id = cr.review_id WHERE cr.emp_id = %s", (emp_id,))
        cursor.execute("DELETE FROM tbl_ipcr_chair_review WHERE emp_id = %s", (emp_id,))

        cursor.execute("DELETE ri FROM tbl_ipcr_ret_review_items ri JOIN tbl_ipcr_ret_review rr ON ri.review_id = rr.review_id WHERE rr.emp_id = %s", (emp_id,))
        cursor.execute("DELETE FROM tbl_ipcr_ret_review WHERE emp_id = %s", (emp_id,))

        # 3. Delete evidence files and committed targets
        cursor.execute("DELETE er FROM tbl_evidence_repo er JOIN tbl_committed_targets ct ON er.target_id = ct.target_id WHERE ct.emp_id = %s", (emp_id,))
        cursor.execute("DELETE FROM tbl_committed_targets WHERE emp_id = %s", (emp_id,))

        # 4. Delete all draft targets so faculty can start fresh with target selection
        cursor.execute("DELETE FROM tbl_draft_targets WHERE emp_id = %s", (emp_id,))

        conn.commit()
        return {
            'success': True,
            'email': email,
            'emp_id': emp_id,
            'message': f'Account {email} (emp_id={emp_id}) rolled back to research target selection state successfully.'
        }
    except Exception as e:
        conn.rollback()
        return {'success': False, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


@faculty_bp.route('/test_dean_package_mail')
def test_dean_package_mail():
    """Diagnostic route to send a sample evidence package submission email to the Dean."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.notification_service import _get_dean_info, _get_base_url
        from app.services.mail_service import _send_email_sync
        
        dean_info = _get_dean_info(cursor)
        dean_email = dean_info.get('email') or 'deanacccount@gmail.com'
        dean_name = dean_info.get('name') or 'College Dean'
        
        resolved_base_url = _get_base_url(None)
        dean_url = f"{resolved_base_url}/dean"
        
        html_dean = render_template('emails/evidence_package_to_dean.html',
            recipient_name=dean_name,
            faculty_name="Ruka Kayamori (Designated Faculty)",
            department="WST Program",
            chair_name="WST Program Chair",
            period_display="A.Y. 2044-2045 (2nd Semester) [Jan 2045 - Jul 2045]",
            is_for_dean=True,
            action_url=dean_url
        )
        text_dean = (
            f"Dear {dean_name},\n\n"
            f"Program Chair WST Program Chair has verified all accomplishment evidence for Ruka Kayamori "
            f"(WST Program) for A.Y. 2044-2045 (2nd Semester) [Jan 2045 - Jul 2045] and submitted the package for your final Tier 2 approval.\n\n"
            f"Review at: {dean_url}\n"
        )
        success, message = _send_email_sync(
            subject="[D-IPCR] Action Required: Evidence Package Submitted for Final Approval - Ruka Kayamori (A.Y. 2044-2045 (2nd Semester))",
            recipients=[dean_email],
            html_body=html_dean,
            text_body=text_dean
        )
        return {
            'status': 'SUCCESS' if success else 'FAILED',
            'recipient': dean_email,
            'message': message
        }
    finally:
        cursor.close()
        conn.close()


@faculty_bp.route('/test_ret_chair_targets_mail')
def test_ret_chair_targets_mail():
    """Diagnostic route to send sample RET Chair target submission email to Dean."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.mail_service import _send_email_sync
        from app.services.notification_service import _get_dean_info, _get_base_url
        
        dean_info = _get_dean_info(cursor)
        dean_email = dean_info.get('email') or 'deanacccount@gmail.com'
        dean_name = dean_info.get('name') or 'College Dean'
        
        resolved_base_url = _get_base_url(None)
        action_url = f"{resolved_base_url}/dean"

        faculty_name = "Corazon Lopez"
        sender_title = "RET Chair"
        academic_rank = "Associate Professor IV"
        department = "Research & Extension Services"
        period_display = "A.Y. 2044-2045 (2nd Semester) [Jan 2045 - Jul 2045]"
        review_stage = "Dean Review for RET Chair Targets"

        html_body = render_template('emails/target_submission_notice.html',
            reviewer_name=dean_name,
            faculty_name=faculty_name,
            sender_title=sender_title,
            designation=sender_title,
            academic_rank=academic_rank,
            department=department,
            period_display=period_display,
            review_stage=review_stage,
            action_url=action_url
        )
        text_body = (
            f"Dear {dean_name},\n\n"
            f"{sender_title} {faculty_name} ({department}) has submitted draft IPCR targets for {period_display} for your review.\n\n"
            f"Review at: {action_url}\n"
        )
        success, message = _send_email_sync(
            subject=f"[D-IPCR] Action Required: {sender_title} IPCR Targets Submitted - {faculty_name} ({period_display})",
            recipients=[dean_email],
            html_body=html_body,
            text_body=text_body
        )
        return {
            'status': 'SUCCESS' if success else 'FAILED',
            'recipient': dean_email,
            'message': message
        }
    finally:
        cursor.close()
        conn.close()


@faculty_bp.route('/test_designated_tier2_mail')
def test_designated_tier2_mail():
    """Diagnostic route to send sample final score approval email to Designated Faculty."""
    from app.services.mail_service import _send_email_sync
    from app.services.notification_service import _get_base_url
    
    recipient = "mitsuhataki153@gmail.com"
    faculty_name = "Ruka Kayamori"
    academic_rank = "Instructor I (Designated Faculty)"
    department = "WST Program"
    period_display = "A.Y. 2044-2045 (2nd Semester) [Jan 2045 - Jul 2045]"
    final_score = "4.2500"
    adjectival_rating = "Very Satisfactory"
    resolved_base_url = _get_base_url(None)
    action_url = f"{resolved_base_url}/designated/print_ipcr"

    html_body = render_template('emails/tier2_final.html',
        recipient_name=faculty_name,
        faculty_name=faculty_name,
        academic_rank=academic_rank,
        department=department,
        period_display=period_display,
        final_score=final_score,
        adjectival_rating=adjectival_rating,
        action_url=action_url
    )
    text_body = (
        f"Dear {faculty_name},\n\n"
        f"Your IPCR for {period_display} has been approved by the College Dean and is ready for print.\n"
        f"Final Score: {final_score} ({adjectival_rating})\n\n"
        f"View and print your finalized IPCR at: {action_url}\n"
    )
    success, message = _send_email_sync(
        subject=f"[D-IPCR] IPCR is approved by Dean and is ready for print - {faculty_name} ({period_display})",
        recipients=[recipient],
        html_body=html_body,
        text_body=text_body
    )
    return {
        'status': 'SUCCESS' if success else 'FAILED',
        'recipient': recipient,
        'message': message
    }


@faculty_bp.route('/test_ret_chair_evidence_mail')
def test_ret_chair_evidence_mail():
    """Diagnostic route to send sample RET Chair evidence submission email to Dean."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.mail_service import _send_email_sync
        from app.services.notification_service import _get_dean_info, _get_base_url
        
        dean_info = _get_dean_info(cursor)
        dean_email = dean_info.get('email') or 'deanacccount@gmail.com'
        dean_name = dean_info.get('name') or 'College Dean'
        
        resolved_base_url = _get_base_url(None)
        action_url = f"{resolved_base_url}/dean"

        faculty_name = "Ivan Fajardo"
        sender_title = "RET Chair"
        academic_rank = "Associate Professor III"
        department = "Research & Extension Services"
        period_display = "A.Y. 2044-2045 (2nd Semester) [Jan 2045 - Jul 2045]"

        html_body = render_template('emails/evidence_submission_notice.html',
            reviewer_name=dean_name,
            faculty_name=faculty_name,
            sender_title=sender_title,
            designation=sender_title,
            academic_rank=academic_rank,
            department=department,
            period_display=period_display,
            action_url=action_url
        )
        text_body = (
            f"Dear {dean_name},\n\n"
            f"{sender_title} {faculty_name} ({department}) has submitted accomplishment evidence files for {period_display} and is awaiting your verification.\n\n"
            f"Verify at: {action_url}\n"
        )
        success, message = _send_email_sync(
            subject=f"[D-IPCR] Evidence Submitted for Verification - {sender_title} {faculty_name} ({period_display})",
            recipients=[dean_email],
            html_body=html_body,
            text_body=text_body
        )
        return {
            'status': 'SUCCESS' if success else 'FAILED',
            'recipient': dean_email,
            'message': message
        }
    finally:
        cursor.close()
        conn.close()


@faculty_bp.route('/test_chair_approved_first_mail')
def test_chair_approved_first_mail():
    """Diagnostic route to test sending Program Chair evidence approval notice to casptone@gmail.com."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        from app.services.mail_service import _send_email_sync
        from app.services.notification_service import _get_base_url

        recipient = request.args.get('email', 'casptone@gmail.com')
        faculty_name = "wst googletest"
        department = "WST Program"
        period_display = "A.Y. 2045-2046 (1st Semester) [Aug 2045 - Dec 2045]"
        resolved_base_url = _get_base_url(None)
        action_url = f"{resolved_base_url}/faculty"

        html_body = render_template('emails/chair_evidence_approved.html',
            faculty_name=faculty_name,
            department=department,
            reviewer_role="Program Chair",
            scope_desc="Strategic Priorities & Support",
            pending_reviewer="RET Chair",
            pending_scope="Research & Extension",
            period_display=period_display,
            action_url=action_url
        )
        text_body = (
            f"Dear {faculty_name},\n\n"
            f"Good news! Your submitted Strategic Priorities & Support evidence files for {period_display} have been "
            f"reviewed and approved by the Program Chair.\n\n"
            f"Evidence verification for Research & Extension by the RET Chair is currently in progress.\n\n"
            f"View dashboard at: {action_url}\n"
        )
        success, message = _send_email_sync(
            subject=f"[D-IPCR] Strategic Priorities & Support Evidences Approved by Program Chair - {period_display}",
            recipients=[recipient],
            html_body=html_body,
            text_body=text_body
        )
        return {
            'status': 'SUCCESS' if success else 'FAILED',
            'recipient': recipient,
            'message': message
        }
    finally:
        cursor.close()
        conn.close()

