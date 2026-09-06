def get_admin_kpis(cursor):
    """Consolidated KPI query — 1 round-trip instead of 3."""
    from app.models.connection import timed_query
    query = """
        SELECT
            (SELECT COUNT(emp_id) FROM tbl_employee_profiles) AS total_roster,
            (SELECT COUNT(emp_id) FROM tbl_auth_credentials) AS claimed_accounts
    """
    result = timed_query(cursor, query, label="get_admin_kpis")
    if not result:
        return {'claimed_accounts': 0, 'total_roster': 0, 'adoption_rate': 0}

    row = result[0]
    total = row['total_roster'] or 0
    claimed = row['claimed_accounts'] or 0
    adoption = round((claimed / total) * 100) if total > 0 else 0

    return {
        'claimed_accounts': claimed,
        'total_roster': total,
        'adoption_rate': adoption
    }
