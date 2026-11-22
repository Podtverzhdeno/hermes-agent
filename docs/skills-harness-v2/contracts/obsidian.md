# obsidian: independent harness acceptance contract

**Scope:** Read within configured vault; writes only to explicit narrow advice directory, not entire vault.

**Operation families:** search_notes, read_note (read); create_note, patch_note, delete_note (write).

**Host-side preflight:** Canonical root and target; reject symlink/junction traversal; ensure writable zone and expected note checksum; back up target and preserve links.

**Approval boundary:** Signed single-note path/content approval; no implicit approval to edit .obsidian metadata, all vault files, or change write boundary.

**Independent verification:** Handle-based/narrow writer with persisted readback and SHA; count and test incoming wikilinks; rollback on failed patch.

**Unknown outcomes and safe stop:** Concurrent note auto-save conflict -> refuse/merge proposal; cannot infer successful disk update from response text.

**Adversarial regression families:** junction; UNC/path aliases; Unicode names; out-of-zone edit; simultaneous writer; malicious instructions in note.

## Implementation note
This is a proposed typed semantic contract, not an executable permission list
or proof that the fork implements these checks. Couple it only to vetted
host-side adapters. Skill text and `harness.json` are advisory. Real-world
side effects remain disabled until cross-surface integration and provider
verification tests pass.
