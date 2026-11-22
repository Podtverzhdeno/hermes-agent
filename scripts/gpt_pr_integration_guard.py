#!/usr/bin/env python3
"""Read-only GPT/Hermes PR integration watch. No credentials or task payloads logged."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_PRS = 100
MAX_FILES_PER_PR = 2000
API = 'https://api.github.com'


class IncompleteSnapshot(ValueError):
    """Metadata is missing or cannot be trusted for a safe comparison."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: urllib otherwise forwards Authorization on redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Repo renames/moves may redirect. Do not send the token to a
        # noncanonical endpoint; require a fresh explicitly scoped scan.
        raise IncompleteSnapshot('Unexpected GitHub API redirect; refusing token forwarding')


def _api_json(path: str, token: str) -> Any:
    request = urllib.request.Request(
        API + path,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'hermes-gpt-pr-integration-watch/1',
            'X-GitHub-Api-Version': '2022-11-28',
            **({'Authorization': f'Bearer {token}'} if token else {}),
        },
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=20) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        # Never print returned HTTP bodies or request headers: they may contain secrets.
        raise IncompleteSnapshot(f'GitHub metadata unavailable for {path}: {type(exc).__name__}') from None


def _pages(path: str, token: str, limit: int, label: str) -> list[Any]:
    results: list[Any] = []
    for page in range(1, (limit // 100) + 2):
        separator = '&' if '?' in path else '?'
        chunk = _api_json(f'{path}{separator}per_page=100&page={page}', token)
        if not isinstance(chunk, list):
            raise IncompleteSnapshot(f'Invalid {label} response: expected list')
        if len(results) + len(chunk) > limit:
            raise IncompleteSnapshot(f'{label} exceeded {limit}; refusing partial analysis')
        results.extend(chunk)
        if len(chunk) < 100:
            return results
    raise IncompleteSnapshot(f'{label} pagination incomplete')


def _sha40(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(
        char in '0123456789abcdefABCDEF' for char in value
    )


def collect(repo: str, token: str = '') -> dict[str, Any]:
    parts = repo.split('/')
    if len(parts) != 2 or not all(
        p and p.replace('-', '').replace('_', '').replace('.', '').isalnum()
        for p in parts
    ):
        raise IncompleteSnapshot('Invalid owner/repository identifier')
    prefix = '/repos/' + '/'.join(urllib.parse.quote(p, safe='') for p in parts)
    metadata = _api_json(prefix, token)
    branch = metadata.get('default_branch') if isinstance(metadata, dict) else None
    if not isinstance(branch, str) or not branch:
        raise IncompleteSnapshot('Default branch not reported')
    ref_path = f"{prefix}/git/ref/heads/{urllib.parse.quote(branch, safe='')}"
    default_ref = _api_json(ref_path, token)
    default_sha = ((default_ref.get('object') or {}).get('sha')
                   if isinstance(default_ref, dict) else None)
    if not _sha40(default_sha):
        raise IncompleteSnapshot('Default branch SHA unavailable')

    raw_prs = _pages(prefix + '/pulls?state=open', token, MAX_PRS, 'open pull requests')
    prs: list[dict[str, Any]] = []
    for p in raw_prs:
        if not isinstance(p, dict) or type(p.get('number')) is not int:
            raise IncompleteSnapshot('Malformed PR list entry')
        n = p['number']
        if n <= 0:
            raise IncompleteSnapshot('PR number must be positive')
        # LIST /pulls does not guarantee changed_files; detail is authoritative
        # for expected count and fork/target repository identities.
        detail = _api_json(f'{prefix}/pulls/{n}', token)
        if not isinstance(detail, dict):
            raise IncompleteSnapshot(f'PR #{n}: invalid detail response')
        for field in ('head', 'base'):
            old, new = p.get(field) or {}, detail.get(field) or {}
            if (old.get('ref'), old.get('sha')) != (new.get('ref'), new.get('sha')):
                raise IncompleteSnapshot(f'PR #{n}: moved before file enumeration')
        head = detail.get('head') or {}
        base = detail.get('base') or {}
        head_repo = (head.get('repo') or {}).get('full_name')
        base_repo = (base.get('repo') or {}).get('full_name')
        if not all(isinstance(value, str) and value
                   for value in (head_repo, base_repo, head.get('ref'), base.get('ref'))):
            raise IncompleteSnapshot(f'PR #{n}: source/target branch origin unavailable')
        if not _sha40(head.get('sha')) or not _sha40(base.get('sha')):
            raise IncompleteSnapshot(f'PR #{n}: exact head/base SHA unavailable')
        changed_files = detail.get('changed_files')
        if (type(changed_files) is not int or changed_files < 0
                or changed_files > MAX_FILES_PER_PR):
            raise IncompleteSnapshot(f'PR #{n}: changed files exceed safe scan limit')
        files = _pages(f'{prefix}/pulls/{n}/files', token, MAX_FILES_PER_PR, f'PR #{n} files')
        paths = []
        renamed_from = []
        for item in files:
            name = item.get('filename') if isinstance(item, dict) else None
            if not isinstance(name, str) or not name:
                raise IncompleteSnapshot(f'PR #{n}: file path missing')
            paths.append(name)
            # A rename must reserve BOTH the old and new path. Otherwise a
            # second PR editing the old name produces a false "no collision".
            if item.get('status') == 'renamed':
                old = item.get('previous_filename')
                if not isinstance(old, str) or not old:
                    raise IncompleteSnapshot(f'PR #{n}: rename source path missing')
                renamed_from.append(old)
        if len(paths) != changed_files or len(set(paths)) != len(paths):
            raise IncompleteSnapshot(f'PR #{n}: file list incomplete/duplicated')
        prs.append({
            'number': n, 'base_ref': base['ref'], 'base_sha': base['sha'],
            'base_repo': base_repo, 'head_ref': head['ref'], 'head_sha': head['sha'],
            'head_repo': head_repo, 'draft': detail.get('draft'),
            'changed_files': changed_files, 'paths': paths,
            'renamed_from_paths': sorted(set(renamed_from)), 
        })

    # Cross-PR reads are not atomic. Catch any changed PR head, base, or fork
    # after enumeration, and never certify a report from a moving snapshot.
    final_prs = _pages(prefix + '/pulls?state=open', token, MAX_PRS,
                       'open pull requests (verification)')
    first_ids = {
        p['number']: (p['head_sha'], p['base_sha'], p['head_ref'], p['base_ref'],
                      p['head_repo'], p['base_repo']) for p in prs
    }
    final_ids = {}
    for p in final_prs:
        if not isinstance(p, dict) or type(p.get('number')) is not int:
            raise IncompleteSnapshot('Malformed final PR listing')
        head, base = p.get('head') or {}, p.get('base') or {}
        final_ids[p['number']] = (
            head.get('sha'), base.get('sha'), head.get('ref'), base.get('ref'),
            (head.get('repo') or {}).get('full_name'),
            (base.get('repo') or {}).get('full_name'),
        )
    if first_ids != final_ids or len(first_ids) != len(prs) or len(final_ids) != len(final_prs):
        raise IncompleteSnapshot('PR head/target changed during scan; not atomic')
    last_ref = _api_json(ref_path, token)
    last_sha = ((last_ref.get('object') or {}).get('sha')
                if isinstance(last_ref, dict) else None)
    if last_sha != default_sha:
        raise IncompleteSnapshot('Default branch moved during scan')
    return {
        'schema': 'hermes.pr.snapshot.v3',
        'repository': repo,
        'collected_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'default_branch': branch,
        'default_head_sha': default_sha,
        'pulls': prs,
        'scope': 'GitHub open PR metadata only; no live worker, CI, browser, or provider telemetry',
    }


def _windows_invalid_path_reason(path: str) -> str | None:
    """Conservative invalid Windows worktree path checks, independent of OS."""
    forbidden = set('<>:"\\|?*')
    for component in path.split('/'):
        if not component or component in {'.', '..'}:
            return 'Empty/current/parent component'
        if component[-1] in {' ', '.'}:
            return 'Trailing period or space'
        if any(c in forbidden or ord(c) < 32 for c in component):
            return 'Reserved character/control character'
        # Win32 device names stay reserved with any extension.
        stem = component.split('.', 1)[0].upper()
        if stem in {'CON', 'PRN', 'AUX', 'NUL'} or (
            len(stem) == 4 and stem[:3] in {'COM', 'LPT'} and
            stem[3] in '123456789\u00b9\u00b2\u00b3'
        ):
            return 'Reserved Windows device name'
    return None


def _windows_identity(path: str) -> str:
    """Conservative casefold/NFC heuristic for NTFS checkout alias hazards.

    Not a proof of Windows path equivalence; Windows volume policies,
    case-sensitive directories and Win32 reserved-name rules vary.
    """
    return unicodedata.normalize('NFC', path).casefold()


def _is_sensitive(path: str) -> bool:
    return path.endswith(('.py', '.js', '.ts', '.tsx', '.mjs', '.toml', '.yaml', '.yml', '.json')) or path.startswith('.github/workflows/')


def analyze(snapshot: dict[str, Any], *, evidence_mode: str = 'unverified_input') -> dict[str, Any]:
    if evidence_mode not in {'github_api', 'offline_snapshot', 'unverified_input'}:
        raise IncompleteSnapshot('Unsupported evidence provenance')
    if not isinstance(snapshot.get('collected_at'), str) or not snapshot['collected_at']:
        raise IncompleteSnapshot('Snapshot collection timestamp unavailable')
    if snapshot.get('schema') != 'hermes.pr.snapshot.v3':
        raise IncompleteSnapshot('Unsupported snapshot schema; v3 required for rename/fork-safe ancestry')
    if not isinstance(snapshot.get('repository'), str) or not snapshot['repository']:
        raise IncompleteSnapshot('Repository identity missing')
    if not isinstance(snapshot.get('default_branch'), str) or not snapshot['default_branch']:
        raise IncompleteSnapshot('Default branch identity missing')
    if not _sha40(snapshot.get('default_head_sha')):
        raise IncompleteSnapshot('Default HEAD SHA missing')
    raw_pulls = snapshot.get('pulls')
    if not isinstance(raw_pulls, list) or len(raw_pulls) > MAX_PRS:
        raise IncompleteSnapshot('Missing or excessive PR inventory')
    pulls: dict[int, dict[str, Any]] = {}
    branches: dict[tuple[str, str], int] = {}
    for p in raw_pulls:
        if not isinstance(p, dict):
            raise IncompleteSnapshot('Malformed PR record')
        n = p.get('number')
        if type(n) is not int or n <= 0 or n in pulls:
            raise IncompleteSnapshot('Missing/repeated PR number')
        for key in ('base_ref', 'head_ref', 'head_repo', 'base_repo'):
            if not isinstance(p.get(key), str) or not p[key]:
                raise IncompleteSnapshot(f'PR #{n}: missing {key}')
        if not _sha40(p.get('base_sha')) or not _sha40(p.get('head_sha')):
            raise IncompleteSnapshot(f'PR #{n}: invalid SHA')
        paths = p.get('paths')
        if (not isinstance(paths, list) or not all(isinstance(x, str) and x for x in paths)
                or len(paths) != len(set(paths)) or type(p.get('changed_files')) is not int
                or len(paths) != p['changed_files']):
            raise IncompleteSnapshot(f'PR #{n}: missing/incomplete paths')
        old_paths = p.get('renamed_from_paths')
        if not isinstance(old_paths, list) or not all(
            isinstance(path, str) and path for path in old_paths
        ) or len(old_paths) != len(set(old_paths)):
            raise IncompleteSnapshot(f'PR #{n}: rename source evidence missing')
        # One renamed source path per changed-file record at most.
        if len(old_paths) > p['changed_files']:
            raise IncompleteSnapshot(f'PR #{n}: invalid rename sources')
        pulls[n] = p
        identity = (p['head_repo'], p['head_ref'])
        if identity in branches:
            branches[identity] = -1
        else:
            branches[identity] = n

    parent: dict[int, int] = {}
    ambiguous_base: list[int] = []
    untracked_base: list[int] = []
    for n, p in pulls.items():
        candidate = branches.get((p['base_repo'], p['base_ref']))
        if candidate == -1:
            ambiguous_base.append(n)
        elif candidate in pulls and candidate != n:
            parent[n] = candidate
        elif (p['base_ref'] != snapshot['default_branch']
              or p['base_repo'] != snapshot['repository']):
            untracked_base.append(n)

    def ancestors(n: int) -> set[int]:
        seen: set[int] = set()
        while n in parent:
            n = parent[n]
            if n in seen:
                raise IncompleteSnapshot('Cyclic PR branch dependency')
            seen.add(n)
        return seen

    for n in pulls:
        ancestors(n)
    findings: list[dict[str, Any]] = []
    provenance = {
        'github_api': 'GitHub REST GET read; cross-PR snapshot non-atomic',
        'offline_snapshot': 'Unverified offline snapshot replay; not current GitHub state',
        'unverified_input': 'Caller-provided metadata; provenance unverified',
    }[evidence_mode]

    def issue(code: str, severity: str, prs: list[int], paths: list[str],
              why: str, next_step: str) -> None:
        findings.append({
            'code': code, 'severity': severity, 'prs': sorted(prs),
            'paths': sorted(paths), 'evidence': provenance,
            'why': why, 'next_step': next_step,
        })

    for n in untracked_base:
        issue('UNTRACKED_STACK_BASE', 'review', [n], [],
              'PR targets a nondefault base not represented by any open PR head.',
              'Inspect branch ownership and pinned snapshot SHA before promotion.')
    for n in ambiguous_base:
        issue('STACK_PARENT_AMBIGUOUS', 'blocker', [n], [],
              'Multiple open PR heads share the same source-repository and branch identity.',
              'Establish one parent and reject ambiguous automatic stacking.')
    for n, p in sorted(pulls.items()):
        if n in parent and p['base_sha'] != pulls[parent[n]]['head_sha']:
            issue('STACK_PARENT_MOVED', 'blocker', [n, parent[n]], [],
                  'Stacked PR target SHA differs from the current parent PR head.',
                  'Update the child, compare combined changes and rerun exact-head CI.')

    # Git/GitHub path names are byte/case-sensitive. Typical Windows
    # checkouts are case-insensitive; two *different* names within one PR can
    # collide on disk. Never infer a successful Windows checkout from Git API.
    for n, p in sorted(pulls.items()):
        groups: dict[str, set[str]] = defaultdict(set)
        for path in p['paths']:
            reason = _windows_invalid_path_reason(path)
            if reason:
                issue('WINDOWS_UNREPRESENTABLE_PATH', 'blocker', [n], [path],
                      f'Potential Windows checkout failure: {reason}.',
                      'Verify path on isolated Windows NTFS checkout; rename or exclude before promotion.')
            groups[_windows_identity(path)].add(path)
        for aliases in groups.values():
            if len(aliases) > 1:
                issue('WINDOWS_PATH_ALIAS_IN_PR', 'blocker', [n], sorted(aliases),
                      'Distinct Git paths normalize to one approximate Windows checkout name.',
                      'Review exact Windows NTFS checkout and rename plan in an isolated worktree.')

    nums = sorted(pulls)
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            a_paths = set(pulls[a]['paths']) | set(pulls[a]['renamed_from_paths'])
            b_paths = set(pulls[b]['paths']) | set(pulls[b]['renamed_from_paths'])
            overlap = sorted(a_paths & b_paths)
            stacked = a in ancestors(b) or b in ancestors(a)
            # Two independent branches can avoid exact-path collisions while
            # still clobbering case-insensitive Windows working directories.
            aliases: dict[str, set[str]] = defaultdict(set)
            a_index: dict[str, set[str]] = defaultdict(set)
            b_index: dict[str, set[str]] = defaultdict(set)
            for path in a_paths:
                a_index[_windows_identity(path)].add(path)
            for path in b_paths:
                b_index[_windows_identity(path)].add(path)
            for norm in a_index.keys() & b_index.keys():
                if a_index[norm] != b_index[norm] or len(a_index[norm]) > 1 or len(b_index[norm]) > 1:
                    aliases[norm].update(a_index[norm] | b_index[norm])
            if aliases:
                issue('WINDOWS_PATH_ALIAS_ACROSS_PRS', 'review' if stacked else 'blocker',
                      [a, b], sorted(set().union(*aliases.values())),
                      'Git path differences may alias on case-insensitive Windows checkouts.',
                      'Test isolated Windows checkout and choose one canonical path casing.')
            if not overlap:
                continue
            if stacked:
                issue('STACKED_FILE_OVERLAP', 'review', [a, b], overlap,
                      'Stacked PRs edit a common file; sequencing alone does not prove safety.',
                      'Review the combined diff at synchronized parent SHA and rerun tests.')
            else:
                severity = 'blocker' if any(_is_sensitive(path) for path in overlap) else 'review'
                issue('INDEPENDENT_WRITE_COLLISION', severity, [a, b], overlap,
                      'Independent PRs edit the same path; merging is not a safe blind operation.',
                      'Assign one integration owner; manually reconcile and test a combined branch.')

    observers: dict[str, set[int]] = defaultdict(set)
    guard_tools: dict[str, set[int]] = defaultdict(set)
    for n, p in pulls.items():
        for path in p['paths']:
            for prefix, key in [
                ('gpt_companion/', 'gpt_companion'),
                ('gpt_bridge/', 'gpt_bridge'),
                ('gpt_extension/', 'gpt_extension'),
                ('hermes_gpt_bridge/', 'hermes_gpt_bridge'),
                ('gateway/gpt_bridge_observer', 'gateway_gpt_bridge_observer'),
                ('gateway/gpt_causal_observer', 'gateway_gpt_causal_observer'),
                ('gateway/gpt_bridge_diagnostics', 'gateway_gpt_bridge_diagnostics'),
            ]:
                if path.startswith(prefix):
                    observers[key].add(n)
            if path.startswith('scripts/') and path.endswith('.py') and (
                'integration_guard' in path or 'coordination_audit' in path
                or 'pr_integration_guard' in path
            ):
                guard_tools[path].add(n)
    if len(observers) >= 2:
        issue('OBSERVER_AUTHORITY_SPLIT', 'review',
              sorted(set().union(*observers.values())), list(observers),
              'Competing observer implementations may claim incompatible event truth.',
              'Compare privacy, crash durability, authentication and event schemas; select one.')
    if len(guard_tools) >= 2:
        issue('DUPLICATE_INTEGRATION_GUARDS', 'review',
              sorted(set().union(*guard_tools.values())), list(guard_tools),
              'Independent integration guards duplicate the coordination control plane.',
              'Select one canonical scanner; migrate verified capabilities without deploying rivals.')

    findings.sort(key=lambda f: ({'blocker': 0, 'review': 1}[f['severity']],
                                 f['code'], f['prs']))
    return {
        'schema': 'hermes.pr.watch.report.v3',
        'repository': snapshot['repository'],
        'collected_at': snapshot.get('collected_at'),
        'default_head_sha': snapshot['default_head_sha'],
        'open_pr_count': len(pulls),
        'counts': {'blocker': sum(f['severity'] == 'blocker' for f in findings),
                   'review': sum(f['severity'] == 'review' for f in findings)},
        'findings': findings,
        'collection_status': 'COMPLETE_METADATA_SNAPSHOT',
        'evidence_mode': evidence_mode,
        'snapshot_currentness': 'RECENT_API_READ_NOT_ATOMIC' if evidence_mode == 'github_api' else 'UNVERIFIED_OFFLINE',
        'provenance': provenance,
        'integration_verdict': 'HOLD_FOR_REVIEW' if any(f['severity'] == 'blocker' for f in findings) else 'REVIEW_ONLY',
        'runtime_verdict': 'UNOBSERVED',
        'ci_verdict': 'UNVERIFIED',
        'confidence': 'GitHub metadata only; no runtime/CI/permission or provider success inferred',
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        '# Hermes GPT PR integration watch',
        f"Open PRs: {report['open_pr_count']}; blockers: {report['counts']['blocker']}; reviews: {report['counts']['review']}.",
        f"**Integration decision: {report['integration_verdict']}** (CI {report['ci_verdict']}; runtime {report['runtime_verdict']}).",
        f"**Evidence source:** {report['provenance']}.",
        f"Base HEAD: `{report['default_head_sha']}`.",
        '**Read-only metadata analysis; not a runtime monitor or test-success assertion.**',
    ]
    for finding in report['findings']:
        safe_paths = [
            str(path).replace('\r', ' ').replace('\n', ' ').replace('`', "'")
            for path in finding['paths'][:5]
        ]
        paths = ', '.join('`' + path + '`' for path in safe_paths) or 'branch dependency'
        lines.append(
            f"- **{finding['severity']} / {finding['code']}** PR "
            + ', '.join('#' + str(n) for n in finding['prs'])
            + f": {paths}. {finding['next_step']}"
        )
    return '\n'.join(lines) + '\n'


def _atomic_write(path: Path, content: bytes) -> None:
    """Atomic per-file replace; do not claim an atomic multi-file transaction.

    Temp is created beside the target and fsynced before os.replace. A machine
    power loss can still affect durability; the bundle digest detects
    incomplete/mixed snapshots on subsequent reads.
    """
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb', prefix=f'.{path.name}.', suffix='.tmp',
            dir=path.parent, delete=False,
        ) as output:
            temporary = output.name
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _write_bundle(
    *,
    snapshot_path: Path | None,
    report_path: Path | None,
    markdown_path: Path | None,
    manifest_path: Path | None,
    snapshot: dict[str, Any],
    report: dict[str, Any],
    summary: str,
) -> None:
    files: list[tuple[str, Path, bytes]] = []
    for label, path, data in (
        ('snapshot', snapshot_path, json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n'),
        ('report', report_path, json.dumps(report, indent=2, ensure_ascii=False) + '\n'),
        ('markdown', markdown_path, summary),
    ):
        if path is not None:
            files.append((label, path, data.encode('utf-8')))
    destinations = [p.resolve() for _, p, _ in files]
    if manifest_path is not None:
        if not files:
            raise IncompleteSnapshot('Cannot certify a bundle with no output files')
        destinations.append(manifest_path.resolve())
    if len(set(destinations)) != len(destinations):
        raise IncompleteSnapshot('Report output paths overlap; refusing to overwrite evidence')

    for _, path, data in files:
        _atomic_write(path, data)
    if manifest_path is not None:
        # Digest manifest is written LAST. It certifies only file consistency
        # at collection time, NOT GitHub atomicity, runtime health or merge.
        manifest = {
            'schema': 'hermes.pr.bundle.v1',
            'status': 'FILES_WRITTEN_NOT_RUNTIME_VERIFIED',
            'snapshot_sha': snapshot['default_head_sha'],
            'evidence_mode': report['evidence_mode'],
            'collected_at': snapshot['collected_at'],
            'files': {
                name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                for name, _, data in files
            },
        }
        manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8')
        _atomic_write(manifest_path, manifest_raw)
        # Catch mixed generations from concurrent writers or corrupt
        # files before the CLI reports success. Readers must verify too.
        verify_bundle(
            manifest_path,
            snapshot_path=snapshot_path,
            report_path=report_path,
            markdown_path=markdown_path,
        )


def verify_bundle(
    manifest_path: Path, *,
    snapshot_path: Path | None,
    report_path: Path | None,
    markdown_path: Path | None,
) -> dict[str, Any]:
    """Offline receipt validation. Hash consistency is not source authentication."""
    if manifest_path.stat().st_size > 16 * 1024:
        raise IncompleteSnapshot('Report manifest too large')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (not isinstance(manifest, dict)
            or manifest.get('schema') != 'hermes.pr.bundle.v1'
            or manifest.get('status') != 'FILES_WRITTEN_NOT_RUNTIME_VERIFIED'
            or not _sha40(manifest.get('snapshot_sha'))
            or not isinstance(manifest.get('evidence_mode'), str)
            or manifest['evidence_mode'] not in
            {'github_api', 'offline_snapshot', 'unverified_input'}):
        raise IncompleteSnapshot('Unsupported or incomplete report manifest')
    paths = {
        role: path for role, path in (
            ('snapshot', snapshot_path),
            ('report', report_path),
            ('markdown', markdown_path),
        ) if path is not None
    }
    if (not paths or not isinstance(manifest.get('files'), dict)
            or set(paths) != set(manifest['files'])):
        raise IncompleteSnapshot('Bundle roles do not match manifest')
    if len({p.resolve() for p in [manifest_path, *paths.values()]}) != len(paths) + 1:
        raise IncompleteSnapshot('Bundle paths overlap')
    observed: dict[str, bytes] = {}
    for role, path in paths.items():
        expected = manifest['files'][role]
        if (not isinstance(expected, dict)
                or type(expected.get('bytes')) is not int
                or not 0 <= expected['bytes'] <= 60 * 1024 * 1024
                or not isinstance(expected.get('sha256'), str)
                or len(expected['sha256']) != 64
                or any(c not in '0123456789abcdef' for c in expected['sha256'])):
            raise IncompleteSnapshot('Invalid bundle file digest or size')
        if path.stat().st_size != expected['bytes']:
            raise IncompleteSnapshot('Bundle byte count mismatch')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise IncompleteSnapshot('Bundle digest mismatch')
        observed[role] = data
    if 'report' in observed:
        report = json.loads(observed['report'].decode('utf-8'))
        if (not isinstance(report, dict)
                or report.get('default_head_sha') != manifest['snapshot_sha']
                or report.get('evidence_mode') != manifest['evidence_mode']
                or report.get('collected_at') != manifest.get('collected_at')
                or report.get('runtime_verdict') != 'UNOBSERVED'):
            raise IncompleteSnapshot('Report provenance mismatch')
    if 'snapshot' in observed:
        snapshot = json.loads(observed['snapshot'].decode('utf-8'))
        if (not isinstance(snapshot, dict)
                or snapshot.get('default_head_sha') != manifest['snapshot_sha']
                or snapshot.get('collected_at') != manifest.get('collected_at')):
            raise IncompleteSnapshot('Snapshot provenance mismatch')
        pulls = snapshot.get('pulls')
        if not isinstance(pulls, list):
            raise IncompleteSnapshot('Bundle snapshot PR inventory malformed')
        if 'report' in observed and report.get('open_pr_count') != len(pulls):
            raise IncompleteSnapshot('Report/snapshot PR counts disagree')
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', ''))
    ap.add_argument('--snapshot-in', type=Path, help='Offline JSON input, no network')
    ap.add_argument('--snapshot-out', type=Path)
    ap.add_argument('--report-out', type=Path)
    ap.add_argument('--markdown-out', type=Path)
    ap.add_argument('--manifest-out', type=Path, help='Written last; per-file SHA-256 receipt')
    ap.add_argument('--verify-manifest', type=Path, help='Verify prior bundle offline without GitHub access')
    ap.add_argument('--strict', action='store_true', help='Exit 2 on blockers')
    args = ap.parse_args(argv)
    try:
        if args.verify_manifest:
            if args.manifest_out or args.snapshot_in:
                raise IncompleteSnapshot('Verification cannot simultaneously collect or generate')
            manifest = verify_bundle(
                args.verify_manifest,
                snapshot_path=args.snapshot_out,
                report_path=args.report_out,
                markdown_path=args.markdown_out,
            )
            print('BUNDLE_HASH_VALID; source=' + str(manifest['evidence_mode'])
                  + '; runtime=UNOBSERVED; no source authenticity/freshness claimed')
            return 0
        snapshot = (
            json.loads(args.snapshot_in.read_text(encoding='utf-8'))
            if args.snapshot_in else collect(args.repo, os.environ.get('GITHUB_TOKEN', ''))
        )
        report = analyze(snapshot, evidence_mode=('offline_snapshot' if args.snapshot_in else 'github_api'))
        summary = markdown(report)
        _write_bundle(
            snapshot_path=args.snapshot_out,
            report_path=args.report_out,
            markdown_path=args.markdown_out,
            manifest_path=args.manifest_out,
            snapshot=snapshot, report=report, summary=summary,
        )
        print(summary)
        return 2 if args.strict and report['counts']['blocker'] else 0
    except (IncompleteSnapshot, OSError, ValueError) as exc:
        print(f'INCOMPLETE: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
