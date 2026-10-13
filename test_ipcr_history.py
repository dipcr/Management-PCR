"""Dashboard rendering regression tests after archive removal; no database connections or writes.

Run with: python -m unittest test_ipcr_history
"""
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

# Application startup normally connects to MySQL. Keep this suite offline.
with patch('mysql.connector.pooling.MySQLConnectionPool'):
    from app import app


class TestDashboardWithoutHistory(unittest.TestCase):
    def test_dashboards_render_without_history_or_an_active_term(self):
        for module, role, path in [
            ('faculty', 'FACULTY', '/faculty/'),
            ('dean', 'DEAN', '/dean/'),
            ('prog_chair', 'PROGRAM_CHAIR', '/prog_chair/'),
            ('ret_chair', 'RET_CHAIR', '/ret_chair/'),
        ]:
            with self.subTest(role=role), ExitStack() as stack:
                conn = MagicMock()
                stack.enter_context(patch(f'app.routes.{module}.get_db_connection', return_value=conn))
                stack.enter_context(patch('app.decorators._account_is_locked', return_value=False))
                stack.enter_context(patch(f'app.routes.{module}.get_all_terms', return_value=[{
                    'term_id': 123, 'is_active': 0,
                }]))
                stack.enter_context(patch('app.models.connection.timed_query', return_value=[]))
                client = app.test_client()
                with client.session_transaction() as session:
                    session['user_id'] = 77
                    session['role'] = role
                    session['specialization'] = 'Test Program'
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertNotIn('Accomplished IPCRs', html)
                self.assertNotIn('No Dean-Approved IPCRs Yet', html)
                conn.cursor.return_value.close.assert_called_once()
                conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
