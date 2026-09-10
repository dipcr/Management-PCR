def open_new_term(conn, cursor, academic_year, semester,
                  period_start=None, period_end=None):
    """
    Open a term and make it the active one.

    period_start/period_end are the rating period printed on the IPCR header
    ("...for the period JANUARY to JUNE 2026"); academic_year and semester cannot
    express that on their own.
    """
    try:
        # Deactivate all current terms
        cursor.execute("UPDATE tbl_academic_terms SET is_active = FALSE")

        # Insert and activate the new term
        query_open = """
            INSERT INTO tbl_academic_terms
                (academic_year, semester, period_start, period_end, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
        """
        cursor.execute(query_open, (academic_year, semester,
                                    period_start or None, period_end or None))
        new_term_id = cursor.lastrowid

        carry_forward_teaching_load(cursor, new_term_id)

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


def carry_forward_teaching_load(cursor, new_term_id):
    """
    Give a newly opened term a teaching-load configuration.

    The mandated load rarely changes between terms, so the previous term's settings are
    copied forward. Without this a new term starts with none at all and the Admin panel
    renders blank fields, which reads as a bug rather than as "not configured yet".

    Any designation the previous term happened to be missing is filled from the built-in
    defaults, so an incomplete term cannot propagate its gap forward.
    """
    from app.models.criteria import DESIGNATION_TYPES
    from app.models.institution import DEFAULT_TEACHING_LOAD, DEFAULT_LOAD_DURATION

    cursor.execute("""
        SELECT term_id FROM tbl_teaching_load_config
        WHERE term_id <> %s
        ORDER BY term_id DESC LIMIT 1
    """, (new_term_id,))
    # fetchall, not fetchone: an unconsumed result set makes the next execute fail with
    # "Unread result found" on this connector.
    prior = cursor.fetchall()
    row = prior[0] if prior else None

    if row:
        # IGNORE so the helper is also safe to run against a term that already has
        # some rows — it then behaves as a top-up rather than failing on the unique key.
        cursor.execute("""
            INSERT IGNORE INTO tbl_teaching_load_config
                (term_id, designation_type, rank_band, hours, duration_value, duration_unit)
            SELECT %s, designation_type, rank_band, hours, duration_value, duration_unit
            FROM tbl_teaching_load_config
            WHERE term_id = %s
        """, (new_term_id, row[0]))

    # Top up whatever is still missing.
    cursor.execute(
        "SELECT DISTINCT designation_type FROM tbl_teaching_load_config WHERE term_id = %s",
        (new_term_id,))
    have = {r[0] for r in cursor.fetchall()}

    value, unit = DEFAULT_LOAD_DURATION
    for designation_type in DESIGNATION_TYPES:
        if designation_type in have:
            continue
        cursor.execute("""
            INSERT INTO tbl_teaching_load_config
                (term_id, designation_type, rank_band, hours, duration_value, duration_unit)
            VALUES (%s, %s, 'General', %s, %s, %s)
        """, (new_term_id, designation_type,
              DEFAULT_TEACHING_LOAD.get(designation_type, 21), value, unit))


def get_all_terms(cursor):
    from app.models.connection import timed_query
    query = """
        SELECT term_id, academic_year, semester,
               period_start, period_end, is_active
        FROM tbl_academic_terms ORDER BY term_id DESC
    """
    return timed_query(cursor, query, label="get_all_terms")
