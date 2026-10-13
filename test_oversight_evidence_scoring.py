"""Regression checks without importing the application's live DB startup."""
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class TestOversightEvidenceScoring(unittest.TestCase):
    def aggregate(self, role, linked, own, files):
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
                return linked
            if label == 'get_oversight_evidence_own':
                return own
            if label == 'get_oversight_evidence_files':
                return [f for f in files if f['target_id'] in params]
            raise AssertionError(label)

        connection.timed_query = query
        namespace = {'get_oversight_cascade_role': lambda cursor, emp_id: role}
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


if __name__ == '__main__':
    unittest.main()
