def get_user_by_email(cursor, email):
    cursor.callproc('get_user_by_email', (email,))
    for result in cursor.stored_results():
        return result.fetchall()
    return []


def record_last_login(emp_id):
    """
    Stamp tbl_auth_credentials.last_login for a successful sign-in.

    Opens its own connection: the login route closes its cursor in a `finally`
    block before the password is even verified, so there is no live cursor left
    to reuse by the time we know the sign-in succeeded. The pool is autocommit,
    so no explicit commit is needed.

    Never raises — a failed timestamp must not cost the user their login.
    """
    from app.models.connection import get_db_connection
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tbl_auth_credentials SET last_login = NOW() WHERE emp_id = %s",
            (emp_id,)
        )
    except Exception:
        pass
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def system_role_for_designation(designation):
    return {
        'Admin': 'Admin',
        'Dean': 'DEAN',
        'Program Chair': 'PROGRAM_CHAIR',
        'RET Chair': 'RET_CHAIR',
        'Designated Faculty': 'DESIGNATED_FACULTY',
    }.get(designation, 'FACULTY')


def register_user(conn, cursor, employee_id_number, email, password_hash):
    """
    Submit an account-claim request.

    Replaces the old `register_user` stored procedure, which inserted the credential
    directly as 'APPROVED' (auto-approval). A claim now lands as 'PENDING' and only
    becomes usable once an Admin approves it -- see approve_account_claim() /
    deny_account_claim(). Raises ValueError with a user-facing message for the cases the
    old procedure signalled via SIGNAL SQLSTATE '45000'. Returns the claimant's emp_id.
    """
    cursor.execute(
        "SELECT emp_id, designation FROM tbl_employee_profiles WHERE employee_id_number = %s",
        (employee_id_number,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Employee ID Number is not recognized by HR. Please contact the administrator.")
    emp_id, designation = row

    cursor.execute("SELECT COUNT(*) FROM tbl_auth_credentials WHERE emp_id = %s", (emp_id,))
    if cursor.fetchone()[0] > 0:
        raise ValueError("This employee account has already been claimed, or its claim is already pending approval.")

    cursor.execute("SELECT COUNT(*) FROM tbl_auth_credentials WHERE corporate_email = %s", (email,))
    if cursor.fetchone()[0] > 0:
        raise ValueError("This corporate email is already registered to another account.")

    role = system_role_for_designation(designation)

    cursor.execute("""
        INSERT INTO tbl_auth_credentials (emp_id, corporate_email, password_hash, verification_status)
        VALUES (%s, %s, %s, 'PENDING')
    """, (emp_id, email, password_hash))

    cursor.execute("""
        INSERT INTO tbl_system_access (emp_id, system_role, account_status)
        VALUES (%s, %s, 'Pending')
        ON DUPLICATE KEY UPDATE system_role = %s, account_status = 'Pending'
    """, (emp_id, role, role))

    conn.commit()
    return emp_id


def get_pending_account_claims(cursor):
    """Pending account-claim requests awaiting Admin approval."""
    from app.models.connection import timed_query
    query = """
        SELECT ac.emp_id, ac.corporate_email, ac.verification_status,
               ep.employee_id_number, ep.first_name, ep.last_name, ep.designation,
               sa.system_role
        FROM tbl_auth_credentials ac
        JOIN tbl_employee_profiles ep ON ep.emp_id = ac.emp_id
        LEFT JOIN tbl_system_access sa ON sa.emp_id = ac.emp_id
        WHERE ac.verification_status = 'PENDING'
        ORDER BY ep.last_name, ep.first_name
    """
    return timed_query(cursor, query, label="get_pending_account_claims")


def approve_account_claim(conn, cursor, emp_id):
    """Approve a pending claim: credential -> APPROVED, access -> Active. Returns True if a row changed."""
    cursor.execute(
        "UPDATE tbl_auth_credentials SET verification_status = 'APPROVED' WHERE emp_id = %s",
        (emp_id,))
    if cursor.rowcount == 0:
        return False
    cursor.execute(
        "UPDATE tbl_system_access SET account_status = 'Active' WHERE emp_id = %s",
        (emp_id,))
    conn.commit()
    return True


def deny_account_claim(conn, cursor, emp_id):
    """Deny a pending claim by deleting the credential row, freeing the ID/email to claim
    again. The denial is recorded in the audit log by the caller. Returns True if removed."""
    cursor.execute("DELETE FROM tbl_auth_credentials WHERE emp_id = %s", (emp_id,))
    if cursor.rowcount == 0:
        return False
    conn.commit()
    return True


def get_all_profiles(cursor):
    from app.models.connection import timed_query
    return timed_query(cursor,
        "SELECT * FROM tbl_employee_profiles ORDER BY last_name ASC, first_name ASC",
        label="get_all_profiles")


def save_single_profile(conn, cursor, data):
    sql = """
        INSERT INTO tbl_employee_profiles 
        (employee_id_number, first_name, last_name, college, assigned_program, specialization, academic_rank, employment_status, leave_status, designation)
        VALUES (%(employee_id_number)s, %(first_name)s, %(last_name)s, %(college)s, %(assigned_program)s, %(specialization)s, %(academic_rank)s, %(employment_status)s, %(leave_status)s, %(designation)s)
        ON DUPLICATE KEY UPDATE 
        first_name = VALUES(first_name),
        last_name = VALUES(last_name),
        college = VALUES(college),
        assigned_program = VALUES(assigned_program),
        specialization = VALUES(specialization),
        academic_rank = VALUES(academic_rank),
        employment_status = VALUES(employment_status),
        leave_status = VALUES(leave_status),
        designation = VALUES(designation)
    """
    try:
        cursor.execute(sql, data)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


def toggle_profile_status(conn, cursor, employee_id_number):
    try:
        cursor.execute("SELECT emp_id, leave_status FROM tbl_employee_profiles WHERE employee_id_number = %s", (employee_id_number,))
        result = cursor.fetchone()
        if not result:
            return False

        emp_id, current_status = result
        new_status = 'Inactive' if current_status == 'Active' else 'Active'

        cursor.execute("UPDATE tbl_employee_profiles SET leave_status = %s WHERE employee_id_number = %s", (new_status, employee_id_number))
        cursor.execute("UPDATE tbl_system_access SET account_status = %s WHERE emp_id = %s", (new_status, emp_id))

        conn.commit()
        return new_status
    except Exception as e:
        conn.rollback()
        raise e


def import_csv_roster(conn, cursor, csv_rows):
    new_added = 0
    updated = 0
    unchanged = 0

    try:
        cursor.execute("SELECT employee_id_number, first_name, last_name, college, assigned_program, specialization, academic_rank, employment_status, leave_status, designation FROM tbl_employee_profiles")
        columns = [col[0] for col in cursor.description]
        existing_profiles = {}
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            for k, v in record.items():
                if v is None:
                    record[k] = ""
            existing_profiles[record['employee_id_number']] = record

        insert_sql = """
            INSERT INTO tbl_employee_profiles 
            (employee_id_number, first_name, last_name, college, assigned_program, specialization, academic_rank, employment_status, leave_status, designation)
            VALUES (%(employee_id_number)s, %(first_name)s, %(last_name)s, %(college)s, %(assigned_program)s, %(specialization)s, %(academic_rank)s, %(employment_status)s, %(leave_status)s, %(designation)s)
        """

        update_sql = """
            UPDATE tbl_employee_profiles 
            SET first_name=%(first_name)s, last_name=%(last_name)s, college=%(college)s, 
                assigned_program=%(assigned_program)s, specialization=%(specialization)s, academic_rank=%(academic_rank)s, 
                employment_status=%(employment_status)s, leave_status=%(leave_status)s, designation=%(designation)s
            WHERE employee_id_number=%(employee_id_number)s
        """

        for row in csv_rows:
            emp_id = row.get('employee_id_number', '').strip()
            if not emp_id:
                continue

            current_row = {
                'employee_id_number': emp_id,
                'first_name': row.get('first_name', '').strip(),
                'last_name': row.get('last_name', '').strip(),
                'college': row.get('college', '').strip(),
                'assigned_program': row.get('assigned_program', '').strip(),
                'specialization': row.get('specialization', '').strip(),
                'academic_rank': row.get('academic_rank', '').strip(),
                'employment_status': row.get('employment_status', '').strip(),
                'leave_status': row.get('leave_status', '').strip(),
                'designation': row.get('designation', '').strip()
            }

            if emp_id not in existing_profiles:
                cursor.execute(insert_sql, current_row)
                new_added += 1
            else:
                existing = existing_profiles[emp_id]
                differs = False
                for key in ['first_name', 'last_name', 'college', 'assigned_program', 'specialization', 'academic_rank', 'employment_status', 'leave_status', 'designation']:
                    if str(current_row[key]) != str(existing[key]):
                        differs = True
                        break

                if differs:
                    cursor.execute(update_sql, current_row)
                    updated += 1
                else:
                    unchanged += 1

        conn.commit()
        return True, new_added, updated, unchanged
    except Exception as e:
        conn.rollback()
        return False, str(e), 0, 0
