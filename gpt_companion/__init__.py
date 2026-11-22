"""Read-only GPT companion observability primitives (no model/tool execution)."""

from .journal import EventJournal, JournalConflict, validate_event

__all__ = ["EventJournal", "JournalConflict", "validate_event"]
