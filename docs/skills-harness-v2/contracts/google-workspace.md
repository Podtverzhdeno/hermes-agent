# google-workspace: independent harness acceptance contract

**Scope:** Exact Google account, Drive resource id, calendar id and granted OAuth scopes.

**Operation families:** read_resource (read); edit_document, create_calendar_event, delete_resource (mutation).

**Host-side preflight:** Resolve stable resource ID (not title); check ETag/revision, document ACL, calendar timezone and DST ambiguity; inspect invites and privacy.

**Approval boundary:** Exact document edits, recipient list, attendees/calendar/time interval or deletion; separate signed authorization per operation.

**Independent verification:** Re-fetch document revision/content; verify calendar event ID/date/attendees, Drive delete/trash state and account identity.

**Unknown outcomes and safe stop:** HTTP timeout after write -> UNKNOWN and provider lookup before a new operation; avoid duplicate calendar invites.

**Adversarial regression families:** wrong account; stale ETag; duplicate titles; ambiguous DST; Google batch partial failure; scope escalation.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
