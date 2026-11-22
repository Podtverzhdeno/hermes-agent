#!/usr/bin/env python3
"""Read-only GPT/Hermes PR integration watch. No credentials or task payloads logged."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
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
        with urllib.request.urlopen(request, timeout=20) as response:
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


def _is_sensitive(path: str) -> bool:
    return path.endswith(('.py', '.js', '.ts', '.tsx', '.mjs', '.toml', '.yaml', '.yml', '.json')) or path.startswith('.github/workflows/')


def analyze(snapshot: dict[str, Any]) -> dict[str, Any]:
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

    def issue(code: str, severity: str, prs: list[int], paths: list[str],
              why: str, next_step: str) -> None:
        findings.append({
            'code': code, 'severity': severity, 'prs': sorted(prs),
            'paths': sorted(paths), 'evidence': 'GitHub PR metadata',
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

    nums = sorted(pulls)
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            a_paths = set(pulls[a]['paths']) | set(pulls[a]['renamed_from_paths'])
            b_paths = set(pulls[b]['paths']) | set(pulls[b]['renamed_from_paths'])
            overlap = sorted(a_paths & b_paths)
            if not overlap:
                continue
            stacked = a in ancestors(b) or b in ancestors(a)
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
        'integration_verdict': 'HOLD_FOR_REVIEW' if any(f['severity'] == 'blocker' for f in findings) else 'REVIEW_ONLY',
        'runtime_verdict': 'UNOBSERVED',
        'ci_verdict': 'UNVERIFIED',
        'confidence': 'GitHub metadata only; no runtime/CI/permission or provider success inferred',
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        '# Hermes GPT PR integration watch',
        f"Open PRs: {report['open_pr_count']}; blockers: {report['counts']['blocker']}; reviews: {report['counts']['review']}.",
        f"**Integration decision: {report['integration_verdict']}** (GitHub metadata only; CI {report['ci_verdict']}; runtime {report['runtime_verdict']}).",
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', ''))
    ap.add_argument('--snapshot-in', type=Path, help='Offline JSON input, no network')
    ap.add_argument('--snapshot-out', type=Path)
    ap.add_argument('--report-out', type=Path)
    ap.add_argument('--markdown-out', type=Path)
    ap.add_argument('--strict', action='store_true', help='Exit 2 on blockers')
    args = ap.parse_args(argv)
    try:
        snapshot = (
            json.loads(args.snapshot_in.read_text(encoding='utf-8'))
            if args.snapshot_in else collect(args.repo, os.environ.get('GITHUB_TOKEN', ''))
        )
        report = analyze(snapshot)
        if args.snapshot_out:
            args.snapshot_out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if args.report_out:
            args.report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        summary = markdown(report)
        if args.markdown_out:
            args.markdown_out.write_text(summary, encoding='utf-8')
        print(summary)
        return 2 if args.strict and report['counts']['blocker'] else 0
    except (IncompleteSnapshot, OSError, ValueError) as exc:
        print(f'INCOMPLETE: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
