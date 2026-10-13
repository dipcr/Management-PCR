"""Personal IPCR history, read from existing term records without copying data."""

from app.models.connection import timed_query
from app.models.ipcr_form import format_rating_period


def get_ipcr_history(cursor, emp_id):
    """One row per inactive term with committed targets belonging to this employee.

    Drafts are not committed IPCRs. Partially approved packages remain visible but
    must not display a stale final score after a reopen. Use the latest saved score
    because older databases do not enforce uniqueness on employee/term scores.
    """
    rows = timed_query(cursor, """
        SELECT t.term_id, t.academic_year, t.semester, t.period_start, t.period_end,
               package.target_count, package.approved_count,
               fs.final_score, fs.adjectival_rating
        FROM tbl_academic_terms t
        JOIN (
            SELECT mi.term_id, COUNT(*) AS target_count,
                   SUM(CASE WHEN ct.status = 'Dean Approved' THEN 1 ELSE 0 END) AS approved_count
            FROM tbl_committed_targets ct
            JOIN tbl_master_indicators mi ON mi.indicator_id = ct.indicator_id
            WHERE ct.emp_id = %s
            GROUP BY mi.term_id
        ) package ON package.term_id = t.term_id
        LEFT JOIN tbl_final_scores fs ON fs.score_id = (
            SELECT MAX(saved.score_id) FROM tbl_final_scores saved
            WHERE saved.emp_id = %s AND saved.term_id = t.term_id
        )
        WHERE COALESCE(t.is_active, 0) = 0
        ORDER BY COALESCE(t.period_end, t.period_start) DESC,
                 t.academic_year DESC, t.term_id DESC
    """, (emp_id, emp_id), label='personal_ipcr_history')
    for row in rows:
        row['is_final'] = row['approved_count'] == row['target_count']
        row['status'] = 'Dean Approved' if row['is_final'] else 'Committed — Not Finalized'
        row['rating_period'] = format_rating_period(row['period_start'], row['period_end'])
        if not row['is_final']:
            row['final_score'] = None
            row['adjectival_rating'] = None
    return rows
