"""Offline history query, dashboard and ownership regressions.

Run: python -m unittest test_personal_ipcr_history
"""
import sqlite3
import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import MagicMock, patch

with patch('mysql.connector.pooling.MySQLConnectionPool'):
    from app import app
    from app.models.ipcr_history import get_ipcr_history


class HistoryQueryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE tbl_academic_terms (
                term_id INTEGER, academic_year TEXT, semester TEXT,
                period_start TEXT, period_end TEXT, is_active INTEGER);
            CREATE TABLE tbl_master_indicators (indicator_id INTEGER, term_id INTEGER);
            CREATE TABLE tbl_committed_targets (emp_id INTEGER, indicator_id INTEGER, status TEXT);
            CREATE TABLE tbl_final_scores (
                score_id INTEGER, emp_id INTEGER, term_id INTEGER,
                final_score REAL, adjectival_rating TEXT);
            INSERT INTO tbl_academic_terms VALUES
                (1, '2024-2025', 'First', '2024-07-01', '2024-12-31', 0),
                (2, '2024-2025', 'Second', '2025-01-01', '2025-06-30', 0),
                (3, '2025-2026', 'First', '2025-07-01', '2025-12-31', 1),
                (4, '2023-2024', 'First', NULL, NULL, 0);
            INSERT INTO tbl_master_indicators VALUES (11,1),(12,1),(21,2),(22,2),(31,3),(41,4);
            INSERT INTO tbl_committed_targets VALUES
                (77,11,'Dean Approved'),(77,12,'Dean Approved'),
                (77,21,'Dean Approved'),(77,22,'Submitted to Dean'),
                (77,31,'Dean Approved'),(88,41,'Dean Approved');
            INSERT INTO tbl_final_scores VALUES
                (1,77,1,3.0,'Old rating'),(2,77,1,4.5,'Outstanding'),
                (3,77,2,5.0,'Stale rating'),(4,88,1,1.0,'Another user');
        """)

    def query(self, cursor, query, params, label):
        # Execute the production SQL, adapting only the connector's placeholders
        # and date conversion. No live application database is touched.
        cursor.execute(query.replace('%s', '?'), params)
        rows = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
        for row in rows:
            for key in ('period_start', 'period_end'):
                row[key] = date.fromisoformat(row[key]) if row[key] else None
        return rows

    def history(self, emp_id=77):
        with patch('app.models.ipcr_history.timed_query', side_effect=self.query):
            return get_ipcr_history(self.db.cursor(), emp_id)

    def test_prior_terms_latest_score_and_employee_isolation(self):
        rows = self.history()
        self.assertEqual([r['term_id'] for r in rows], [2, 1])
        self.assertEqual(rows[1]['target_count'], 2)
        self.assertEqual(rows[1]['final_score'], 4.5)
        self.assertTrue(rows[1]['is_final'])
        self.assertFalse(rows[0]['is_final'])
        self.assertIsNone(rows[0]['final_score'])
        self.assertIsNone(rows[0]['adjectival_rating'])
        self.assertEqual(rows[1]['rating_period'], 'JULY to DECEMBER 2024')
        self.assertEqual(self.history(999), [])

    def test_no_active_term_and_missing_period_or_score(self):
        self.db.execute('UPDATE tbl_academic_terms SET is_active=0')
        self.assertEqual([r['term_id'] for r in self.history()], [3, 2, 1])
        row = self.history(88)[0]
        self.assertIsNone(row['rating_period'])
        self.assertIsNone(row['final_score'])


class HistoryAccessTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.conn = MagicMock()
        self.stack.enter_context(patch('app.routes.ipcr_history.get_db_connection', return_value=self.conn))
        self.locked = self.stack.enter_context(patch('app.routes.ipcr_history._account_is_locked', return_value=False))
        self.history = self.stack.enter_context(patch('app.routes.ipcr_history.get_ipcr_history', return_value=[{'term_id': 1}]))
        self.form = self.stack.enter_context(patch('app.routes.ipcr_history.build_ipcr_form', return_value={'has_targets': True}))
        self.render = self.stack.enter_context(patch('app.routes.ipcr_history.render_template', return_value='Own historical IPCR'))
        self.client = app.test_client()

    def login(self, role='FACULTY'):
        with self.client.session_transaction() as session:
            session['user_id'] = 77
            session['role'] = role

    def test_all_roles_view_only_session_owner_even_with_forged_query(self):
        for role in ('FACULTY','DESIGNATED_FACULTY','PROGRAM_CHAIR','RET_CHAIR','DEAN','ADMIN'):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.client.get('/ipcr-history/1?emp_id=88').status_code, 200)
                self.history.assert_called_with(self.conn.cursor.return_value, 77)
                self.form.assert_called_with(self.conn.cursor.return_value, 77, 1)
                self.assertIn('overview', self.render.call_args.kwargs['back_url'])

    def test_missing_or_other_employee_term_returns_404(self):
        self.login()
        self.assertEqual(self.client.get('/ipcr-history/99').status_code, 404)
        self.form.assert_not_called()
        self.conn.close.assert_called_once()
        self.conn.cursor.return_value.close.assert_called_once()

    def test_anonymous_and_locked_accounts_cannot_view(self):
        self.assertEqual(self.client.get('/ipcr-history/1').status_code, 302)
        self.login()
        self.locked.return_value = True
        self.assertEqual(self.client.get('/ipcr-history/1').status_code, 302)
        self.history.assert_not_called()
        with self.client.session_transaction() as session:
            self.assertNotIn('user_id', session)


class HistoryDashboardTests(unittest.TestCase):
    def test_history_shows_with_no_active_term(self):
        record = dict(term_id=9, academic_year='2024-2025', semester='Second',
                      rating_period=None, is_final=True, status='Dean Approved',
                      final_score=4.5, adjectival_rating='Outstanding')
        for module, role in [('faculty','FACULTY'), ('dean','DEAN'),
                             ('prog_chair','PROGRAM_CHAIR'), ('ret_chair','RET_CHAIR'),
                             ('designated','DESIGNATED_FACULTY'), ('admin','ADMIN')]:
            with self.subTest(role=role), ExitStack() as stack:
                conn = MagicMock()
                stack.enter_context(patch(f'app.routes.{module}.get_db_connection', return_value=conn))
                stack.enter_context(patch('app.decorators._account_is_locked', return_value=False))
                stack.enter_context(patch(f'app.routes.{module}.get_all_terms', return_value=[]))
                stack.enter_context(patch('app.models.connection.timed_query', return_value=[]))
                if module == 'designated':
                    conn.cursor.return_value.fetchone.return_value = ('Designated Faculty',)
                    stack.enter_context(patch('app.models.connection.get_db_connection', return_value=conn))
                    stack.enter_context(patch('app.models.connection._pool.get_connection', return_value=conn))
                if module == 'admin':
                    for helper in ('get_all_profiles', 'get_all_criteria', 'get_ipcr_categories',
                                   'get_departments', 'get_recent_audit_logs',
                                   'get_all_users_for_security', 'get_pending_account_claims'):
                        stack.enter_context(patch(f'app.routes.admin.{helper}', return_value=[]))
                    for helper in ('get_category_type_map', 'get_institution_settings',
                                   'get_signatories', 'get_admin_kpis'):
                        stack.enter_context(patch(f'app.routes.admin.{helper}', return_value={}))
                history = stack.enter_context(patch(f'app.routes.{module}.get_ipcr_history', return_value=[record]))
                client = app.test_client()
                with client.session_transaction() as session:
                    session.update(user_id=77, role=role, specialization='Test Program')
                response = client.get(f'/{module}/')
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn('My IPCR History', html)
                self.assertIn('/ipcr-history/9', html)
                self.assertIn('4.50', html)
                history.assert_called_once_with(conn.cursor.return_value, 77)

    def test_shared_empty_state(self):
        with app.test_request_context('/'):
            html = app.jinja_env.get_template('partials/ipcr_history.html').render(ipcr_history=[])
            self.assertIn('No past IPCR records yet', html)


if __name__ == '__main__':
    unittest.main()
