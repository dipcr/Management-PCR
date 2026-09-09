# Docker setup
import os
import logging
import mysql.connector
from mysql.connector import Error
from app.auth import hash_pass, validate_password_policy

logger = logging.getLogger(__name__)

ADMIN_ROLE = 'Admin'          
ADMIN_DESIGNATION = 'Admin'   


def bootstrap_admin():
    admin_email = (os.getenv('ADMIN_EMAIL') or '').strip()
    admin_password = os.getenv('ADMIN_PASSWORD') or ''

    if not admin_email or not admin_password:
        logger.warning("ADMIN_EMAIL or ADMIN_PASSWORD not set — skipping bootstrap.")
        return

    ok, msg = validate_password_policy(admin_password)
    if not ok:
        logger.warning(f"ADMIN_PASSWORD rejected by policy: {msg} — skipping bootstrap.")
        return

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT')),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            connection_timeout=10
        )
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM tbl_system_access WHERE UPPER(system_role) = 'ADMIN'"
        )
        if cursor.fetchone()[0] > 0:
            logger.info("Admin account already exists — skipping bootstrap.")
            return

        logger.info("No admin found. Bootstrapping first admin...")

        # Create the employee profile
        cursor.execute("""
            INSERT INTO tbl_employee_profiles
                (employee_id_number, first_name, last_name, college, assigned_program,
                 academic_rank, employment_status, designation, leave_status, specialization)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, ('ADMIN-001', 'System', 'Admin', 'CICT', 'BSIT',
              'Admin', 'Regular', ADMIN_DESIGNATION, 'Active', 'System Administration'))

        emp_id = cursor.lastrowid

        hashed = hash_pass(admin_password)
        cursor.execute("""
            INSERT INTO tbl_auth_credentials (emp_id, corporate_email, password_hash, verification_status)
            VALUES (%s, %s, %s, 'APPROVED')
        """, (emp_id, admin_email, hashed))

        cursor.execute("""
            INSERT INTO tbl_system_access (emp_id, system_role, account_status)
            VALUES (%s, %s, 'Active')
        """, (emp_id, ADMIN_ROLE))

        conn.commit()
        logger.info(f"Admin account created: {admin_email}")

    except Error as e:
        logger.error(f"Failed to bootstrap admin: {e}")
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
