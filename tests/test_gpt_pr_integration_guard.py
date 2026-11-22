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
    return dict(number=n, paths=paths, renamed_from_paths=[], changed_files=len(paths),
                head_ref=head or f'feature-{n}', head_repo='test/repo',
                head_sha=(str(n % 10) * 40), base_ref=base,
                base_repo='test/repo', base_sha=base_sha, draft=True)


def snapshot(*pulls):
    return {'schema': 'hermes.pr.snapshot.v3', 'repository': 'test/repo',
            'default_branch': 'main', 'default_head_sha': 'f'*40, 'collected_at': '2026-11-22T00:00:00+00:00',
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

    def test_fork_same_branch_name_is_not_a_local_parent(self):
        # A PR from outsider/repo:feature must not be confused with
        # a PR targeting test/repo:feature.
        a = pr(1, ['a.py'], head='feature')
        a['head_repo'] = 'outsider/repo'
        b = pr(2, ['b.py'], base='feature', base_sha='a' * 40)
        r = guard.analyze(snapshot(a, b))
        codes = [v['code'] for v in r['findings']]
        self.assertIn('UNTRACKED_STACK_BASE', codes)
        self.assertNotIn('STACK_PARENT_MOVED', codes)

    def test_wrong_changed_file_cardinality_fails_closed(self):
        x = pr(1, ['a.py'])
        x['changed_files'] = 2
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(snapshot(x))

    def test_unknown_source_repository_fails_closed(self):
        x = pr(1, ['a.py'])
        del x['head_repo']
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(snapshot(x))

    def test_nondefault_base_not_in_open_prs_is_review(self):
        x = pr(10, ['docs/ledger.md'], base='snapshots/autopilot-fixed')
        r = guard.analyze(snapshot(x))
        self.assertIn('UNTRACKED_STACK_BASE', [f['code'] for f in r['findings']])

    def test_three_competing_guards_trigger_convergence(self):
        a = pr(14, ['scripts/hermes_gpt_coordination_audit.py'])
        b = pr(18, ['scripts/gpt_integration_guard.py'])
        c = pr(22, ['scripts/gpt_pr_integration_guard.py'])
        r = guard.analyze(snapshot(a, b, c))
        self.assertIn('DUPLICATE_INTEGRATION_GUARDS', [f['code'] for f in r['findings']])

    def test_default_head_sha_required(self):
        x = snapshot(pr(1, ['x.py']))
        x['default_head_sha'] = 'bad'
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(x)

    def test_collector_rejects_changed_file_count_mismatch(self):
        from unittest.mock import patch
        repo = 'test/repo'
        sha = 'a' * 40
        head = {'ref': 'topic', 'sha': 'b' * 40,
                'repo': {'full_name': repo}}
        base = {'ref': 'main', 'sha': sha, 'repo': {'full_name': repo}}
        p = {'number': 4, 'head': head, 'base': base}
        responses = {
            '/repos/test/repo': {'default_branch': 'main'},
            '/repos/test/repo/git/ref/heads/main': {'object': {'sha': sha}},
            '/repos/test/repo/pulls/4': {**p, 'changed_files': 2, 'draft': True},
        }
        def fake_get(path, token):
            return responses[path]
        def fake_pages(path, token, limit, label):
            if path.endswith('/files'):
                return [{'filename': 'x.py'}]
            return [p]
        with patch.object(guard, '_api_json', side_effect=fake_get):
            with patch.object(guard, '_pages', side_effect=fake_pages):
                with self.assertRaises(guard.IncompleteSnapshot):
                    guard.collect(repo)

    def test_collector_detects_default_head_movement(self):
        from unittest.mock import patch
        repo = 'test/repo'
        refs = iter(['a' * 40, 'b' * 40])
        head = {'ref': 'topic', 'sha': 'c' * 40,
                'repo': {'full_name': repo}}
        base = {'ref': 'main', 'sha': 'a' * 40,
                'repo': {'full_name': repo}}
        p = {'number': 4, 'head': head, 'base': base}
        def fake_get(path, token):
            if path.endswith('git/ref/heads/main'):
                return {'object': {'sha': next(refs)}}
            if path.endswith('/pulls/4'):
                return {**p, 'changed_files': 1, 'draft': True}
            return {'default_branch': 'main'}
        def fake_pages(path, token, limit, label):
            return [{'filename': 'x.py'}] if path.endswith('/files') else [p]
        with patch.object(guard, '_api_json', side_effect=fake_get):
            with patch.object(guard, '_pages', side_effect=fake_pages):
                with self.assertRaises(guard.IncompleteSnapshot):
                    guard.collect(repo)

    def test_metadata_collection_green_never_means_runtime_green(self):
        r = guard.analyze(snapshot(pr(1, ['x.py']), pr(2, ['x.py'])))
        self.assertEqual(r['collection_status'], 'COMPLETE_METADATA_SNAPSHOT')
        self.assertEqual(r['integration_verdict'], 'HOLD_FOR_REVIEW')
        self.assertEqual(r['runtime_verdict'], 'UNOBSERVED')
        self.assertEqual(r['ci_verdict'], 'UNVERIFIED')
        summary = guard.markdown(r)
        self.assertIn('HOLD_FOR_REVIEW', summary)
        self.assertIn('UNOBSERVED', summary)

    def test_thirty_agents_colliding_on_one_api_file_are_all_detected(self):
        prs = [pr(n, ['gateway/platforms/api_server.py'])
               for n in range(1, 31)]
        report = guard.analyze(snapshot(*prs))
        collisions = [i for i in report['findings']
                      if i['code'] == 'INDEPENDENT_WRITE_COLLISION']
        self.assertEqual(report['open_pr_count'], 30)
        self.assertEqual(len(collisions), (30 * 29) // 2)
        self.assertEqual(report['integration_verdict'], 'HOLD_FOR_REVIEW')

    def test_one_hundred_disjoint_workers_no_false_collisions_or_merge_approval(self):
        prs = [pr(n, [f'worktrees/agent-{n:03d}/unique.py'])
               for n in range(1, 101)]
        report = guard.analyze(snapshot(*prs))
        self.assertEqual(report['open_pr_count'], 100)
        self.assertEqual(report['counts'], {'blocker': 0, 'review': 0})
        self.assertEqual(report['integration_verdict'], 'REVIEW_ONLY')
        self.assertEqual(report['runtime_verdict'], 'UNOBSERVED')
        self.assertEqual(report['ci_verdict'], 'UNVERIFIED')

    def test_one_hundred_one_workers_refuses_partial_inventory(self):
        prs = [pr(n, [f'worktrees/agent-{n:03d}/unique.py'])
               for n in range(1, 102)]
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(snapshot(*prs))

    def test_rename_source_collides_with_independent_old_path_edit(self):
        renamed = pr(1, ['gateway/modern.py'])
        renamed['renamed_from_paths'] = ['gateway/legacy.py']
        modified = pr(2, ['gateway/legacy.py'])
        report = guard.analyze(snapshot(renamed, modified))
        collisions = [f for f in report['findings']
                      if f['code'] == 'INDEPENDENT_WRITE_COLLISION']
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['paths'], ['gateway/legacy.py'])
        self.assertEqual(collisions[0]['severity'], 'blocker')

    def test_cross_renames_are_not_silently_disjoint(self):
        a = pr(1, ['tools/new.py'])
        a['renamed_from_paths'] = ['tools/old.py']
        b = pr(2, ['tools/old.py'])
        b['renamed_from_paths'] = ['tools/new.py']
        report = guard.analyze(snapshot(a, b))
        collision = next(f for f in report['findings']
                         if f['code'] == 'INDEPENDENT_WRITE_COLLISION')
        self.assertEqual(set(collision['paths']), {'tools/old.py', 'tools/new.py'})

    def test_old_v2_snapshot_and_missing_rename_evidence_fail_closed(self):
        legacy = snapshot(pr(1, ['src/a.py']))
        legacy['schema'] = 'hermes.pr.snapshot.v2'
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(legacy)
        unknown = snapshot(pr(1, ['src/a.py']))
        del unknown['pulls'][0]['renamed_from_paths']
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze(unknown)

    def test_collector_rename_without_previous_filename_is_incomplete(self):
        from unittest.mock import patch
        repo = 'test/repo'
        sha = 'a' * 40
        head = {'ref': 'topic', 'sha': 'b' * 40,
                'repo': {'full_name': repo}}
        base = {'ref': 'main', 'sha': sha, 'repo': {'full_name': repo}}
        p = {'number': 4, 'head': head, 'base': base}
        def fake_get(path, token):
            if path.endswith('/pulls/4'):
                return {**p, 'changed_files': 1, 'draft': True}
            if path.endswith('git/ref/heads/main'):
                return {'object': {'sha': sha}}
            return {'default_branch': 'main'}
        def fake_pages(path, token, limit, label):
            if path.endswith('/files'):
                return [{'filename': 'gateway/new.py', 'status': 'renamed'}]
            return [p]
        with patch.object(guard, '_api_json', side_effect=fake_get):
            with patch.object(guard, '_pages', side_effect=fake_pages):
                with self.assertRaises(guard.IncompleteSnapshot):
                    guard.collect(repo)

    def test_invalid_schema_fails_closed(self):
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze({'pulls': []})


if __name__ == '__main__':
    unittest.main()
