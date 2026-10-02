import json
from pathlib import Path
import tempfile
import unittest
import test_runtime_recovery as recovery_fixtures
from local_control.evaluation import check_patch
from local_control.diagnostics import report


class Evaluation(unittest.TestCase):
    def test_patch_checks_behavior_without_executing_code(self):
        with tempfile.TemporaryDirectory() as folder:
            source = 'def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n'
            result = check_patch(json.dumps({'path':'clamp.py','content':source}), Path(folder))
            self.assertEqual(result['passed'],8)
            bad = check_patch(json.dumps({'path':'clamp.py','content':'def clamp(value, lower, upper):\n    return value\n'}), Path(folder))
            self.assertLess(bad['passed'],bad['total'])

    def test_path_traversal_imports_and_arbitrary_calls_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for path,content in [('../escape',''), ('clamp.py','import os'),
                                 ('clamp.py','def clamp(value, lower, upper):\n    return __import__("os")\n')]:
                with self.assertRaises(ValueError):check_patch(json.dumps({'path':path,'content':content}),Path(folder))


class Support(unittest.TestCase):
    setUp = recovery_fixtures.Recovery.setUp

    def test_allowlist_omits_seeded_private_data_even_in_evidence(self):
        secret='seeded-private-secret'
        self.control.config['primary']['contract']={'level':secret}
        self.control.config['nodes']['local']['name']=secret
        self.control.events=[{'message':secret}]
        self.control.jobs={'one':{'status':secret,'operation':secret,'detail':secret,'result':{'secret':secret}}}
        value=json.dumps(report(self.control))
        self.assertNotIn(secret,value)
        self.assertNotIn(str(self.root),value)
