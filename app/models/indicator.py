def get_master_indicators(cursor, term_id):
    """Returns master indicators as dicts with category_name — used by Admin and Dean dashboards."""
    from app.models.connection import timed_query
    query = """
        SELECT mi.*, tc.category_name 
        FROM tbl_master_indicators mi
        LEFT JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE mi.term_id = %s AND mi.is_custom = 0 AND mi.indicator_description NOT LIKE '%%Teaching Load%%'
        ORDER BY tc.category_name, mi.indicator_id
    """
    return timed_query(cursor, query, (term_id,), label="get_master_indicators")


def is_indicator_cascaded(cursor, indicator_id):
    """True once this indicator has entered any downstream pipeline: a Dean-cascaded quota
    (the normal path for Instruction/Support/RET indicators), or a RET Chair rank rule
    (tbl_ret_rule_indicators has no FK to tbl_cascaded_quotas, so an indicator assigned into
    a rank rule wouldn't be caught by the quota check alone)."""
    cursor.execute("SELECT COUNT(*) FROM tbl_cascaded_quotas WHERE indicator_id = %s", (indicator_id,))
    if cursor.fetchone()[0] > 0:
        return True
    cursor.execute("SELECT COUNT(*) FROM tbl_ret_rule_indicators WHERE indicator_id = %s", (indicator_id,))
    return cursor.fetchone()[0] > 0


def add_master_indicator(conn, cursor, category_name, description, efficiency_type, term_id):
    cursor.execute("SELECT category_id FROM tbl_target_categories WHERE category_name = %s", (category_name,))
    cat_result = cursor.fetchone()
    if not cat_result:
        cursor.execute("INSERT INTO tbl_target_categories (category_name) VALUES (%s)", (category_name,))
        category_id = cursor.lastrowid
    else:
        category_id = cat_result[0]

    query = "INSERT INTO tbl_master_indicators (category_id, indicator_description, efficiency_type, term_id) VALUES (%s, %s, %s, %s)"
    cursor.execute(query, (category_id, description, efficiency_type, term_id))
    conn.commit()


def edit_master_indicator(conn, cursor, indicator_id, category_name, description, efficiency_type):
    cursor.execute("SELECT category_id FROM tbl_master_indicators WHERE indicator_id = %s", (indicator_id,))
    current = cursor.fetchone()
    current_category_id = current[0] if current else None

    # Look up only -- do not create the category row yet. Creating it here and only
    # checking the cascade lock afterward would leave a permanent orphan row (autocommit
    # is on, no rollback) if the edit turns out to be blocked below.
    cursor.execute("SELECT category_id FROM tbl_target_categories WHERE category_name = %s", (category_name,))
    cat_result = cursor.fetchone()
    category_changing = (cat_result is None) or (cat_result[0] != current_category_id)

    if category_changing and is_indicator_cascaded(cursor, indicator_id):
        raise ValueError(
            "This indicator has already been cascaded to departments — its category cannot "
            "be changed. The description and efficiency type can still be edited."
        )

    if cat_result:
        category_id = cat_result[0]
    else:
        cursor.execute("INSERT INTO tbl_target_categories (category_name) VALUES (%s)", (category_name,))
        category_id = cursor.lastrowid

    query = "UPDATE tbl_master_indicators SET category_id = %s, indicator_description = %s, efficiency_type = %s WHERE indicator_id = %s"
    cursor.execute(query, (category_id, description, efficiency_type, indicator_id))
    conn.commit()


def delete_master_indicator(conn, cursor, indicator_id):
    if is_indicator_cascaded(cursor, indicator_id):
        raise ValueError("This indicator has already been cascaded to departments and cannot be deleted.")
    cursor.execute("DELETE FROM tbl_master_indicators WHERE indicator_id = %s", (indicator_id,))
    conn.commit()


def import_previous_term_indicators(conn, cursor, active_term_id):
    cursor.execute("SELECT term_id FROM tbl_academic_terms WHERE is_active = FALSE ORDER BY term_id DESC LIMIT 1")
    prev_term = cursor.fetchone()
    if not prev_term:
        return False, "No previous term found to import from."

    # Added is_custom = 0 and NOT LIKE '%Teaching Load%' conditions to prevent importing user-specific custom targets or baseline teaching loads as global indicators
    # Joined to tbl_target_categories and filtered on is_active so indicators under a criterion the Admin has since deactivated aren't resurrected into the new term
    cursor.execute("""
        SELECT mi.category_id, mi.indicator_description, mi.efficiency_type
        FROM tbl_master_indicators mi
        JOIN tbl_target_categories tc ON mi.category_id = tc.category_id
        WHERE mi.term_id = %s AND mi.is_custom = 0 AND mi.indicator_description NOT LIKE '%%Teaching Load%%'
          AND tc.is_active = 1
    """, (prev_term[0],))
    prev_indicators = cursor.fetchall()

    if not prev_indicators:
        return False, "Previous term has no indicators to import."

    for ind in prev_indicators:
        cursor.execute(
            "INSERT INTO tbl_master_indicators (category_id, indicator_description, efficiency_type, term_id, is_custom) VALUES (%s, %s, %s, %s, 0)",
            (ind[0], ind[1], ind[2], active_term_id)
        )
    conn.commit()
    return True, "Previous semester targets successfully imported!"

