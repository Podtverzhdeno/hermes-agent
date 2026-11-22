"""Offline tests for no-false-green and parallel-worker integration gates."""
import importlib.util
import io
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
        p['checks'] = [{'name': n, 'status': 'completed', 'conclusion': 'success',
                        'head_sha': p['head_sha']}
                       for n in ('test', 'Scan PR for supply chain risks')]
        self.assertEqual(mod.evaluate(snapshot(p))['status'], 'REVIEW')
        p['checks'][0]['head_sha'] = 'b'*40
        self.assertIn('CI_EVIDENCE_SHA_MISMATCH',
                      [x['code'] for x in mod.evaluate(snapshot(p))['issues']])

    def test_no_code_overlap_docs_only(self):
        left = pr(1, 'a', paths=['docs/shared.md'])
        right = pr(2, 'b', paths=['docs/shared.md'])
        r = mod.evaluate(snapshot(left, right))
        overlaps = [x for x in r['issues'] if x['code'] == 'PARALLEL_PATH_OVERLAP']
        self.assertEqual(overlaps[0]['severity'], 'medium')

    def test_ci_skipped_optional_publish_does_not_erase_required_green(self):
        p = pr(1, 'a')
        p['checks'] = [
            {'name': n, 'status': 'completed', 'conclusion': 'success',
             'head_sha': p['head_sha']}
            for n in ('test', 'Scan PR for supply chain risks')]
        p['checks'].append({'name': 'build-and-push', 'status': 'completed',
                            'conclusion': 'skipped', 'head_sha': p['head_sha']})
        self.assertEqual(mod.evaluate(snapshot(p))['status'], 'REVIEW')

    def test_ci_unrelated_green_check_cannot_replace_required_tests(self):
        p = pr(1, 'a')
        p['checks'] = [{'name': 'lint', 'status': 'completed', 'conclusion': 'success',
                        'head_sha': p['head_sha']}]
        codes = [x['code'] for x in mod.evaluate(snapshot(p))['issues']]
        self.assertIn('REQUIRED_CI_MISSING', codes)

    def test_ci_unexpected_skipped_check_is_not_silent_success(self):
        p = pr(1, 'a')
        p['checks'] = [
            {'name': n, 'status': 'completed', 'conclusion': 'success',
             'head_sha': p['head_sha']}
            for n in ('test', 'Scan PR for supply chain risks')]
        p['checks'].append({'name': 'security', 'status': 'completed',
                            'conclusion': 'skipped', 'head_sha': p['head_sha']})
        self.assertIn('CI_NOT_GREEN_AT_EXACT_HEAD',
                      [x['code'] for x in mod.evaluate(snapshot(p))['issues']])

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
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM audit_snapshots').fetchone()[0], 2)

    def test_cli_bad_snapshot_exits_unknown_not_clean(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'in.json'
            p.write_text(json.dumps({'schema_version': 1}), encoding='utf-8')
            cp = subprocess.run([sys.executable, str(MODULE_PATH), '--snapshot', str(p)],
                                capture_output=True, text=True)
            self.assertEqual(cp.returncode, 3)
            self.assertIn('EVIDENCE_INCOMPLETE', cp.stderr)

    def test_live_collection_fetches_pr_detail_for_changed_files(self):
        # GitHub GET /pulls does not include the changed_files field.
        sha = '4'*40
        listing = {'number': 4, 'head': {'sha': sha, 'ref': 'branch'},
                   'base': {'sha': 'a'*40, 'ref': 'main'}, 'draft': True}
        detail = dict(listing, changed_files=1)

        def fake_get(repo, path, token):
            if path == 'branches/main':
                return {'commit': {'sha': 'a'*40}, 'protected': False}
            if path.startswith('pulls?'):
                return [listing]
            if path == 'pulls/4':
                return detail
            if path.startswith('pulls/4/files?'):
                return [{'filename': 'gateway/platforms/api_server.py'}]
            if path.startswith('commits/'):
                return {'total_count': 0, 'check_runs': []}
            raise AssertionError(path)

        with mock.patch.object(mod, '_get_json', side_effect=fake_get):
            report = mod.collect('Podtverzhdeno/hermes-agent')
        self.assertEqual(report['prs'][0]['changed_files'], 1)
        self.assertEqual(report['prs'][0]['head_sha'], sha)

    def test_live_collection_rejects_head_shift_between_list_and_detail(self):
        listing = {'number': 4, 'head': {'sha': '4'*40, 'ref': 'branch'},
                   'base': {'sha': 'a'*40, 'ref': 'main'}}
        def fake_get(repo, path, token):
            if path == 'branches/main':
                return {'commit': {'sha': 'a'*40}, 'protected': False}
            if path.startswith('pulls?'):
                return [listing]
            if path == 'pulls/4':
                return {**listing, 'head': {**listing['head'], 'sha': '5'*40}, 'changed_files': 1}
            raise AssertionError(path)
        with mock.patch.object(mod, '_get_json', side_effect=fake_get):
            with self.assertRaises(mod.IncompleteScan):
                mod.collect('Podtverzhdeno/hermes-agent')

    def test_live_collection_rejects_added_pr_during_scan(self):
        listing = {'number': 4, 'head': {'sha': '4'*40, 'ref': 'branch'},
                   'base': {'sha': 'a'*40, 'ref': 'main'}}
        detail = {**listing, 'changed_files': 1}
        calls = [0]

        def fake_get(repo, path, token):
            if path == 'branches/main':
                return {'commit': {'sha': 'a'*40}, 'protected': False}
            if path.startswith('pulls?'):
                calls[0] += 1
                return [listing] if calls[0] == 1 else [listing, {
                    **listing, 'number': 5, 'head': {'sha': '5'*40, 'ref': 'new'}}]
            if path == 'pulls/4':
                return detail
            if path.startswith('pulls/4/files?'):
                return [{'filename': 'gateway/platforms/api_server.py'}]
            if path.startswith('commits/'):
                return {'total_count': 0, 'check_runs': []}
            raise AssertionError(path)
        with mock.patch.object(mod, '_get_json', side_effect=fake_get):
            with self.assertRaisesRegex(mod.IncompleteScan, 'changed during scan'):
                mod.collect('Podtverzhdeno/hermes-agent')

    def test_live_collection_rejects_moving_main_head(self):
        calls = [0]
        def fake_get(repo, path, token):
            if path == 'branches/main':
                calls[0] += 1
                return {'commit': {'sha': ('a' if calls[0] == 1 else 'b')*40},
                        'protected': False}
            if path.startswith('pulls?'):
                return []
            raise AssertionError(path)
        with mock.patch.object(mod, '_get_json', side_effect=fake_get):
            with self.assertRaisesRegex(mod.IncompleteScan, 'Main HEAD changed'):
                mod.collect('Podtverzhdeno/hermes-agent')

    def test_github_request_is_get_only_and_redirects_disabled(self):
        payload = io.BytesIO(b'{"ok": true}')
        with mock.patch.object(mod._SAFE_OPENER, 'open', return_value=payload) as opened:
            result = mod._get_json('Podtverzhdeno/hermes-agent', 'branches/main', 'fake')
        req = opened.call_args.args[0]
        self.assertEqual(result, {'ok': True})
        self.assertEqual(req.get_method(), 'GET')
        self.assertEqual(req.full_url,
                         'https://api.github.com/repos/Podtverzhdeno/hermes-agent/branches/main')
        self.assertEqual(req.headers['Authorization'], 'Bearer fake')
        self.assertIsNone(mod._NoRedirect().redirect_request(None, None, 302, '', {},
                                                               'https://elsewhere.example/'))

    def test_repo_arg_cannot_override_host(self):
        with self.assertRaises(ValueError):
            mod.collect('github.com/owner/repo')


if __name__ == '__main__':
    unittest.main()
