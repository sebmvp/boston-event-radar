from __future__ import annotations

from datetime import UTC, datetime, timedelta

from event_radar.models import EventRecord, RawEvent
from event_radar.processing.text import has_term


def topical_enough(event: EventRecord | RawEvent, keywords: dict, *, always_keep: bool = False) -> bool:
    if always_keep:
        return True
    include = [k.lower() for k in keywords.get("include") or []]
    exclude = [k.lower() for k in keywords.get("exclude_unless_high_signal") or []]
    if isinstance(event, EventRecord):
        blob = " ".join(
            [
                event.title,
                event.description or "",
                event.organizer or "",
                " ".join(event.categories),
                event.venue or "",
            ]
        ).lower()
    else:
        blob = " ".join(
            [
                event.title,
                event.description or "",
                event.organizer or "",
                " ".join(event.categories),
                " ".join(event.tags),
            ]
        ).lower()
    has_include = any(has_term(blob, k) for k in include) if include else True
    has_exclude = any(has_term(blob, k) for k in exclude)
    if has_exclude and not has_include:
        return False
    return has_include


def is_upcoming(event: EventRecord, now: datetime | None = None, *, grace_hours: int = 12) -> bool:
    now = now or datetime.now(UTC)
    start = event.start_at
    if start is None:
        return True
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return start >= now - timedelta(hours=grace_hours)
