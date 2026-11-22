#!/usr/bin/env python3
"""Read-only cross-base GPT stacked-PR ancestry and revision evidence guard.

Complements, does not replace, scripts/hermes_gpt_coordination_audit.py in PR #14.
Exit 0 = no identified stack problems, NOT merge approval; 1 = review required;
2 = incomplete/untrusted data. No actions other than GitHub GET and JSON output.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")


class IncompleteAudit(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get(path, token=None):
    if not path.startswith('/repos/') or '//' in path or '\\' in path or '#' in path:
        raise IncompleteAudit('unsafe API path')
    req = urllib.request.Request('https://api.github.com'+path,
        headers={'Accept':'application/vnd.github+json','User-Agent':'hermes-gpt-stack-guard/1',
                 **({'Authorization':'Bearer '+token} if token else {})})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        raise IncompleteAudit('GitHub request unavailable or invalid JSON') from None


def pages(path, token=None, cap=10):
    parts = []
    for page in range(1,cap+1):
        rows = get(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}',token)
        if not isinstance(rows,list):
            raise IncompleteAudit('GitHub collection not a list')
        parts.extend(rows)
        if len(rows)<100:
            return parts
    raise IncompleteAudit('paginated GitHub result truncated')


def collect(repo, token=None):
    if not REPO.fullmatch(repo) or '..' in repo:
        raise IncompleteAudit('invalid repository')
    prefix=f'/repos/{repo}'
    data=pages(prefix+'/pulls?state=open',token)
    items=[]
    for row in data:
        number=row.get('number')
        if type(number) is not int or number<1:
            raise IncompleteAudit('invalid PR number')
        detail=get(prefix+f'/pulls/{number}',token)
        if detail.get('head',{}).get('sha')!=row.get('head',{}).get('sha'):
            raise IncompleteAudit('PR changed during inventory')
        paths=pages(prefix+f'/pulls/{number}/files',token,cap=30)
        newest=get(prefix+f'/pulls/{number}',token)
        if newest.get('head',{}).get('sha')!=row.get('head',{}).get('sha') or newest.get('base',{}).get('ref')!=row.get('base',{}).get('ref'):
            raise IncompleteAudit('PR changed during file fetch')
        items.append({'number':number,'head_ref':row['head']['ref'],
            'head_repo':(row['head'].get('repo') or {}).get('full_name'),
            'head_sha':row['head']['sha'],'base_ref':row['base']['ref'],
            'files':[f.get('filename') for f in paths]})
    owner={p['head_ref']:p for p in items if p['head_repo']==repo}
    if len(owner)!=len([p for p in items if p['head_repo']==repo]):
        raise IncompleteAudit('ambiguous same-repository parent branch')
    for p in items:
        parent=owner.get(p['base_ref'])
        if parent is None:
            continue
        ancestry=get(prefix+f"/compare/{parent['head_sha']}...{p['head_sha']}",token)
        p['parent_compare']={'parent_sha':parent['head_sha'],
            'behind_by':ancestry.get('behind_by'), 'status':ancestry.get('status')}
    return {'schema_version':1,'repo':repo,
        'collected_at':datetime.now(timezone.utc).isoformat(), 'pulls':items}


def analyze(snapshot):
    if not isinstance(snapshot,dict) or snapshot.get('schema_version')!=1 or not REPO.fullmatch(str(snapshot.get('repo',''))):
        raise IncompleteAudit('invalid snapshot identity')
    rows=snapshot.get('pulls')
    if not isinstance(rows,list) or len(rows)>5000:
        raise IncompleteAudit('invalid PR inventory')
    clean=[]
    numbers=set()
    heads={}
    for p in rows:
        if not isinstance(p,dict):
            raise IncompleteAudit('invalid PR entry')
        n=p.get('number'); sha=p.get('head_sha'); base=p.get('base_ref'); head=p.get('head_ref')
        f=p.get('files'); hrepo=p.get('head_repo')
        if (type(n) is not int or n<1 or n in numbers or not SHA.fullmatch(str(sha))
            or not isinstance(base,str) or not base or not isinstance(head,str) or not head
            or not isinstance(hrepo,str) or not REPO.fullmatch(hrepo)
            or not isinstance(f,list) or len(f)>3000
            or any(not isinstance(x,str) or not x or x.startswith('/') or '\\' in x or '..' in x.split('/') for x in f)):
            raise IncompleteAudit('missing or unsafe PR metadata')
        numbers.add(n)
        clean.append(p)
        if hrepo == snapshot['repo']:
            if head in heads:
                raise IncompleteAudit('ambiguous same-repository parent branch')
            heads[head]=p
    problems=[]
    for p in sorted(clean,key=lambda r:r['number']):
        parent=heads.get(p['base_ref'])
        if parent is None:
            if p['base_ref'] not in ('main','master'):
                problems.append({'pr':p['number'],'code':'PARENT_NOT_IN_SNAPSHOT','base_ref':p['base_ref']})
            continue
        if parent['number']==p['number']:
            raise IncompleteAudit('PR refers to itself as base')
        proof=p.get('parent_compare')
        if not isinstance(proof,dict) or proof.get('parent_sha')!=parent['head_sha']:
            code='PARENT_ANCESTRY_UNVERIFIED'
        elif type(proof.get('behind_by')) is not int or proof['behind_by']<0 or proof.get('status') not in ('ahead','behind','diverged','identical'):
            code='INVALID_COMPARE_EVIDENCE'
        elif proof['behind_by']>0:
            code='PARENT_ADVANCED_REBASE_REQUIRED'
        else:
            code=None
        shared=sorted(set(parent['files'])&set(p['files']))
        if code:
            problems.append({'pr':p['number'],'parent_pr':parent['number'],'code':code})
        if shared:
            problems.append({'pr':p['number'],'parent_pr':parent['number'],
                'code':'STACKED_FILE_OVERLAP_REVIEW','paths':shared})
    return {'schema_version':1,'repo':snapshot['repo'],
        'stacks_checked':sum(p['base_ref'] in heads for p in clean),
        'issues':problems,
        'verdict':'REVIEW_REQUIRED' if problems else 'NO_STACK_ISSUES_NOT_MERGE_APPROVAL',
        'not_checked':['CI status','cross-root semantic conflicts','external side effects','deployed runtime','general non-stacked collisions']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    exclusive=parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument('--snapshot',type=Path)
    exclusive.add_argument('--repo')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    try:
        source=json.loads(args.snapshot.read_text(encoding='utf-8')) if args.snapshot else collect(args.repo,os.getenv('GITHUB_TOKEN'))
        report=analyze(source)
        body=json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+'\n'
        if args.output:
            with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=args.output.parent,delete=False,prefix='.gpt-stack-') as f:
                filename=f.name
                f.write(body);f.flush();os.fsync(f.fileno())
            try: os.replace(filename,args.output)
            finally:
                if os.path.exists(filename): os.unlink(filename)
        else:
            print(body,end='')
        return 1 if report['issues'] else 0
    except (IncompleteAudit,OSError,ValueError,TypeError) as exc:
        print('AUDIT_INCOMPLETE: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
