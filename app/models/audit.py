def log_audit_action(conn, cursor, actor_id, action_type, details, ip_address):
    query = "INSERT INTO tbl_audit_logs (actor_id, action_type, action_details, ip_address) VALUES (%s, %s, %s, %s)"
    cursor.execute(query, (actor_id, action_type, details, ip_address))
    conn.commit()


def get_recent_audit_logs(cursor, limit=50):
    from app.models.connection import timed_query
    query = """
        SELECT a.log_timestamp, a.actor_id, a.action_type, a.action_details, a.ip_address,
               CONCAT(e.first_name, ' ', e.last_name) AS actor_name
        FROM tbl_audit_logs a
        LEFT JOIN tbl_employee_profiles e ON e.emp_id = a.actor_id
        ORDER BY a.log_timestamp DESC LIMIT %s
    """
    return timed_query(cursor, query, (limit,), label="get_recent_audit_logs")


def emergency_reset_password(conn, cursor, emp_id, new_hashed_password):
    cursor.execute(
        "UPDATE tbl_auth_credentials SET password_hash = %s WHERE emp_id = %s",
        (new_hashed_password, emp_id)
    )
    conn.commit()


def emergency_lock_account(conn, cursor, emp_id):
    cursor.execute(
        "UPDATE tbl_system_access SET account_status = 'Locked' WHERE emp_id = %s",
        (emp_id,)
    )
    conn.commit()


def emergency_unlock_account(conn, cursor, emp_id):
    cursor.execute(
        "UPDATE tbl_system_access SET account_status = 'Active' WHERE emp_id = %s",
        (emp_id,)
    )
    conn.commit()


def get_all_users_for_security(cursor):
    from app.models.connection import timed_query
    query = """
        SELECT e.emp_id, e.first_name, e.last_name, s.system_role, s.account_status
        FROM tbl_employee_profiles e
        JOIN tbl_system_access s ON e.emp_id = s.emp_id
        ORDER BY e.last_name ASC
    """
    return timed_query(cursor, query, label="get_all_users_for_security")
