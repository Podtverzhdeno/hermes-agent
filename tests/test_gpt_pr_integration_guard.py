"""Offline regression suite for read-only PR metadata integration guard."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'gpt_pr_integration_guard.py'
SPEC = importlib.util.spec_from_file_location('guard', PATH)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def pr(n, paths, head=None, base='main', base_sha='0'*40):
    return dict(number=n, paths=paths, head_ref=head or f'feature-{n}',
                head_sha=(str(n % 10) * 40), base_ref=base, base_sha=base_sha, draft=True)


def snapshot(*pulls):
    return {'schema': 'hermes.pr.snapshot.v1', 'repository': 'test/repo',
            'default_head_sha': 'f'*40, 'collected_at': '2026-11-22T00:00:00+00:00',
            'pulls': list(pulls)}


class PRWatchTests(unittest.TestCase):
    def test_independent_api_edit_blocks(self):
        r = guard.analyze(snapshot(pr(1, ['gateway/platforms/api_server.py']),
                                   pr(2, ['gateway/platforms/api_server.py'])))
        self.assertEqual(r['counts']['blocker'], 1)
        self.assertEqual(r['findings'][0]['code'], 'INDEPENDENT_WRITE_COLLISION')

    def test_independent_doc_edit_requires_review(self):
        r = guard.analyze(snapshot(pr(1, ['docs/SDD.md']), pr(2, ['docs/SDD.md'])))
        self.assertEqual(r['counts'], {'blocker': 0, 'review': 1})

    def test_stacked_overlap_requires_review_not_false_independence(self):
        a = pr(1, ['gateway/platforms/api_server.py'], head='parent')
        b = pr(2, ['gateway/platforms/api_server.py'], base='parent', base_sha=a['head_sha'])
        r = guard.analyze(snapshot(a, b))
        self.assertEqual([i['code'] for i in r['findings']], ['STACKED_FILE_OVERLAP'])

    def test_parent_moves_blocker_even_if_different_paths(self):
        a = pr(1, ['README.md'], head='parent')
        b = pr(2, ['tests/test_x.py'], base='parent', base_sha='a'*40)
        r = guard.analyze(snapshot(a, b))
        self.assertIn('STACK_PARENT_MOVED', [i['code'] for i in r['findings']])

    def test_duplicate_observers_without_exact_path_collision(self):
        r = guard.analyze(snapshot(pr(8, ['hermes_gpt_bridge/diagnostics.py']),
                                   pr(9, ['gpt_bridge/observability.py']),
                                   pr(12, ['gpt_companion/journal.py'])))
        self.assertEqual([i['code'] for i in r['findings']], ['OBSERVER_AUTHORITY_SPLIT'])

    def test_missing_paths_never_counted_as_safe(self):
        x = pr(1, [])
        del x['paths']
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(snapshot(x))

    def test_duplicate_branch_name_blocks_ambiguous_lineage(self):
        a = pr(1, ['file.py'], head='same')
        b = pr(2, ['file.py'], head='same')
        c = pr(3, ['unrelated.py'], base='same')
        r = guard.analyze(snapshot(a, b, c))
        self.assertTrue(any(i['code'] == 'INDEPENDENT_WRITE_COLLISION' for i in r['findings']))
        self.assertTrue(any(i['code'] == 'STACK_PARENT_AMBIGUOUS' for i in r['findings']))
        self.assertFalse(any(i['code'] == 'STACK_PARENT_MOVED' for i in r['findings']))

    def test_main_offline_cli_reproducible_and_strict(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.json'
            o = Path(d) / 'report.json'
            p.write_text(json.dumps(snapshot(pr(4, ['a.py']), pr(5, ['a.py']))))
            self.assertEqual(guard.main(['--snapshot-in', str(p), '--report-out', str(o)]), 0)
            self.assertEqual(guard.main(['--snapshot-in', str(p), '--strict']), 2)
            self.assertEqual(json.loads(o.read_text())['counts']['blocker'], 1)

    def test_cycle_is_rejected(self):
        a = pr(1, ['a.py'], head='A', base='B')
        b = pr(2, ['b.py'], head='B', base='A')
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(snapshot(a, b))

    def test_invalid_schema_fails_closed(self):
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze({'pulls': []})


if __name__ == '__main__':
    unittest.main()
