"""Exercise the cascade handler without importing the app's live DB startup."""
import ast
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from flask import Flask, flash, redirect, request


class TestCascadeSharing(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).parent / 'app/routes/dean.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        handler = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef) and node.name == 'cascade_quotas')
        handler.decorator_list = []
        self.save = MagicMock(return_value=(True, 'Saved'))
        namespace = {
            'request': request, 'flash': flash, 'redirect': redirect,
            'url_for': lambda endpoint: '/dean/',
            'get_db_connection': MagicMock(),
            'get_departments': lambda cursor: [{'department_name': 'WST Program'}],
            'SPECIAL_CASCADE_ROLES': ['RET / Extension', 'College-Wide'],
            'save_cascaded_quotas': self.save,
        }
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), 'exec'), namespace)
        self.handler = namespace['cascade_quotas']
        self.app = Flask(__name__)
        self.app.secret_key = 'test'

    def submit(self, choices):
        data = {
            'term_id': '1', 'indicator_id[]': ['1', '2', '3'],
            'quota_0[]': ['4', '0', '0'],
            'quota_1[]': ['0', '2', '0'],
            'quota_2[]': ['80', '2', '6'],
        }
        data.update(choices)
        with self.app.test_request_context('/dean/cascade_quotas', method='POST', data=data):
            self.assertEqual(self.handler().status_code, 302)
        self.save.assert_called_once()
        return self.save.call_args.args[3]

    def test_only_selected_college_wide_target_is_shared(self):
        rows = self.submit({'cw_allow_allocation_1': '0',
                            'cw_allow_allocation_2': '0',
                            'cw_allow_allocation_3': '1'})
        self.assertEqual({r['indicator_id']: r['allow_chair_allocation']
                          for r in rows if r['assigned_role'] == 'College-Wide'},
                         {1: 0, 2: 0, 3: 1})
        self.assertTrue(all(r['allow_chair_allocation'] == 1
                            for r in rows if r['assigned_role'] != 'College-Wide'))

    def test_unselected_values_default_to_dean_only(self):
        for value in (None, '', 'false', 'unexpected'):
            with self.subTest(value=value):
                self.save.reset_mock()
                choices = {} if value is None else {'cw_allow_allocation_1': value}
                rows = self.submit(choices)
                self.assertTrue(all(r['allow_chair_allocation'] == 0
                                    for r in rows if r['assigned_role'] == 'College-Wide'))


if __name__ == '__main__':
    unittest.main()
