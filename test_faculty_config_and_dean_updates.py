"""
Tests for the Admin/Dean changes from the "recheck Faculty Configuration" /
"Silent vs To Chairs" / "Program column" work:

  - Faculty Configuration: block a 2nd Program Chair per specialization, or a
    2nd college-wide RET Chair/Dean (app/models/user.py: find_designation_conflict)
  - Designation change auto-syncs the employee's login system_role
    (app/models/user.py: sync_system_role_for_designation)
  - CSV bulk import applies the same conflict check and role sync
    (app/models/user.py: import_csv_roster)
  - Admin term-open "recheck Faculty Configuration" banner / Mark as Reviewed
    (app/models/term.py: mark_faculty_config_reviewed)
  - Dean dashboard tables now select specialization instead of assigned_program
    (app/models/dean.py: get_designated_draft_submissions,
    get_college_wide_allocations_tracker)

Mirrors this project's existing convention (see test_notifications.py): plain
unittest, mocked cursor/connection for logic-level tests so they run without
touching the shared dev database. The TestLiveIntegration class at the bottom
is the exception -- it exercises the real HTTP routes against the live DB
configured in .env, using only read-only checks and self-cleaning throwaway
rows (created and deleted within the same test). Run it deliberately, not as
part of routine/CI runs, since it needs real DB connectivity:

    python test_faculty_config_and_dean_updates.py                     # everything
    python -m unittest test_faculty_config_and_dean_updates.TestDesignationConflict  # one class
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from app import app
from app.models.user import (
    SINGLETON_DESIGNATIONS,
    find_designation_conflict,
    sync_system_role_for_designation,
    import_csv_roster,
)
from app.models.term import mark_faculty_config_reviewed
from app.models.dean import (
    get_designated_draft_submissions,
    get_college_wide_allocations_tracker,
)


class _AppContextTestCase(unittest.TestCase):
    """Common setup: push an app context so app.models.connection imports resolve."""

    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()


# ──────────────────────────────────────────────
# find_designation_conflict — Faculty Configuration singleton-role guard
# ──────────────────────────────────────────────
class TestDesignationConflict(_AppContextTestCase):

    def _cursor_returning(self, row):
        cur = MagicMock()
        cur.fetchone.return_value = row
        return cur

    def test_non_singleton_designations_never_query_the_db(self):
        cur = MagicMock()
        for designation in ('Regular Faculty', 'Designated Faculty', '', None):
            self.assertIsNone(find_designation_conflict(cur, designation, 'WST Program'))
        cur.execute.assert_not_called()

    def test_program_chair_conflict_is_scoped_to_specialization(self):
        cur = self._cursor_returning(('9999', 'Existing', 'Chair', 'WST Program'))
        result = find_designation_conflict(cur, 'Program Chair', 'WST Program',
                                            exclude_employee_id_number='NEW-1')
        self.assertEqual(result['employee_id_number'], '9999')
        query, params = cur.execute.call_args[0]
        self.assertIn('specialization = %s', query)
        self.assertIn('WST Program', params)

    def test_program_chair_without_a_specialization_short_circuits(self):
        cur = MagicMock()
        result = find_designation_conflict(cur, 'Program Chair', '',
                                            exclude_employee_id_number='NEW-1')
        self.assertIsNone(result)
        cur.execute.assert_not_called()

    def test_ret_chair_conflict_is_college_wide_not_specialization_scoped(self):
        cur = self._cursor_returning(('1111', 'Existing', 'RETChair', 'DST Program'))
        result = find_designation_conflict(cur, 'RET Chair', 'Anything Here',
                                            exclude_employee_id_number='NEW-1')
        self.assertEqual(result['employee_id_number'], '1111')
        query, params = cur.execute.call_args[0]
        self.assertNotIn('specialization = %s', query)

    def test_dean_conflict_is_college_wide(self):
        cur = self._cursor_returning(('2222', 'Existing', 'Dean', 'WST Program'))
        result = find_designation_conflict(cur, 'Dean', None,
                                            exclude_employee_id_number='NEW-1')
        self.assertEqual(result['employee_id_number'], '2222')

    def test_no_conflict_when_seat_is_free(self):
        cur = self._cursor_returning(None)
        result = find_designation_conflict(cur, 'Program Chair', 'Brand New Spec',
                                            exclude_employee_id_number='NEW-1')
        self.assertIsNone(result)

    def test_self_edit_excludes_the_current_holder(self):
        # excludes 'CURRENT-1' -- simulate that by having the mock return None,
        # which is what the real WHERE ... employee_id_number != %s would do.
        cur = self._cursor_returning(None)
        result = find_designation_conflict(cur, 'Program Chair', 'WST Program',
                                            exclude_employee_id_number='CURRENT-1')
        self.assertIsNone(result)
        _, params = cur.execute.call_args[0]
        self.assertIn('CURRENT-1', params)

    def test_singleton_designations_constant_matches_the_three_roles(self):
        self.assertEqual(set(SINGLETON_DESIGNATIONS), {'Program Chair', 'RET Chair', 'Dean'})


# ──────────────────────────────────────────────
# sync_system_role_for_designation — login role follows designation changes
# ──────────────────────────────────────────────
class TestRoleSync(_AppContextTestCase):

    def test_updates_role_and_commits(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.rowcount = 1
        result = sync_system_role_for_designation(conn, cur, 42, 'Program Chair')
        self.assertTrue(result)
        conn.commit.assert_called_once()
        _, params = cur.execute.call_args[0]
        self.assertIn('PROGRAM_CHAIR', params)
        self.assertIn(42, params)

    def test_returns_false_when_employee_has_no_system_access_row(self):
        conn = MagicMock()
        cur = MagicMock()
        cur.rowcount = 0  # UPDATE matched nothing -- unclaimed account
        result = sync_system_role_for_designation(conn, cur, 999, 'Dean')
        self.assertFalse(result)

    def test_every_designation_maps_to_the_expected_role(self):
        expected = {
            'Dean': 'DEAN',
            'Program Chair': 'PROGRAM_CHAIR',
            'RET Chair': 'RET_CHAIR',
            'Designated Faculty': 'DESIGNATED_FACULTY',
            'Regular Faculty': 'FACULTY',
            'Admin': 'Admin',
            None: 'FACULTY',
        }
        for designation, role in expected.items():
            conn, cur = MagicMock(), MagicMock()
            cur.rowcount = 1
            sync_system_role_for_designation(conn, cur, 1, designation)
            _, params = cur.execute.call_args[0]
            self.assertIn(role, params, f"designation={designation!r} should map to {role!r}")


# ──────────────────────────────────────────────
# import_csv_roster — batch conflict skip + role sync during bulk import
# ──────────────────────────────────────────────
class TestCsvBatchConflict(_AppContextTestCase):

    @staticmethod
    def _row(emp_id, designation, specialization='Spec', **overrides):
        row = {
            'employee_id_number': emp_id, 'first_name': emp_id, 'last_name': 'Test',
            'college': 'CICT', 'assigned_program': 'BSIT', 'specialization': specialization,
            'academic_rank': 'Instructor I', 'employment_status': 'Full-time',
            'leave_status': 'Active', 'designation': designation,
        }
        row.update(overrides)
        return row

    def _cursor_with_existing(self, existing_rows):
        cur = MagicMock()
        cur.description = [
            ('emp_id',), ('employee_id_number',), ('first_name',), ('last_name',),
            ('college',), ('assigned_program',), ('specialization',), ('academic_rank',),
            ('employment_status',), ('leave_status',), ('designation',),
        ]
        cur.fetchall.return_value = existing_rows
        return cur

    def test_second_conflicting_program_chair_in_same_file_is_skipped(self):
        conn = MagicMock()
        cur = self._cursor_with_existing([])  # nobody in the DB yet
        rows = [self._row('A', 'Program Chair'), self._row('B', 'Program Chair')]
        success, new_added, updated, unchanged, conflicts = import_csv_roster(conn, cur, rows)
        self.assertTrue(success)
        self.assertEqual(new_added, 1)
        self.assertEqual(len(conflicts), 1)
        self.assertIn('B', conflicts[0])
        self.assertIn('Program Chair', conflicts[0])

    def test_conflict_against_a_pre_existing_db_holder_is_skipped(self):
        conn = MagicMock()
        existing = (1, 'X', 'Existing', 'Chair', 'CICT', 'BSIT', 'Spec',
                    'Instructor I', 'Full-time', 'Active', 'RET Chair')
        cur = self._cursor_with_existing([existing])
        rows = [self._row('NEWGUY', 'RET Chair')]
        success, new_added, updated, unchanged, conflicts = import_csv_roster(conn, cur, rows)
        self.assertEqual(new_added, 0)
        self.assertEqual(len(conflicts), 1)

    def test_regular_and_designated_faculty_never_conflict_even_in_same_specialization(self):
        conn = MagicMock()
        cur = self._cursor_with_existing([])
        rows = [self._row(f'F{i}', d, specialization='Same Spec')
                for i, d in enumerate(['Regular Faculty', 'Regular Faculty', 'Designated Faculty'])]
        success, new_added, updated, unchanged, conflicts = import_csv_roster(conn, cur, rows)
        self.assertEqual(new_added, 3)
        self.assertEqual(conflicts, [])

    def test_designation_change_on_an_existing_row_syncs_system_role(self):
        conn = MagicMock()
        existing = (7, 'PROMO', 'Some', 'Body', 'CICT', 'BSIT', 'Spec',
                    'Instructor I', 'Full-time', 'Active', 'Regular Faculty')
        cur = self._cursor_with_existing([existing])
        rows = [self._row('PROMO', 'Program Chair')]  # promoted from Regular Faculty
        import_csv_roster(conn, cur, rows)
        # last execute() call before the final commit should be the system_access role sync
        executed_queries = [c.args[0] for c in cur.execute.call_args_list]
        self.assertTrue(any('tbl_system_access' in q for q in executed_queries))


# ──────────────────────────────────────────────
# mark_faculty_config_reviewed — term-open banner dismissal
# ──────────────────────────────────────────────
class TestMarkFacultyReviewed(_AppContextTestCase):

    def test_updates_and_commits_when_term_exists(self):
        conn, cur = MagicMock(), MagicMock()
        cur.rowcount = 1
        self.assertTrue(mark_faculty_config_reviewed(conn, cur, 64))
        conn.commit.assert_called_once()

    def test_returns_false_when_term_does_not_exist(self):
        conn, cur = MagicMock(), MagicMock()
        cur.rowcount = 0
        self.assertFalse(mark_faculty_config_reviewed(conn, cur, 999999))


# ──────────────────────────────────────────────
# Dean dashboard queries — specialization replaces assigned_program
# ──────────────────────────────────────────────
class TestDeanSpecializationColumns(_AppContextTestCase):

    @patch('app.models.connection.timed_query')
    def test_designated_draft_submissions_selects_specialization(self, mock_timed_query):
        mock_timed_query.return_value = []
        get_designated_draft_submissions(MagicMock(), 64)
        query = mock_timed_query.call_args[0][1]
        self.assertIn('ep.specialization', query)
        self.assertNotIn('assigned_program', query)

    @patch('app.models.connection.timed_query')
    def test_college_wide_allocations_selects_specialization(self, mock_timed_query):
        mock_timed_query.return_value = []
        get_college_wide_allocations_tracker(MagicMock(), 64)
        query = mock_timed_query.call_args[0][1]
        self.assertIn('ep.specialization', query)
        self.assertNotIn('assigned_program', query)


# ──────────────────────────────────────────────
# Live integration checks -- real DB, real HTTP routes, self-cleaning.
# Skipped unless RUN_LIVE_DB_TESTS=1, since it needs the .env DB reachable
# and writes (and deletes) a couple of throwaway rows against the shared
# dev database.
# ──────────────────────────────────────────────
@unittest.skipUnless(os.getenv('RUN_LIVE_DB_TESTS') == '1',
                      "set RUN_LIVE_DB_TESTS=1 to run against the real dev database")
class TestLiveIntegration(unittest.TestCase):

    TEST_ID = 'AUTOTEST-FCDU-1'

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['user_id'] = 3  # seed Admin account, see README/SETUP.md
            sess['role'] = 'ADMIN'

    def tearDown(self):
        from app.models.connection import get_db_connection
        with app.app_context():
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM tbl_employee_profiles WHERE employee_id_number LIKE 'AUTOTEST-%'")
            conn.commit()
            cur.close()
            conn.close()

    def test_duplicate_program_chair_is_blocked_over_http(self):
        # WST Program already has a Program Chair on the live roster (see SETUP.md fixtures) --
        # trying to add a second one must be rejected without writing anything.
        resp = self.client.post('/admin/faculty/save', data={
            'employee_id_number': self.TEST_ID, 'first_name': 'Auto', 'last_name': 'Test',
            'college': 'CICT', 'assigned_program': 'BSIT', 'specialization': 'WST Program',
            'academic_rank': 'Instructor I', 'employment_status': 'Full-time',
            'leave_status': 'Active', 'designation': 'Program Chair',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Cannot save', html)

        from app.models.connection import get_db_connection
        with app.app_context():
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM tbl_employee_profiles WHERE employee_id_number = %s",
                        (self.TEST_ID,))
            self.assertEqual(cur.fetchone()[0], 0, "blocked save must not write a row")
            cur.close()
            conn.close()

    def test_regular_faculty_save_succeeds_in_the_same_specialization(self):
        resp = self.client.post('/admin/faculty/save', data={
            'employee_id_number': self.TEST_ID, 'first_name': 'Auto', 'last_name': 'Test',
            'college': 'CICT', 'assigned_program': 'BSIT', 'specialization': 'WST Program',
            'academic_rank': 'Instructor I', 'employment_status': 'Full-time',
            'leave_status': 'Active', 'designation': 'Regular Faculty',
        }, follow_redirects=True)
        html = resp.get_data(as_text=True)
        self.assertIn('saved successfully', html)


if __name__ == '__main__':
    unittest.main()
