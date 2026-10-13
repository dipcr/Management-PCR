"""Regression checks without importing the application's live DB startup."""
import ast
from pathlib import Path
import sys
import sqlite3
import types
import unittest
from unittest.mock import patch


class TestOversightEvidenceScoring(unittest.TestCase):
    def aggregate(self, role, linked, own, files, assignment_db=None, oversight=None):
        source = Path(__file__).parent / 'app/models/designated.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == 'get_oversight_evidence')
        connection = types.ModuleType('app.models.connection')
        institution = types.ModuleType('app.models.institution')
        institution.ROLE_RET = 'RET'
        institution.ROLE_DEAN_ALL_DEPARTMENTS = 'Dean'

        def query(cursor, sql, params, label):
            if label == 'get_oversight_evidence_targets':
                return list(linked)
            if label == 'get_oversight_evidence_assigned':
                if assignment_db is None:
                    return []
                return [dict(row) for row in assignment_db.execute(sql.replace('%s', '?'), params)]
            if label == 'get_oversight_evidence_own':
                return own
            if label == 'get_oversight_evidence_files':
                return [f for f in files if f['target_id'] in params]
            raise AssertionError(label)

        connection.timed_query = query
        namespace = {
            'get_oversight_cascade_role': lambda cursor, emp_id: role,
            'get_oversight_indicator_ids': lambda cursor, emp_id, term_id: (oversight or {}).get(emp_id, set()),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        with patch.dict(sys.modules, {'app.models.connection': connection,
                                     'app.models.institution': institution}):
            return namespace['get_oversight_evidence'](None, 1, 1, 1)

    def row(self, target_id, quantity):
        return dict(target_id=target_id, actual_quantity=quantity,
                    actual_duration_value=5, efficiency_rating_E=None,
                    first_name='Test', last_name='Faculty')

    def file(self, target_id):
        return dict(evidence_id=target_id, target_id=target_id, file_path='test.pdf',
                    actual_qty_Q=81, verification_status='Pending')

    def test_dean_only_upload_counts_without_appearing_as_linked(self):
        result = self.aggregate('Dean', [], [self.row(10, 81)], [self.file(10)])
        self.assertEqual(result['total_actual_quantity'], 81)
        self.assertEqual(result['max_actual_duration_value'], 5)
        self.assertEqual(result['evidence_count'], 1)
        self.assertEqual(result['evidence_breakdown'], [])

    def test_mixed_uploads_count_both_but_link_only_faculty(self):
        result = self.aggregate('Dean', [self.row(20, 10)], [self.row(10, 81)],
                                [self.file(10), self.file(20)])
        self.assertEqual(result['total_actual_quantity'], 91)
        self.assertEqual(result['evidence_count'], 2)
        self.assertEqual([f['evidence_id'] for f in result['evidence_breakdown']], [20])

    def test_chair_counts_only_linked_evidence(self):
        result = self.aggregate('Department', [self.row(20, 10)], [self.row(10, 81)],
                                [self.file(10), self.file(20)])
        self.assertEqual(result['total_actual_quantity'], 10)
        self.assertEqual(result['evidence_count'], 1)

    def test_no_files_keeps_evidence_count_zero(self):
        result = self.aggregate('Dean', [], [self.row(10, 0)], [])
        self.assertEqual(result['evidence_count'], 0)

    def test_dean_links_explicit_college_wide_assignments_without_oversight_copies(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory = sqlite3.Row
            db.executescript("""
                CREATE TABLE tbl_committed_targets (
                    target_id INTEGER, emp_id INTEGER, indicator_id INTEGER,
                    actual_quantity INTEGER, actual_duration_value INTEGER,
                    efficiency_rating_E INTEGER, is_admin_function INTEGER);
                CREATE TABLE tbl_employee_profiles (emp_id INTEGER, first_name TEXT, last_name TEXT);
                CREATE TABLE tbl_master_indicators (indicator_id INTEGER, term_id INTEGER);
                CREATE TABLE tbl_draft_allocation (emp_id INTEGER, indicator_id INTEGER, assigned_quantity INTEGER);
                CREATE TABLE tbl_cascaded_quotas (indicator_id INTEGER, assigned_to_role TEXT, total_target_value INTEGER);
                INSERT INTO tbl_master_indicators VALUES (1, 1), (2, 1), (3, 2);
                INSERT INTO tbl_cascaded_quotas VALUES (1, 'College-Wide', 2), (1, 'College-Wide', 2);
                INSERT INTO tbl_employee_profiles VALUES
                    (1, 'Dean', 'Own'), (2, 'BSDS', 'Chair'), (3, 'DST', 'Chair'),
                    (4, 'Other', 'Chair'), (5, 'Unassigned', 'Faculty');
                INSERT INTO tbl_draft_allocation VALUES
                    (1, 1, 2), (2, 1, 1), (2, 1, 1), (3, 1, 1), (4, 1, 1),
                    (2, 2, 1), (2, 3, 1);
                INSERT INTO tbl_committed_targets VALUES
                    (10, 1, 1, 2, 5, NULL, 1),
                    (20, 2, 1, 1, 4, NULL, 1),
                    (30, 3, 1, 1, 5, NULL, 1),
                    (40, 4, 1, 50, 9, NULL, 1),
                    (50, 5, 1, 50, 9, NULL, 1),
                    (60, 2, 2, 50, 9, NULL, 1),
                    (70, 2, 3, 50, 9, NULL, 1);
            """)
            result = self.aggregate('Dean', [], [self.row(10, 2)],
                                    [self.file(i) for i in (10, 20, 30, 40, 50, 60, 70)],
                                    assignment_db=db, oversight={4: {1}})
        self.assertEqual(result['total_actual_quantity'], 4)
        self.assertEqual(result['max_actual_duration_value'], 5)
        self.assertEqual(result['evidence_count'], 3)
        self.assertEqual([f['evidence_id'] for f in result['evidence_breakdown']], [20, 30])


if __name__ == '__main__':
    unittest.main()
