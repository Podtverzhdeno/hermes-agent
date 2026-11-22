"""Offline tests for no-false-green and parallel-worker integration gates."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'gpt_integration_guard.py'
spec = importlib.util.spec_from_file_location('gpt_integration_guard', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def pr(number, head, base='main', paths=(), checks=None, base_sha='a'*40, head_sha=None):
    return {'number': number, 'head': head, 'base': base,
            'head_sha': head_sha or format(number, '040x'), 'base_sha': base_sha,
            'changed_files': len(paths), 'files': list(paths), 'checks': checks}


def snapshot(*items, protected=True):
    return {'schema_version': 1, 'repository': 'Podtverzhdeno/hermes-agent',
            'baseline_sha': 'a'*40, 'main_protected': protected, 'prs': list(items)}


class IntegrationGateTests(unittest.TestCase):
    def test_no_false_green_without_ci(self):
        r = mod.evaluate(snapshot(pr(1, 'alpha')))
        self.assertEqual(r['status'], 'BLOCKED')
        self.assertIn('CI_UNVERIFIED', [x['code'] for x in r['issues']])

    def test_parallel_gateway_collision(self):
        r = mod.evaluate(snapshot(pr(4, 'a', paths=['gateway/platforms/api_server.py']),
                                  pr(5, 'b', paths=['gateway/platforms/api_server.py'])))
        self.assertTrue(any(x['code'] == 'PARALLEL_PATH_OVERLAP' and x['severity'] == 'critical'
                            for x in r['issues']))

    def test_stacked_parent_head_moves(self):
        parent = pr(4, 'parent', paths=['gateway/platforms/api_server.py'])
        child = pr(11, 'child', base='parent', base_sha='f'*40,
                   paths=['gateway/platforms/api_server.py'])
        codes = [x['code'] for x in mod.evaluate(snapshot(parent, child))['issues']]
        self.assertIn('STACKED_BASE_STALE', codes)
        self.assertIn('STACKED_PATH_OVERLAP', codes)

    def test_dedicated_observers_require_architecture_decision(self):
        r = mod.evaluate(snapshot(pr(8, 'a', paths=['hermes_gpt_bridge/diagnostics.py']),
                                  pr(12, 'b', paths=['gpt_companion/journal.py'])))
        self.assertIn('DUPLICATE_OBSERVER_DESIGNS', [x['code'] for x in r['issues']])

    def test_incomplete_files_fail_closed(self):
        candidate = pr(1, 'a', paths=['a.py'])
        candidate['changed_files'] = 2
        with self.assertRaises(mod.IncompleteScan):
            mod.evaluate(snapshot(candidate))

    def test_missing_sha_fails_closed(self):
        candidate = pr(1, 'a'); candidate['head_sha'] = ''
        with self.assertRaises(mod.IncompleteScan):
            mod.evaluate(snapshot(candidate))

    def test_duplicate_pr_and_head_branch_fail_closed(self):
        with self.assertRaises(mod.IncompleteScan):
            mod.evaluate(snapshot(pr(1, 'a'), pr(1, 'b')))
        with self.assertRaises(mod.IncompleteScan):
            mod.evaluate(snapshot(pr(1, 'a'), pr(2, 'a')))

    def test_exact_sha_completed_check(self):
        p = pr(1, 'a')
        p['checks'] = [{'name': 'test', 'status': 'completed', 'conclusion': 'success',
                        'head_sha': p['head_sha']}]
        self.assertEqual(mod.evaluate(snapshot(p))['status'], 'REVIEW')
        p['checks'][0]['head_sha'] = 'b'*40
        self.assertIn('CI_NOT_GREEN_AT_EXACT_HEAD',
                      [x['code'] for x in mod.evaluate(snapshot(p))['issues']])

    def test_no_code_overlap_docs_only(self):
        left = pr(1, 'a', paths=['docs/shared.md'])
        right = pr(2, 'b', paths=['docs/shared.md'])
        r = mod.evaluate(snapshot(left, right))
        overlaps = [x for x in r['issues'] if x['code'] == 'PARALLEL_PATH_OVERLAP']
        self.assertEqual(overlaps[0]['severity'], 'medium')

    def test_unprotected_main_flagged(self):
        r = mod.evaluate(snapshot(protected=False))
        self.assertIn('MAIN_UNPROTECTED', [x['code'] for x in r['issues']])

    def test_journal_idempotent_and_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'audit.sqlite')
            a = mod.evaluate(snapshot(pr(1, 'a')))
            b = mod.evaluate(snapshot(pr(2, 'b')))
            self.assertTrue(mod.journal(path, a))
            self.assertFalse(mod.journal(path, a))
            self.assertTrue(mod.journal(path, b))
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM audit_snapshots').fetchone()[0], 2)

    def test_cli_bad_snapshot_exits_unknown_not_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'in.json'
            p.write_text(json.dumps({'schema_version': 1}), encoding='utf-8')
            cp = subprocess.run([sys.executable, str(MODULE_PATH), '--snapshot', str(p)],
                                capture_output=True, text=True)
            self.assertEqual(cp.returncode, 3)
            self.assertIn('EVIDENCE_INCOMPLETE', cp.stderr)

    def test_repo_arg_cannot_override_host(self):
        with self.assertRaises(ValueError):
            mod.collect('github.com/owner/repo')


if __name__ == '__main__':
    unittest.main()
