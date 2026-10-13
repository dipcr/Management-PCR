"""Read-only access to the signed-in employee's previous IPCRs."""

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for

from app.decorators import _account_is_locked, _LOCKED_MESSAGE
from app.models.connection import get_db_connection
from app.models.ipcr_form import build_ipcr_form
from app.models.ipcr_history import get_ipcr_history

ipcr_history_bp = Blueprint('ipcr_history', __name__, url_prefix='/ipcr-history')

HOME_ENDPOINTS = {
    'ADMIN': 'admin.admin_dashboard',
    'FACULTY': 'faculty.faculty_dashboard',
    'DESIGNATED_FACULTY': 'designated.designated_dashboard',
    'PROGRAM_CHAIR': 'prog_chair.prog_chair_dashboard',
    'RET_CHAIR': 'ret_chair.ret_chair_dashboard',
    'DEAN': 'dean.dean_dashboard',
}


@ipcr_history_bp.route('/<int:term_id>')
def view_ipcr(term_id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    emp_id = session['user_id']
    if _account_is_locked(emp_id):
        session.clear()
        flash(_LOCKED_MESSAGE, 'danger')
        return redirect(url_for('auth.login'))
    endpoint = HOME_ENDPOINTS.get(session.get('role'))
    if not endpoint:
        abort(403)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ownership comes exclusively from the session, never a URL employee ID.
        if not any(row['term_id'] == term_id for row in get_ipcr_history(cursor, emp_id)):
            abort(404)
        form = build_ipcr_form(cursor, emp_id, term_id)
        if not form or not form['has_targets']:
            abort(404)
        section = 'designated-overview' if session.get('role') == 'DESIGNATED_FACULTY' else 'nav-overview'
        return render_template('ipcr_print.html', form=form,
                               back_url=url_for(endpoint) + '#' + section)
    finally:
        cursor.close()
        conn.close()
