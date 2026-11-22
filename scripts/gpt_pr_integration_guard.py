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


def collect(repo: str, token: str = '') -> dict[str, Any]:
    parts = repo.split('/')
    if len(parts) != 2 or not all(
        p and p.replace('-', '').replace('_', '').replace('.', '').isalnum() for p in parts
    ):
        raise IncompleteSnapshot('Invalid owner/repository identifier')
    prefix = '/repos/' + '/'.join(urllib.parse.quote(p, safe='') for p in parts)
    metadata = _api_json(prefix, token)
    branch = metadata.get('default_branch') if isinstance(metadata, dict) else None
    if not isinstance(branch, str) or not branch:
        raise IncompleteSnapshot('No default branch reported')
    default_ref = _api_json(
        f"{prefix}/git/ref/heads/{urllib.parse.quote(branch, safe='')}", token
    )
    default_sha = (default_ref.get('object') or {}).get('sha') if isinstance(default_ref, dict) else None
    if not isinstance(default_sha, str) or len(default_sha) != 40:
        raise IncompleteSnapshot('Default branch SHA unavailable')
    raw_prs = _pages(prefix + '/pulls?state=open', token, MAX_PRS, 'open pull requests')
    prs = []
    for p in raw_prs:
        number = p.get('number')
        if type(number) is not int or number <= 0:
            raise IncompleteSnapshot('PR without valid number')
        files = _pages(f'{prefix}/pulls/{number}/files', token, MAX_FILES_PER_PR, f'PR #{number} files')
        paths = []
        for f in files:
            name = f.get('filename') if isinstance(f, dict) else None
            if not isinstance(name, str) or not name:
                raise IncompleteSnapshot(f'PR #{number} file path unavailable')
            paths.append(name)
        prs.append({
            'number': number,
            'base_ref': (p.get('base') or {}).get('ref'),
            'base_sha': (p.get('base') or {}).get('sha'),
            'head_ref': (p.get('head') or {}).get('ref'),
            'head_sha': (p.get('head') or {}).get('sha'),
            'draft': p.get('draft'),
            'paths': paths,
        })
    # A GitHub PR listing is not transactional. Refuse if any head/base moved.
    final_prs = _pages(prefix + '/pulls?state=open', token, MAX_PRS, 'open pull requests (verification)')
    first_ids = {p['number']: (p['head_sha'], p['base_sha'], p['head_ref'], p['base_ref']) for p in prs}
    final_ids = {
        p['number']: (
            (p.get('head') or {}).get('sha'), (p.get('base') or {}).get('sha'),
            (p.get('head') or {}).get('ref'), (p.get('base') or {}).get('ref')
        ) for p in final_prs
    }
    if first_ids != final_ids or len(first_ids) != len(prs) or len(final_ids) != len(final_prs):
        raise IncompleteSnapshot('PR heads/target changed during scan; retry later; not atomic')
    return {
        'schema': 'hermes.pr.snapshot.v1',
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
    if snapshot.get('schema') != 'hermes.pr.snapshot.v1' or not isinstance(snapshot.get('pulls'), list):
        raise IncompleteSnapshot('Unsupported or incomplete snapshot schema')
    pulls: dict[int, dict[str, Any]] = {}
    branches: dict[str, int] = {}
    for p in snapshot['pulls']:
        if not isinstance(p, dict):
            raise IncompleteSnapshot('Malformed PR record')
        n = p.get('number')
        if type(n) is not int or n <= 0 or n in pulls:
            raise IncompleteSnapshot('Missing or repeated PR number')
        if not isinstance(p.get('paths'), list) or not all(
            isinstance(path, str) and path for path in p['paths']
        ):
            raise IncompleteSnapshot(f'PR #{n}: missing paths; never assume no changes')
        for key in ('base_ref', 'head_ref', 'base_sha', 'head_sha'):
            if not isinstance(p.get(key), str) or not p[key]:
                raise IncompleteSnapshot(f'PR #{n}: missing {key}')
        pulls[n] = p
        if p['head_ref'] in branches:
            branches[p['head_ref']] = -1  # Same name across forks: ambiguous.
        else:
            branches[p['head_ref']] = n
    parent: dict[int, int] = {}
    ambiguous_base: list[int] = []
    for n, p in pulls.items():
        candidate = branches.get(p['base_ref'])
        if candidate == -1:
            ambiguous_base.append(n)
        elif candidate in pulls and candidate != n:
            parent[n] = candidate

    def ancestors(n: int) -> set[int]:
        seen: set[int] = set()
        while n in parent:
            n = parent[n]
            if n in seen:
                raise IncompleteSnapshot('Cyclic PR branch dependency')
            seen.add(n)
        return seen

    for number in pulls:
        ancestors(number)

    findings = []

    def issue(code: str, severity: str, prs: list[int], paths: list[str], why: str, next_step: str):
        findings.append({
            'code': code, 'severity': severity, 'prs': sorted(prs),
            'paths': sorted(paths), 'evidence': 'GitHub PR metadata',
            'why': why, 'next_step': next_step,
        })

    for n in ambiguous_base:
        issue('STACK_PARENT_AMBIGUOUS', 'blocker', [n], [],
              'Multiple PR heads use this base branch name; ancestry is ambiguous.',
              'Check head repository identity; do not assume an independent PR.')
    for n, p in sorted(pulls.items()):
        if n in parent and p['base_sha'] != pulls[parent[n]]['head_sha']:
            issue('STACK_PARENT_MOVED', 'blocker', [n, parent[n]], [],
                  'Child base SHA differs from current parent head; tests may be stale.',
                  'Refresh child from current parent and rerun exact-head tests.')

    nums = sorted(pulls)
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            overlap = sorted(set(pulls[a]['paths']) & set(pulls[b]['paths']))
            if not overlap:
                continue
            stacked = a in ancestors(b) or b in ancestors(a)
            significant = any(_is_sensitive(p) for p in overlap)
            if stacked:
                issue('STACKED_FILE_OVERLAP', 'review', [a, b], overlap,
                      'Both stacked changes edit the same file; sequence does not prove compatibility.',
                      'Review combined diff and tests after parent SHA synchronization.')
            else:
                issue('INDEPENDENT_WRITE_COLLISION', 'blocker' if significant else 'review',
                      [a, b], overlap,
                      'Independent PRs edit the same path; blind merge can overwrite semantics.',
                      'Assign a single integrator and build a tested combined branch; no auto-merge.')

    observer_impls: dict[str, set[int]] = defaultdict(set)
    for n, p in pulls.items():
        for path in p['paths']:
            if path.startswith('gpt_companion/'):
                observer_impls['gpt_companion'].add(n)
            elif path.startswith('gpt_bridge/'):
                observer_impls['gpt_bridge'].add(n)
            elif path.startswith('hermes_gpt_bridge/'):
                observer_impls['hermes_gpt_bridge'].add(n)
            elif path == 'gateway/gpt_bridge_diagnostics.py':
                observer_impls['gateway_diagnostics'].add(n)
    if len(observer_impls) >= 2:
        issue('OBSERVER_AUTHORITY_SPLIT', 'review',
              sorted(set().union(*observer_impls.values())), list(observer_impls),
              'Observer packages overlap conceptually despite disjoint paths.',
              'Select one read-only event contract before integration.')

    if not isinstance(snapshot.get('default_head_sha'), str) or not snapshot.get('default_head_sha'):
        raise IncompleteSnapshot('Missing default HEAD SHA')
    findings.sort(key=lambda i: ({'blocker': 0, 'review': 1}[i['severity']], i['code'], i['prs']))
    return {
        'schema': 'hermes.pr.watch.report.v1',
        'repository': snapshot.get('repository'),
        'collected_at': snapshot.get('collected_at'),
        'default_head_sha': snapshot['default_head_sha'],
        'open_pr_count': len(pulls),
        'counts': {
            'blocker': sum(i['severity'] == 'blocker' for i in findings),
            'review': sum(i['severity'] == 'review' for i in findings),
        },
        'findings': findings,
        'confidence': 'Metadata-backed integration risks, not runtime, CI, stop or provider results',
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        '# Hermes GPT PR integration watch',
        f"Open PRs: {report['open_pr_count']}; blockers: {report['counts']['blocker']}; reviews: {report['counts']['review']}.",
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
