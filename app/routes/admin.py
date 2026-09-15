from flask import Blueprint, render_template, request, redirect, session, url_for, flash, Response
from app.models import *
from app.decorators import role_required
from app.auth import hash_pass
import io, csv, secrets, string, datetime, re

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.route('/')
@role_required('ADMIN')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        profiles = get_all_profiles(cursor)
        terms = get_all_terms(cursor)
        active_term = next((t for t in terms if t['is_active'] == 1), None)
        indicators = get_master_indicators(cursor, active_term['term_id']) if active_term else []
        criteria = get_all_criteria(cursor)
        category_scopes = CATEGORY_SCOPES
        ipcr_categories = {scope: get_ipcr_categories(cursor, scope, active_only=False) for scope in CATEGORY_SCOPES}
        category_types = {scope: get_category_type_map(cursor, scope) for scope in CATEGORY_SCOPES}
        weights_grid = {
            dt: (get_criteria_weights_grid(cursor, active_term['term_id'], dt) if active_term else {})
            for dt in DESIGNATION_TYPES
        }
        weights_mode = {
            dt: (get_weights_mode(cursor, active_term['term_id'], dt) if active_term else MODE_GENERAL)
            for dt in DESIGNATION_TYPES
        }
        departments = get_departments(cursor, active_only=False)
        institution = get_institution_settings(cursor)
        # conn lets the panel recreate the standard blocks if the table was emptied.
        signatories = get_signatories(cursor, conn)
        teaching_load = {
            dt: (get_teaching_load_grid(cursor, active_term['term_id'], dt) if active_term else {})
            for dt in DESIGNATION_TYPES
        }
        teaching_load_mode = {
            dt: (get_teaching_load_mode(cursor, active_term['term_id'], dt) if active_term else 'GENERAL')
            for dt in DESIGNATION_TYPES
        }
        audit_logs = get_recent_audit_logs(cursor)
        security_users = get_all_users_for_security(cursor)
        kpis = get_admin_kpis(cursor)
        pending_claims = get_pending_account_claims(cursor)
        return render_template('admin_dashboard.html', profiles=profiles, terms=terms, active_term=active_term,
                               indicators=indicators, criteria=criteria,
                               category_scopes=category_scopes,
                               ipcr_categories=ipcr_categories, category_types=category_types,
                               weights_grid=weights_grid, weights_mode=weights_mode,
                               departments=departments, institution=institution,
                               signatories=signatories,
                               signatory_labels=SIGNATORY_BLOCK_LABELS,
                               signatory_sources=SIGNATORY_SOURCES,
                               teaching_load=teaching_load,
                               teaching_load_mode=teaching_load_mode,
                               rank_bands=RANK_BANDS, general_band=GENERAL_BAND,
                               designation_types=DESIGNATION_TYPES, audit_logs=audit_logs,
                               security_users=security_users, kpis=kpis,
                               pending_claims=pending_claims)
    finally:
        cursor.close()
        conn.close()


@admin_bp.route('/backup')
@role_required('ADMIN')
def admin_backup():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]

        output = io.StringIO()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        output.write(f"-- D-IPCR IPCR System Database Backup\n")
        output.write(f"-- Generated: {timestamp}\n")
        output.write(f"-- Database: ipcr_db\n\n")
        output.write("SET FOREIGN_KEY_CHECKS=0;\n\n")

        for table in tables:
            cursor.execute(f"SELECT * FROM `{table}`")
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]

            output.write(f"-- Table: {table}\n")
            output.write(f"TRUNCATE TABLE `{table}`;\n")

            if rows:
                cols = ', '.join(f'`{c}`' for c in col_names)
                output.write(f"INSERT INTO `{table}` ({cols}) VALUES\n")
                value_rows = []
                for row in rows:
                    vals = []
                    for v in row:
                        if v is None:
                            vals.append('NULL')
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        elif isinstance(v, (datetime.date, datetime.datetime)):
                            vals.append(f"'{v}'")
                        else:
                            escaped = str(v).replace("'", "''")
                            vals.append(f"'{escaped}'")
                    value_rows.append(f"  ({', '.join(vals)})")
                output.write(',\n'.join(value_rows) + ";\n")
            output.write("\n")

        output.write("SET FOREIGN_KEY_CHECKS=1;\n")

        filename = f"ipcr_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        return Response(
            output.getvalue(),
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename={filename}'}
        )

    except Exception as e:
        flash(f"Backup failed: {str(e)}", "danger")
        return redirect(url_for('admin.admin_dashboard'))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@admin_bp.route('/open_term', methods=['POST'])
@role_required('ADMIN')
def admin_open_term():
    academic_year = request.form.get('academic_year', '').strip()
    semester = request.form.get('semester')
    period_start = request.form.get('period_start')
    period_end = request.form.get('period_end')

    match = re.match(r'^(\d{4})\s*-\s*(\d{4})$', academic_year)
    if not match or int(match.group(2)) != int(match.group(1)) + 1 or not (2000 <= int(match.group(1)) <= 2099):
        flash("Invalid Academic Year format. Please use consecutive years in YYYY - YYYY format (e.g., 2025 - 2026).", "danger")
        return redirect(url_for('admin.admin_dashboard'))
    academic_year = f"{match.group(1)} - {match.group(2)}"

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        open_new_term(conn, cursor, academic_year, semester,
                      period_start, period_end)
        log_audit_action(conn, cursor, session.get('user_id'), 'Term Opened',
                         f"New term opened: {academic_year} {semester}",
                         request.remote_addr)
        flash("New Academic Term opened successfully.", "success")
    except Exception as e:
        flash(f"Error opening term: {e}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/faculty/save', methods=['POST'])
@role_required('ADMIN')
def save_faculty():
    data = {
        'employee_id_number': request.form.get('employee_id_number'),
        'first_name': request.form.get('first_name'),
        'last_name': request.form.get('last_name'),
        'college': request.form.get('college'),
        'assigned_program': request.form.get('assigned_program'),
        'specialization': request.form.get('specialization'),
        'academic_rank': request.form.get('academic_rank'),
        'employment_status': request.form.get('employment_status'),
        'leave_status': request.form.get('leave_status'),
        'designation': request.form.get('designation') or None
    }

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT emp_id FROM tbl_employee_profiles WHERE employee_id_number = %s",
            (data['employee_id_number'],))
        existed = cursor.fetchone() is not None
        save_single_profile(conn, cursor, data)
        cursor.execute(
            "SELECT emp_id FROM tbl_employee_profiles WHERE employee_id_number = %s",
            (data['employee_id_number'],))
        row = cursor.fetchone()
        emp_id = row[0] if row else None
        log_audit_action(conn, cursor, session.get('user_id'),
                         'Profile Updated' if existed else 'Profile Created',
                         f"{'Updated' if existed else 'Created'} profile {data['employee_id_number']} "
                         f"({data['first_name']} {data['last_name']}, designation: {data['designation'] or '-'}).",
                         request.remote_addr)
        flash("Faculty profile saved successfully.", "success")
    except Exception as e:
        flash(f"Error saving profile: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/account_claims/approve', methods=['POST'])
@role_required('ADMIN')
def approve_claim():
    emp_id = request.form.get('emp_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if approve_account_claim(conn, cursor, emp_id):
            log_audit_action(conn, cursor, session.get('user_id'), 'Account Claim Approved',
                             f"Approved account claim for emp_id {emp_id}.", request.remote_addr)
            flash("Account claim approved. The user may now sign in.", "success")
        else:
            flash("No pending claim found for that account.", "danger")
    except Exception as e:
        flash(f"Error approving claim: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/account_claims/deny', methods=['POST'])
@role_required('ADMIN')
def deny_claim():
    emp_id = request.form.get('emp_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if deny_account_claim(conn, cursor, emp_id):
            log_audit_action(conn, cursor, session.get('user_id'), 'Account Claim Denied',
                             f"Denied and removed account claim for emp_id {emp_id}.", request.remote_addr)
            flash("Account claim denied and removed. The person may claim again.", "success")
        else:
            flash("No pending claim found for that account.", "danger")
    except Exception as e:
        flash(f"Error denying claim: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/faculty/toggle_status', methods=['POST'])
@role_required('ADMIN')
def toggle_status():
    emp_id = request.form.get('employee_id_number')
    if not emp_id:
        flash("Employee ID missing.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        new_status = toggle_profile_status(conn, cursor, emp_id)
        if new_status:
            flash(f"Profile status updated to {new_status}.", "success")
        else:
            flash("Profile not found.", "danger")
    except Exception as e:
        flash(f"Error toggling status: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/csv/import', methods=['POST'])
@role_required('ADMIN')
def import_csv():
    if 'csv_file' not in request.files:
        flash("No file part.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    file = request.files['csv_file']
    if file.filename == '':
        flash("No selected file.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    if not file.filename.endswith('.csv'):
        flash("File must be a CSV.", "danger")
        return redirect(url_for('admin.admin_dashboard'))

    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        rows = list(csv_reader)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            success, new_added, updated, unchanged = import_csv_roster(conn, cursor, rows)
            if success:
                log_audit_action(conn, cursor, session.get('user_id'), 'CSV Roster Import',
                                 f"Import complete: {new_added} added, {updated} updated, {unchanged} unchanged.",
                                 request.remote_addr)
        finally:
            cursor.close()
            conn.close()

        if success:
            flash(f"CSV Import Complete: {new_added} New Hires Added, {updated} Profiles Updated, {unchanged} Unchanged.",
                  "success")
        else:
            flash(f"Error importing CSV: {new_added}", "danger")
    except Exception as e:
        flash(f"Error reading CSV file: {str(e)}", "danger")

    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/indicators/add', methods=['POST'])
@role_required('ADMIN')
def admin_add_indicator():
    term_id = request.form.get('term_id')
    category_name = request.form.get('category_name')
    description = request.form.get('description')
    efficiency_type = request.form.get('efficiency_type')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        add_master_indicator(conn, cursor, category_name, description, efficiency_type, term_id)
        flash("Master Indicator added successfully.", "success")
    except Exception as e:
        flash(f"Error adding indicator: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-indicators')


@admin_bp.route('/indicators/edit', methods=['POST'])
@role_required('ADMIN')
def admin_edit_indicator():
    indicator_id = request.form.get('indicator_id')
    category_name = request.form.get('category_name')
    description = request.form.get('description')
    efficiency_type = request.form.get('efficiency_type')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        edit_master_indicator(conn, cursor, indicator_id, category_name, description, efficiency_type)
        flash("Master Indicator updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating indicator: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-indicators')


@admin_bp.route('/indicators/delete', methods=['POST'])
@role_required('ADMIN')
def admin_delete_indicator():
    indicator_id = request.form.get('indicator_id')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        delete_master_indicator(conn, cursor, indicator_id)
        flash("Master Indicator deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting indicator: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-indicators')


@admin_bp.route('/indicators/import', methods=['POST'])
@role_required('ADMIN')
def admin_import_indicators():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        active_term_id = request.form.get('term_id')
        success, message = import_previous_term_indicators(conn, cursor, active_term_id)
        flash(message, "success" if success else "warning")
    except Exception as e:
        flash(f"Error importing indicators: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-indicators')


@admin_bp.route('/criteria/add', methods=['POST'])
@role_required('ADMIN')
def admin_add_criteria():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = add_criteria(
            conn, cursor,
            request.form.get('name'),
            request.form.get('slug'),
            request.form.get('review_lane'),
        )
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error adding criterion: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/criteria/edit', methods=['POST'])
@role_required('ADMIN')
def admin_edit_criteria():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = update_criteria(
            conn, cursor,
            request.form.get('category_id'),
            request.form.get('name'),
            request.form.get('review_lane'),
        )
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error updating criterion: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/criteria/reorder', methods=['POST'])
@role_required('ADMIN')
def admin_reorder_criteria():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = reorder_criteria(
            conn, cursor, request.form.get('category_id'), request.form.get('direction'))
        if not success:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error reordering criterion: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/criteria/toggle_active', methods=['POST'])
@role_required('ADMIN')
def admin_toggle_criteria():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        is_active = request.form.get('is_active') == '1'
        success, msg = set_criteria_active(conn, cursor, request.form.get('category_id'), is_active)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error updating criterion status: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/categories/save', methods=['POST'])
@role_required('ADMIN')
def admin_save_category():
    """Create or update an IPCR category and its assigned target types."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = save_ipcr_category(
            conn, cursor,
            request.form.get('designation_type'),
            request.form.get('category_name'),
            request.form.getlist('type_ids[]'),
            request.form.get('ipcr_category_id') or None,
        )
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving category: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/categories/reorder', methods=['POST'])
@role_required('ADMIN')
def admin_reorder_category():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = reorder_ipcr_category(
            conn, cursor, request.form.get('ipcr_category_id'), request.form.get('direction'))
        if not success:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error reordering category: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/categories/toggle_active', methods=['POST'])
@role_required('ADMIN')
def admin_toggle_category():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        is_active = request.form.get('is_active') == '1'
        success, msg = set_ipcr_category_active(conn, cursor,
                                                request.form.get('ipcr_category_id'), is_active)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error updating category status: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/institution/save', methods=['POST'])
@role_required('ADMIN')
def admin_save_institution():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        ok = True
        for key in ('college_full_name', 'college_code'):
            if key in request.form:
                success, msg = save_institution_setting(conn, cursor, key, request.form.get(key))
                ok = ok and success
        flash("Institution details saved." if ok else "Some settings could not be saved.",
              "success" if ok else "danger")
    except Exception as e:
        flash(f"Error saving institution details: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-institution')


@admin_bp.route('/signatories/save', methods=['POST'])
@role_required('ADMIN')
def admin_save_signatories():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        saved, failed = 0, []
        for sig in get_signatories(cursor):
            sid = sig['signatory_id']
            success, msg = save_signatory(
                conn, cursor, sid,
                request.form.get(f'sig_{sid}_source'),
                request.form.get(f'sig_{sid}_name'),
                request.form.get(f'sig_{sid}_title'),
            )
            if success:
                saved += 1
            else:
                failed.append(msg)
        if failed:
            flash("; ".join(dict.fromkeys(failed)), "danger")
        else:
            flash(f"Signatories saved ({saved} blocks).", "success")
    except Exception as e:
        flash(f"Error saving signatories: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-institution')


@admin_bp.route('/departments/save', methods=['POST'])
@role_required('ADMIN')
def admin_save_department():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = save_department(
            conn, cursor,
            request.form.get('department_name'),
            request.form.get('department_code'),
            request.form.get('department_id') or None,
        )
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving department: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-institution')


@admin_bp.route('/departments/reorder', methods=['POST'])
@role_required('ADMIN')
def admin_reorder_department():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = reorder_department(
            conn, cursor, request.form.get('department_id'), request.form.get('direction'))
        if not success:
            flash(msg, "danger")
    except Exception as e:
        flash(f"Error reordering department: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-institution')


@admin_bp.route('/departments/toggle_active', methods=['POST'])
@role_required('ADMIN')
def admin_toggle_department():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        is_active = request.form.get('is_active') == '1'
        success, msg = set_department_active(conn, cursor, request.form.get('department_id'), is_active)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error updating department: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-institution')


@admin_bp.route('/teaching_load/save', methods=['POST'])
@role_required('ADMIN')
def admin_save_teaching_load():
    term_id = request.form.get('term_id')
    designation_type = request.form.get('designation_type')
    mode = request.form.get('mode', 'GENERAL')
    if not term_id or designation_type not in DESIGNATION_TYPES:
        flash("No term or designation type specified.", "danger")
        return redirect(url_for('admin.admin_dashboard') + '#nav-institution')

    def _int(field, default=0):
        try:
            return int(request.form.get(field) or default)
        except (TypeError, ValueError):
            return default

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        rows = []
        if mode == 'GENERAL':
            rows.append((GENERAL_BAND, _int('tl_general_hours'),
                         _int('tl_general_duration', 6),
                         request.form.get('tl_general_unit') or 'months'))
        else:
            for idx, band in enumerate(RANK_BANDS):
                rows.append((band, _int(f'tl_{idx}_hours'),
                             _int(f'tl_{idx}_duration', 6),
                             request.form.get(f'tl_{idx}_unit') or 'months'))
        success, msg = save_teaching_load(conn, cursor, int(term_id), designation_type, mode, rows)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving teaching load: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-institution')


@admin_bp.route('/criteria/save_weights', methods=['POST'])
@role_required('ADMIN')
def admin_save_weights():
    term_id = request.form.get('term_id')
    designation_type = request.form.get('designation_type')
    if not term_id or designation_type not in DESIGNATION_TYPES:
        flash("No term or designation type specified.", "danger")
        return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')
    mode = request.form.get('mode', MODE_GENERAL)

    def _pct(field):
        try:
            return float(request.form.get(field, '0') or 0)
        except (ValueError, TypeError):
            return 0

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        categories = get_ipcr_categories(cursor, designation_type)
        rows = []
        if mode == MODE_GENERAL:
            for c in categories:
                cid = c['ipcr_category_id']
                rows.append((GENERAL_BAND, cid, _pct(f'w_general_{cid}')))
        else:
            for idx, band in enumerate(RANK_BANDS):
                for c in categories:
                    cid = c['ipcr_category_id']
                    rows.append((band, cid, _pct(f'w_{idx}_{cid}')))
        success, msg = save_criteria_weights(conn, cursor, int(term_id), designation_type, mode, rows)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error saving weights: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/criteria/copy_weights', methods=['POST'])
@role_required('ADMIN')
def admin_copy_weights():
    term_id = request.form.get('term_id')
    designation_type = request.form.get('designation_type')
    if not term_id or designation_type not in DESIGNATION_TYPES:
        flash("No term or designation type specified.", "danger")
        return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        success, msg = copy_weights_from_previous_term(conn, cursor, int(term_id), designation_type)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error copying weights: {str(e)}", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return redirect(url_for('admin.admin_dashboard') + '#nav-criteria')


@admin_bp.route('/security/reset_password', methods=['POST'])
@role_required('ADMIN')
def admin_reset_password():
    emp_id = request.form.get('emp_id')
    try:
        alphabet = string.ascii_letters + string.digits
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(10))

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            new_hash = hash_pass(temp_password)
            emergency_reset_password(conn, cursor, emp_id, new_hash)
            log_audit_action(conn, cursor, session.get('user_id'), 'Emergency Password Reset',
                             f"Temporary password issued for emp_id: {emp_id}",
                             request.remote_addr)
        finally:
            cursor.close()
            conn.close()
        flash(f"Password for account #{emp_id} has been reset. Temporary password (show once): {temp_password}", "warning")
    except Exception as e:
        flash(f"Error resetting password: {str(e)}", "danger")
    return redirect(url_for('admin.admin_dashboard') + '#nav-security')


@admin_bp.route('/security/lock_account', methods=['POST'])
@role_required('ADMIN')
def admin_lock_account():
    emp_id = request.form.get('emp_id')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            emergency_lock_account(conn, cursor, emp_id)
            log_audit_action(conn, cursor, session.get('user_id'), 'Emergency Account Lock',
                             f"Force locked account for emp_id: {emp_id}",
                             request.remote_addr)
        finally:
            cursor.close()
            conn.close()
        flash(f"Account #{emp_id} has been locked.", "warning")
    except Exception as e:
        flash(f"Error locking account: {str(e)}", "danger")
    return redirect(url_for('admin.admin_dashboard') + '#nav-security')
