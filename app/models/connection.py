import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_pool = None


def _require_env(key):
    """Get an env var or raise a clear error."""
    val = os.getenv(key)
    if val is None:
        raise RuntimeError(
            f"Missing required environment variable '{key}'. "
            f"Check your .env file or set it in your environment."
        )
    return val


def init_db_pool():
    """Initialize the connection pool once at app startup."""
    global _pool
    try:
        logger.info("Initializing database connection pool...")
        _pool = MySQLConnectionPool(
            pool_name="dipcr_pool",
            pool_size=5,
            host=_require_env('DB_HOST'),
            port=int(_require_env('DB_PORT')),
            database=_require_env('DB_NAME'),
            user=_require_env('DB_USER'),
            password=_require_env('DB_PASSWORD'),
            connection_timeout=5,
            autocommit=True
        )
        logger.info("Database connection pool created successfully.")
    except Error as e:
        raise RuntimeError(f"Failed to create DB connection pool: {e}")


def get_overall_ipcr_status(cursor, emp_id, term_id):
    """
    Dynamically computes the overall IPCR status string based on the current state
    of targets and reviews, removing the need for a separate physical status table.
    """
    # 1. Check if locked (completed)
    cursor.execute("""
        SELECT COUNT(*) FROM tbl_committed_targets ct
        JOIN tbl_master_indicators mi ON ct.indicator_id = mi.indicator_id
        WHERE ct.emp_id = %s AND mi.term_id = %s
    """, (emp_id, term_id))
    if cursor.fetchone()[0] > 0:
        return 'completed'

    # 2. Check if approved by Program Chair
    cursor.execute("""
        SELECT overall_status FROM tbl_ipcr_chair_review
        WHERE emp_id = %s AND term_id = %s
    """, (emp_id, term_id))
    chair_row = cursor.fetchone()
    if chair_row and chair_row[0] == 'Approved':
        return 'approved_by_program_chair'

    # 3. Check if we have draft targets at all
    cursor.execute("""
        SELECT COUNT(*) FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        WHERE dt.emp_id = %s AND mi.term_id = %s
    """, (emp_id, term_id))
    has_drafts = cursor.fetchone()[0] > 0
    if not has_drafts:
        return 'draft'

    # 4. Check if any targets are returned/rejected
    cursor.execute("""
        SELECT COUNT(*) FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        WHERE dt.emp_id = %s AND mi.term_id = %s AND dt.review_status = 'Returned'
    """, (emp_id, term_id))
    if cursor.fetchone()[0] > 0:
        return 'draft'

    # 5. Check if any targets are still 'Draft'
    cursor.execute("""
        SELECT COUNT(*) FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        WHERE dt.emp_id = %s AND mi.term_id = %s AND dt.review_status = 'Draft'
    """, (emp_id, term_id))
    if cursor.fetchone()[0] > 0:
        return 'draft'

    # 6. Check RET review status — Option B: the RET review stage is triggered by the
    # presence of Research targets (self-selected or chair-assigned), not by a per-faculty
    # enable flag. Extension is distributed and auto-flows, so it never triggers RET review.
    cursor.execute("""
        SELECT COUNT(*)
        FROM tbl_draft_targets dt
        JOIN tbl_master_indicators mi ON dt.indicator_id = mi.indicator_id
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE dt.emp_id = %s AND mi.term_id = %s
          AND tc.slug = 'research' AND dt.proposed_quantity > 0
    """, (emp_id, term_id))
    has_research_targets = cursor.fetchone()[0] > 0

    if not has_research_targets:
        # No Research targets -> bypass RET review, straight to Program Chair
        if chair_row and chair_row[0] == 'Rejected':
            return 'rejected_by_program_chair'
        return 'waiting_for_program_chair_review'

    cursor.execute("""
        SELECT overall_status FROM tbl_ipcr_ret_review
        WHERE emp_id = %s AND term_id = %s
    """, (emp_id, term_id))
    ret_row = cursor.fetchone()

    if ret_row:
        ret_status = ret_row[0]
        if ret_status == 'Rejected':
            return 'rejected_by_ret_chair'
        elif ret_status == 'Approved':
            # RET has approved
            if chair_row:
                chair_status = chair_row[0]
                if chair_status == 'Rejected':
                    return 'rejected_by_program_chair'
                elif chair_status == 'Approved':
                    return 'approved_by_program_chair'
            return 'waiting_for_program_chair_review'
        elif ret_status == 'Pending':
            if chair_row and chair_row[0] == 'Approved':
                return 'waiting_for_ret_chair_review'
            return 'pending_ret_review'
    else:
        # No RET review record exists yet, but targets are submitted
        return 'waiting_for_ret_chair_review'

    return 'draft'



def get_db_connection():
    global _pool
    if _pool is None:
        init_db_pool()
    try:
        t0 = time.time()
        connection = _pool.get_connection()
        elapsed = time.time() - t0
        if elapsed > 0.5:
            logger.warning(f"Slow pool checkout: {elapsed:.2f}s")
        if connection.is_connected():
            # Register on the request context so the app's teardown_request handler
            # ALWAYS returns this connection to the pool — even if the route raises
            # before its manual conn.close() runs. This prevents pool exhaustion
            # ("Too many connections" / slow checkouts) from leaked connections.
            try:
                from flask import g
                g._db_conn = connection
            except Exception:
                pass  # Outside a request context — caller is responsible for closing
            return connection
        raise RuntimeError("Database connection could not be established.")
    except Error as e:
        raise RuntimeError(f"Database connection failed: {e}")


def timed_query(cursor, query, params=None, label=""):
    """Execute a query with timing logging."""
    t0 = time.time()
    cursor.execute(query, params or ())
    elapsed = time.time() - t0
    if elapsed > 0.3:
        logger.warning(f"SLOW QUERY ({elapsed:.2f}s): {label or query[:80]}")
    columns = [col[0] for col in cursor.description] if cursor.description else []
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
