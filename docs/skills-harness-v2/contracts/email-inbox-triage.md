# email-inbox-triage: independent harness acceptance contract

**Scope:** Exact mailbox/account, thread, message recipients including CC/BCC and attachments.

**Operation families:** read_thread (read); draft_reply (draft); send_reply, archive_thread, delete_thread (external effect).

**Host-side preflight:** Read complete thread/pagination and Sent evidence; bind to stable thread/account, normalized MIME body and attachment hashes; match recipient identities.

**Approval boundary:** Drafting is not permission to send; signed exact recipients, subject, body, attachments and sender account for sends.

**Independent verification:** Provider message-ID and Sent readback tied to thread and exact recipients; state of archive/delete and folder coverage.

**Unknown outcomes and safe stop:** SMTP timeout after acceptance -> UNKNOWN, never blind send retry; inspect Sent and mailbox before any new intent.

**Adversarial regression families:** email injection; account switch; hidden BCC change; attachment replacement; 504/SMTP ambiguity; truncated thread.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
