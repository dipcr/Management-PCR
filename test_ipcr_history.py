"""Dashboard archive regression tests; no database connections or writes.

Run with: python -m unittest test_ipcr_history
"""
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

# Application startup normally connects to MySQL. Keep this suite offline.
with patch('mysql.connector.pooling.MySQLConnectionPool'):
    from app import app


class TestClosedTermHistory(unittest.TestCase):
    def test_personal_history_renders_without_an_active_term(self):
        history = [{
            'term_id': 123, 'academic_year': '2025-2026',
            'semester': 'First Semester', 'rating_period': 'JULY to DECEMBER 2025',
            'final_score': 4.25, 'adjectival_rating': 'Very Satisfactory',
            'total_targets': 7, 'approved_targets': 7,
        }]
        for module, role, path, print_path in [
            ('faculty', 'FACULTY', '/faculty/', '/faculty/print_ipcr'),
            ('dean', 'DEAN', '/dean/', '/designated/print_ipcr'),
            ('prog_chair', 'PROGRAM_CHAIR', '/prog_chair/', '/designated/print_ipcr'),
            ('ret_chair', 'RET_CHAIR', '/ret_chair/', '/designated/print_ipcr'),
        ]:
            with self.subTest(role=role), ExitStack() as stack:
                conn = MagicMock()
                stack.enter_context(patch(f'app.routes.{module}.get_db_connection', return_value=conn))
                stack.enter_context(patch('app.decorators._account_is_locked', return_value=False))
                stack.enter_context(patch(f'app.routes.{module}.get_all_terms', return_value=[{
                    'term_id': 123, 'is_active': 0,
                }]))
                stack.enter_context(patch('app.models.connection.timed_query', return_value=[]))
                archive = stack.enter_context(patch(
                    'app.models.ipcr_form.get_employee_accomplished_ipcrs', return_value=history))
                # Dean imports the function into its route module at startup.
                if module == 'dean':
                    archive = stack.enter_context(patch(
                        'app.routes.dean.get_employee_accomplished_ipcrs', return_value=history))
                client = app.test_client()
                with client.session_transaction() as session:
                    session['user_id'] = 77
                    session['role'] = role
                    session['specialization'] = 'Test Program'
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn('JULY to DECEMBER 2025', html)
                self.assertIn('4.25', html)
                self.assertIn(f'{print_path}?term_id=123', html)
                archive.assert_called_once_with(conn.cursor.return_value, 77)
                conn.cursor.return_value.close.assert_called_once()
                conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
