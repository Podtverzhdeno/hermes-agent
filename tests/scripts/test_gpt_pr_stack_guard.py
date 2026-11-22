"""Standalone offline proof checks for cross-base PR graph; no GitHub mutation."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

SOURCE=Path(__file__).resolve().parents[2]/'scripts'/'gpt_pr_stack_guard.py'
spec=importlib.util.spec_from_file_location('gpt_pr_stack_guard',SOURCE)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def pr(i,base='main',files=None,head=None,proof=None):
    z={'number':i,'head_ref':head or f'b{i}','head_repo':'owner/repo','head_sha':f'{i:040x}',
       'base_ref':base,'files':files if files is not None else [f'docs/{i}.md']}
    if proof is not None:z['parent_compare']=proof
    return z


def snap(*ps):return {'schema_version':1,'repo':'owner/repo','pulls':list(ps)}


def proof(parent,behind=0,status=None,ahead=None):
    status = status or ('diverged' if behind else 'ahead')
    ahead = (0 if status in ('behind','identical') else 1) if ahead is None else ahead
    return {'parent_sha':f'{parent:040x}','behind_by':behind,'ahead_by':ahead,'status':status}


def test_no_stack_cannot_mean_merge_approved():
    r=mod.analyze(snap(pr(1),pr(2)))
    assert r['verdict']=='NO_STACK_ISSUES_NOT_MERGE_APPROVAL'
    assert 'CI status' in r['not_checked']


def test_parent_advanced_requires_rebase():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(1,behind=2))))
    assert any(e['code']=='PARENT_ADVANCED_REBASE_REQUIRED' for e in r['issues'])


def test_stacked_without_compare_is_unverified():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent')))
    assert r['issues'][0]['code']=='PARENT_ANCESTRY_UNVERIFIED'


def test_stacked_same_file_needs_review_even_with_ancestry():
    r=mod.analyze(snap(pr(1,head='parent',files=['gateway/platforms/api_server.py']),
                           pr(2,base='parent',files=['gateway/platforms/api_server.py'],proof=proof(1))))
    assert r['issues'][0]['code']=='STACKED_FILE_OVERLAP_REVIEW'


def test_unknown_base_never_green():
    assert mod.analyze(snap(pr(1,base='unknown')))['issues'][0]['code']=='PARENT_NOT_IN_SNAPSHOT'


def test_valid_stacked_no_overlap_yet_no_merging_attestation():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(1))))
    assert r['issues']==[] and r['stacks_checked']==1
    assert r['verdict']=='NO_STACK_ISSUES_NOT_MERGE_APPROVAL'


@pytest.mark.parametrize('bad',[snap(pr(1),pr(1)),snap(pr(1,files=['../secret'])),
  snap(pr(1,head='x'),pr(2,head='x')),
  snap(pr(1))|{'pulls':[pr(1)|{'head_sha':'bad'}]},
  snap(pr(1))|{'pulls':[pr(1)|{'files':'not-a-list'}]}])
def test_invalid_inventory_fails_closed(bad):
    with pytest.raises(mod.IncompleteAudit):mod.analyze(bad)


def test_inconsistent_compare_evidence_downgrade():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(99))))
    assert r['issues'][0]['code']=='PARENT_ANCESTRY_UNVERIFIED'


def test_pagination_limit_blocks_unknown_tail():
    with patch.object(mod,'get',return_value=[{}]*100):
        with pytest.raises(mod.IncompleteAudit):mod.pages('/repos/a/b/pulls',cap=1)


def test_no_auth_redirect():
    assert mod.NoRedirect().redirect_request(None,None,302,'Found',{},'https://x.test') is None


def test_cli_exit_code_1_on_stale_parent(tmp_path):
    x=tmp_path/'snapshot.json';x.write_text(json.dumps(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(1,3)))))
    p=subprocess.run([sys.executable,str(SOURCE),'--snapshot',str(x)],capture_output=True,text=True)
    assert p.returncode==1
    assert json.loads(p.stdout)['issues'][0]['code']=='PARENT_ADVANCED_REBASE_REQUIRED'


def test_cli_exit_code_2_on_corrupt_data(tmp_path):
    x=tmp_path/'snapshot.json';x.write_text('oops')
    p=subprocess.run([sys.executable,str(SOURCE),'--snapshot',str(x)],capture_output=True,text=True)
    assert p.returncode==2 and 'AUDIT_INCOMPLETE' in p.stderr


def test_collect_verifies_heads_before_and_after_files():
    initial={'number':2,'head':{'ref':'b2','sha':f'{2:040x}','repo':{'full_name':'owner/repo'}},'base':{'ref':'main'}}
    def fetch(path,token):
        if path.endswith('/pulls/2'):return initial
        if '/compare/' in path:return {'behind_by':0,'ahead_by':1,'status':'ahead'}
        raise AssertionError(path)
    def fetch_pages(path,token,cap=10):
        if 'state=open' in path:return [initial]
        if '/files' in path:return [{'filename':'docs/2.md'}]
        raise AssertionError(path)
    with patch.object(mod,'get',side_effect=fetch),patch.object(mod,'pages',side_effect=fetch_pages):
        data=mod.collect('owner/repo')
    assert data['pulls'][0]['head_sha']==f'{2:040x}'


def test_online_only_api_get_has_no_mutating_calls():
    with patch.object(mod,'pages',return_value=[]),patch.object(mod,'get') as get:
        data=mod.collect('owner/repo')
    assert data['pulls']==[] and get.call_count==0


def test_dependency_cycle_cannot_appear_green():
    # Both branches may temporarily point to one revision; ancestry alone is insufficient.
    a=pr(1,base='b2',head='b1',proof=proof(2))
    b=pr(2,base='b1',head='b2',proof=proof(1))
    with pytest.raises(mod.IncompleteAudit,match='cyclic'):
        mod.analyze(snap(a,b))


def test_collect_rejects_invalid_pr_shape():
    with patch.object(mod,'pages',return_value=[{'number':1,'head':None}]):
        with pytest.raises(mod.IncompleteAudit,match='shape'):
            mod.collect('owner/repo')


def test_invalid_compare_shape_fails_closed():
    a=pr(1,head='parent');b=pr(2,base='parent')
    raw={
        'number':1,'head':{'ref':'parent','sha':a['head_sha'],'repo':{'full_name':'owner/repo'}},
        'base':{'ref':'main'}
    }
    child={
        'number':2,'head':{'ref':'b2','sha':b['head_sha'],'repo':{'full_name':'owner/repo'}},
        'base':{'ref':'parent'}
    }
    def fetch(path,token):
        if '/compare/' in path:return []
        if path.endswith('/pulls/1'):return raw
        if path.endswith('/pulls/2'):return child
        raise AssertionError(path)
    def pages(path,token,cap=10):
        if 'state=open' in path:return [raw,child]
        if '/files' in path:return [{'filename':'docs/a.md'}]
        raise AssertionError(path)
    with patch.object(mod,'get',side_effect=fetch),patch.object(mod,'pages',side_effect=pages):
        with pytest.raises(mod.IncompleteAudit,match='compare'):
            mod.collect('owner/repo')


def test_contradictory_diverged_without_behind_never_green():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(1,status='diverged',behind=0,ahead=1))))
    assert r['issues'][0]['code']=='INVALID_COMPARE_EVIDENCE'


def test_missing_ahead_field_never_green():
    x=proof(1)
    x.pop('ahead_by')
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=x)))
    assert r['issues'][0]['code']=='INVALID_COMPARE_EVIDENCE'


def test_identical_compare_must_have_zero_bidirectional_counts():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(1,status='identical',ahead=2))))
    assert r['issues'][0]['code']=='INVALID_COMPARE_EVIDENCE'


def test_genuine_identical_parent_head_is_an_ancestry_success_only():
    r=mod.analyze(snap(pr(1,head='parent'),pr(2,base='parent',proof=proof(1,status='identical',behind=0,ahead=0))))
    assert r['issues']==[] and r['verdict']=='NO_STACK_ISSUES_NOT_MERGE_APPROVAL'
