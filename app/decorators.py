from flask import session, redirect, url_for, flash

_LOCKED_MESSAGE = "Your account has been locked by the administrator. Please contact IT/Administration for assistance."


def _account_is_locked(emp_id):
    """
    True if an Admin has locked (or deactivated) this account since it logged in.

    Checked per-request rather than trusting the session, since a lock applied mid-session
    must take effect immediately -- an already-logged-in locked user must not be able to keep
    performing actions just because their session predates the lock.
    """
    from app.models.connection import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT account_status FROM tbl_system_access WHERE emp_id = %s", (emp_id,))
        row = cursor.fetchone()
        return bool(row) and row[0] in ('Locked', 'Inactive')
    finally:
        cursor.close()
        conn.close()


def role_required(required_role):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if session.get('role') != required_role:
                return "Unauthorised", 403
            if _account_is_locked(session['user_id']):
                session.clear()
                flash(_LOCKED_MESSAGE, "danger")
                return redirect(url_for('auth.login'))
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


def designated_ipcr_required(func):
    """
    Guards the shared Designated Faculty IPCR flow.

    Access is decided by the employee's *designation* (their accountability role), not by
    session['role'] (which dashboard they logged into). A Program Chair, RET Chair or Dean
    is a designated faculty member with an IPCR of their own, so they reach this flow from
    their own dashboard while keeping their chair/dean role.

    Regular Faculty are excluded — they have their own flow under /faculty/ — as are system
    accounts with no IPCR at all.
    """
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        if _account_is_locked(session['user_id']):
            session.clear()
            flash(_LOCKED_MESSAGE, "danger")
            return redirect(url_for('auth.login'))

        from app.models.connection import get_db_connection
        from app.models.criteria import is_designated

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT designation FROM tbl_employee_profiles WHERE emp_id = %s",
                (session.get('user_id'),))
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

        if not row or not is_designated(row[0]):
            return "Unauthorised", 403
        return func(*args, **kwargs)

    wrapper.__name__ = func.__name__
    return wrapper
