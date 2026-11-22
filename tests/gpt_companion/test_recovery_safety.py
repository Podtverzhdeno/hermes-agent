"""Regression tests for cross-attempt effects, event limits, and multiactor ambiguity."""

import pytest

from gpt_companion import EventJournal
from gpt_companion.watch import StatusWatch, _fingerprint


def make_event(idx, kind, *, attempt=1, source='worker-a', action=None):
    ev = {'schema_version': 1, 'event_id': f'event-{attempt}-{source}-{idx}',
          'source': source, 'run_id': 'run-1', 'attempt': attempt,
          'sequence': idx, 'kind': kind}
    if action is not None:
        ev['action_id'] = action
    return ev


def test_earlier_unknown_effect_blocks_unrelated_new_attempt(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', action='pr-1'))
    journal.ingest(make_event(1, 'worker.started', attempt=2))
    result = journal.assess('run-1', now=1001)
    assert result['attempt'] == 2
    assert result['state'] == 'NEEDS_RECONCILIATION'
    assert result['next_action'] == 'RECONCILE_PRIOR_ATTEMPT_EFFECT'
    assert result['historical_unresolved_effects'] == ['1:pr-1']
    assert result['event_position'] == 2


def test_resolved_prior_effect_clears_historical_warning(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', action='pr-1'))
    journal.ingest(make_event(2, 'tool.effect_acknowledged', action='pr-1'))
    journal.ingest(make_event(1, 'worker.started', attempt=2))
    state = journal.assess('run-1', now=1001)
    assert state['historical_unresolved_effects'] == []
    assert state['state'] == 'RECENT_TELEMETRY'


def test_cross_emitter_resolution_cannot_clear_effect(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', action='write'))
    journal.ingest(make_event(2, 'tool.effect_acknowledged', source='worker-b', action='write'))
    result = journal.assess('run-1', now=1001)
    assert result['state'] == 'EFFECT_IN_FLIGHT'
    assert result['unresolved_effects'] == ['write']


def test_cross_emitter_prior_resolution_does_not_clear_old_effect(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', action='write'))
    journal.ingest(make_event(2, 'tool.effect_not_executed', source='worker-b', action='write'))
    journal.ingest(make_event(1, 'worker.started', attempt=2))
    result = journal.assess('run-1', now=1001)
    assert result['state'] == 'NEEDS_RECONCILIATION'
    assert result['historical_unresolved_effects'] == ['1:write']


def test_delayed_old_attempt_effect_updates_run_position_and_watch_status(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'worker.started', attempt=2))
    watcher = StatusWatch(journal.path, tmp_path / 'status.db', clock=lambda: 1001.)
    assert watcher.sample('run-1')['diagnosis']['state'] == 'RECENT_TELEMETRY'
    journal.ingest(make_event(2, 'tool.effect_reserved', attempt=1, action='old-pr'))
    result = watcher.sample('run-1')
    assert result['diagnosis']['event_position'] == 2
    assert result['diagnosis']['state'] == 'NEEDS_RECONCILIATION'
    assert result['diagnosis']['historical_unresolved_effects'] == ['1:old-pr']


def test_partial_worker_stop_does_not_stop_whole_run(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'worker.started', source='worker-a'))
    journal.ingest(make_event(1, 'worker.started', source='worker-b'))
    journal.ingest(make_event(2, 'worker.stopped', source='worker-a'))
    result = journal.assess('run-1', now=1001)
    assert result['state'] == 'PARTIAL_WORKER_OUTAGE'


def test_assessment_explicitly_rejects_truncated_event_windows(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'worker.started'))
    journal.ingest(make_event(2, 'worker.heartbeat'))
    diagnosis = journal.assess('run-1', max_events=1)
    assert diagnosis['state'] == 'TRACE_WINDOW_LIMIT_EXCEEDED'
    assert 'HALT' in diagnosis['next_action']
    with pytest.raises(ValueError):
        journal.assess('run-1', max_events=0)
    with pytest.raises(ValueError):
        journal.assess('run-1', max_events=True)


def test_historical_event_window_limit_is_fail_closed(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', attempt=1, action='first'))
    journal.ingest(make_event(2, 'tool.effect_reserved', attempt=1, action='second'))
    journal.ingest(make_event(1, 'worker.started', attempt=2))
    assert journal.assess('run-1', max_events=1)['state'] == 'TRACE_WINDOW_LIMIT_EXCEEDED'


def test_changed_historical_effects_change_dedup_fingerprint():
    a = {'attempt': 3, 'state': 'NEEDS_RECONCILIATION',
         'historical_unresolved_effects': ['1:a']}
    b = {**a, 'historical_unresolved_effects': ['1:b']}
    assert _fingerprint(a) != _fingerprint(b)


def test_history_recent_limit(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'worker.started'))
    w = StatusWatch(journal.path, tmp_path / 'alerts.db', clock=lambda: 1000.)
    assert w.sample('run-1') is not None
    assert w.sample('run-1', now=1200) is not None
    assert len(w.history('run-1')) == 2
    assert len(w.history('run-1', limit=1)) == 1
    assert w.history('run-1', limit=1)[0]['state'] == 'WORKER_UNRESPONSIVE'
    with pytest.raises(ValueError):
        w.history('run-1', limit=-1)


def test_duplicate_reservation_is_not_cleared_by_one_ack(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', action='important'))
    journal.ingest(make_event(2, 'tool.effect_reserved', action='important'))
    journal.ingest(make_event(3, 'tool.effect_acknowledged', action='important'))
    state = journal.assess('run-1', now=1001)
    assert state['state'] == 'EFFECT_IN_FLIGHT'
    assert state['unresolved_effects'] == ['important']


def test_duplicate_historical_reservation_must_be_reconciled(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'tool.effect_reserved', action='important'))
    journal.ingest(make_event(2, 'tool.effect_reserved', action='important'))
    journal.ingest(make_event(3, 'tool.effect_acknowledged', action='important'))
    journal.ingest(make_event(1, 'worker.started', attempt=2))
    state = journal.assess('run-1', now=1001)
    assert state['state'] == 'NEEDS_RECONCILIATION'
    assert state['historical_unresolved_effects'] == ['1:important']


def test_event_id_db_column_tampering_breaks_chain(tmp_path):
    import sqlite3
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'worker.started'))
    with sqlite3.connect(journal.path) as db:
        db.execute("UPDATE events SET event_id='different-id' WHERE position=1")
    assert journal.verify_chain() is False


def test_untrusted_other_emitter_cannot_clear_approval(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'approval.required', source='worker-a', action='grant'))
    journal.ingest(make_event(1, 'approval.resolved', source='observer-b', action='grant'))
    diagnosis = journal.assess('run-1', now=1001)
    assert diagnosis['pending_approvals'] == ['grant']
    assert diagnosis['state'] in ('TRACE_INCOMPLETE', 'WAITING_APPROVAL')


def test_duplicate_completion_reports_require_trace_review(tmp_path):
    journal = EventJournal(tmp_path / 'events.db', clock=lambda: 1000.)
    journal.ingest(make_event(1, 'run.reported_completed'))
    journal.ingest(make_event(2, 'run.reported_completed'))
    assert journal.assess('run-1', now=1001)['state'] == 'TRACE_INCOMPLETE'
