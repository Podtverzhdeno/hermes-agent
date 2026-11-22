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

    def test_redirect_policy_does_not_forward_authorization(self):
        policy = guard._NoRedirect()
        with self.assertRaises(guard.IncompleteSnapshot):
            policy.redirect_request(None, None, 302, 'Found', {},
                                    'https://redirect.attacker.invalid/collect')

    def test_offline_snapshots_are_not_claimed_as_live(self):
        fixture = snapshot(pr(1, ['a.py']))
        offline = guard.analyze(fixture, evidence_mode='offline_snapshot')
        self.assertEqual(offline['evidence_mode'], 'offline_snapshot')
        self.assertEqual(offline['snapshot_currentness'], 'UNVERIFIED_OFFLINE')
        self.assertIn('offline snapshot', offline['provenance'])
        self.assertEqual(offline['runtime_verdict'], 'UNOBSERVED')
        live = guard.analyze(fixture, evidence_mode='github_api')
        self.assertEqual(live['snapshot_currentness'], 'RECENT_API_READ_NOT_ATOMIC')
        self.assertIn('non-atomic', live['provenance'])

    def test_offline_cli_report_marks_unverified_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'snapshot.json'
            report = Path(folder) / 'report.json'
            source.write_text(json.dumps(snapshot(pr(1, ['a.py']))), encoding='utf-8')
            self.assertEqual(
                guard.main(['--snapshot-in', str(source), '--report-out', str(report)]), 0,
            )
            saved = json.loads(report.read_text(encoding='utf-8'))
            self.assertEqual(saved['evidence_mode'], 'offline_snapshot')
            self.assertEqual(saved['snapshot_currentness'], 'UNVERIFIED_OFFLINE')

    def test_windows_case_alias_across_independent_agent_paths(self):
        a = pr(1, ['Gateway/State.py'])
        b = pr(2, ['gateway/state.py'])
        report = guard.analyze(snapshot(a, b))
        aliased = [x for x in report['findings']
                   if x['code'] == 'WINDOWS_PATH_ALIAS_ACROSS_PRS']
        self.assertEqual(len(aliased), 1)
        self.assertEqual(aliased[0]['severity'], 'blocker')
        self.assertEqual(set(aliased[0]['paths']),
                         {'Gateway/State.py', 'gateway/state.py'})
        self.assertFalse(any(x['code'] == 'INDEPENDENT_WRITE_COLLISION'
                             for x in report['findings']))

    def test_unicode_normalization_alias_is_suspected_not_certified(self):
        composed = 'docs/caf\u00e9.md'
        decomposed = 'docs/cafe\u0301.md'
        report = guard.analyze(snapshot(pr(1, [composed]), pr(2, [decomposed])))
        self.assertIn('WINDOWS_PATH_ALIAS_ACROSS_PRS',
                      [f['code'] for f in report['findings']])
        self.assertEqual(report['runtime_verdict'], 'UNOBSERVED')

    def test_within_one_pr_windows_alias_blocks_independent_checkout(self):
        item = pr(1, ['Foo.py', 'foo.py'])
        report = guard.analyze(snapshot(item))
        self.assertIn('WINDOWS_PATH_ALIAS_IN_PR',
                      [f['code'] for f in report['findings']])
        self.assertEqual(report['integration_verdict'], 'HOLD_FOR_REVIEW')

    def test_case_only_rename_requires_windows_checkout_review(self):
        renamed = pr(1, ['gateway/modern.py'])
        renamed['renamed_from_paths'] = ['gateway/Modern.py']
        other = pr(2, ['gateway/Modern.py'])
        report = guard.analyze(snapshot(renamed, other))
        self.assertTrue(any(f['code'] == 'INDEPENDENT_WRITE_COLLISION'
                            for f in report['findings']))

    def test_windows_prohibited_device_and_component_names_block_checkout(self):
        samples = [
            'src/CON.txt', 'src/nul.txt', 'docs/AUX.log', 'jobs/COM1.py',
            'jobs/LPT9.txt', 'docs/trailing.', 'docs/trailing ',
            'src/no?.py', 'src/no:name.py', 'src/back\\slash.py',
            'src/control\x01.py', 'src//empty.py', 'src/../parent.py',
        ]
        for path in samples:
            with self.subTest(path=repr(path)):
                report = guard.analyze(snapshot(pr(1, [path])))
                self.assertIn('WINDOWS_UNREPRESENTABLE_PATH',
                              [i['code'] for i in report['findings']])
                self.assertEqual(report['integration_verdict'], 'HOLD_FOR_REVIEW')

    def test_normal_windows_paths_do_not_produce_windows_invalid_warnings(self):
        report = guard.analyze(snapshot(
            pr(1, ['src/runner.py', 'docs/Design Note.md', '.github/workflows/ci.yml'])
        ))
        self.assertNotIn('WINDOWS_UNREPRESENTABLE_PATH',
                         [i['code'] for i in report['findings']])
        self.assertEqual(report['integration_verdict'], 'REVIEW_ONLY')

    def test_bundle_manifest_written_last_and_hashes_verify(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            snap_path, report_path = root / 'snap.json', root / 'report.json'
            markdown_path, manifest_path = root / 'summary.md', root / 'manifest.json'
            data = snapshot(pr(1, ['a.py']))
            report = guard.analyze(data, evidence_mode='offline_snapshot')
            guard._write_bundle(
                snapshot_path=snap_path, report_path=report_path,
                markdown_path=markdown_path, manifest_path=manifest_path,
                snapshot=data, report=report, summary=guard.markdown(report),
            )
            manifest = guard.verify_bundle(
                manifest_path, snapshot_path=snap_path,
                report_path=report_path, markdown_path=markdown_path,
            )
            self.assertEqual(manifest['schema'], 'hermes.pr.bundle.v1')
            self.assertEqual(manifest['evidence_mode'], 'offline_snapshot')
            self.assertEqual(set(manifest['files']), {'snapshot', 'report', 'markdown'})

    def test_partial_or_tampered_bundle_never_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            snap_path, report_path = root / 'snap.json', root / 'report.json'
            manifest_path = root / 'manifest.json'
            data = snapshot(pr(1, ['a.py']))
            report = guard.analyze(data, evidence_mode='offline_snapshot')
            guard._write_bundle(
                snapshot_path=snap_path, report_path=report_path,
                markdown_path=None, manifest_path=manifest_path,
                snapshot=data, report=report, summary=guard.markdown(report),
            )
            report_path.write_text(report_path.read_text(encoding='utf-8') + '\n')
            with self.assertRaises(guard.IncompleteSnapshot):
                guard.verify_bundle(
                    manifest_path, snapshot_path=snap_path,
                    report_path=report_path, markdown_path=None,
                )

    def test_failed_atomic_replace_preserves_last_good_file(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'last-good.json'
            path.write_bytes(b'VALID')
            with patch.object(guard.os, 'replace', side_effect=OSError('simulated crash')):
                with self.assertRaises(OSError):
                    guard._atomic_write(path, b'NEW')
            self.assertEqual(path.read_bytes(), b'VALID')
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ['last-good.json'])

    def test_overlapping_output_targets_rejected_without_write(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'shared.json'
            data = snapshot(pr(1, ['a.py']))
            report = guard.analyze(data, evidence_mode='offline_snapshot')
            with self.assertRaises(guard.IncompleteSnapshot):
                guard._write_bundle(
                    snapshot_path=target, report_path=target,
                    markdown_path=None, manifest_path=None,
                    snapshot=data, report=report, summary=guard.markdown(report),
                )
            self.assertFalse(target.exists())

    def test_offline_cli_verify_bundle_never_fetches_api(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fixture, snap, report = root/'source.json', root/'snap.json', root/'report.json'
            manifest = root/'receipt.json'
            fixture.write_text(json.dumps(snapshot(pr(1, ['a.py']))), encoding='utf-8')
            self.assertEqual(guard.main([
                '--snapshot-in', str(fixture), '--snapshot-out', str(snap),
                '--report-out', str(report), '--manifest-out', str(manifest),
            ]), 0)
            with patch.object(guard, '_api_json', side_effect=AssertionError('network forbidden')):
                self.assertEqual(guard.main([
                    '--verify-manifest', str(manifest),
                    '--snapshot-out', str(snap), '--report-out', str(report),
                ]), 0)

    def test_unhashable_manifest_provenance_fails_closed_not_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = root/'manifest.json'
            m.write_text(json.dumps({
                'schema': 'hermes.pr.bundle.v1',
                'status': 'FILES_WRITTEN_NOT_RUNTIME_VERIFIED',
                'snapshot_sha': 'a'*40,
                'evidence_mode': {'unexpected': 'dict'},
                'files': {},
            }), encoding='utf-8')
            with self.assertRaises(guard.IncompleteSnapshot):
                guard.verify_bundle(m, snapshot_path=None,
                                    report_path=None, markdown_path=None)

    def test_invalid_snapshot_inventory_in_manifest_fails_closed(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            snap_path, report_path, m = root/'snap.json', root/'report.json', root/'manifest.json'
            data = snapshot(pr(1, ['a.py']))
            report = guard.analyze(data, evidence_mode='offline_snapshot')
            guard._write_bundle(
                snapshot_path=snap_path, report_path=report_path,
                markdown_path=None, manifest_path=m,
                snapshot=data, report=report, summary=guard.markdown(report),
            )
            bad = json.loads(snap_path.read_text(encoding='utf-8'))
            bad['pulls'] = None
            bad_raw = (json.dumps(bad, indent=2, ensure_ascii=False)+'\n').encode('utf-8')
            snap_path.write_bytes(bad_raw)
            manifest = json.loads(m.read_text(encoding='utf-8'))
            manifest['files']['snapshot'] = {
                'sha256': hashlib.sha256(bad_raw).hexdigest(),
                'bytes': len(bad_raw),
            }
            m.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaises(guard.IncompleteSnapshot):
                guard.verify_bundle(
                    m, snapshot_path=snap_path,
                    report_path=report_path, markdown_path=None,
                )

    def test_invalid_schema_fails_closed(self):
        with self.assertRaises(guard.IncompleteSnapshot):
            guard.analyze({'pulls': []})


if __name__ == '__main__':
    unittest.main()
