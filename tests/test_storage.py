from datetime import UTC, datetime
from pathlib import Path

from event_radar.models import EventRecord, SourceRef
from event_radar.storage import Store


def _event(title: str, url: str, start: datetime, city: str = "Boston") -> EventRecord:
    now = datetime.now(UTC)
    return EventRecord(
        id=title,
        title=title,
        source_url=url,
        canonical_url=url,
        discovered_at=now,
        last_checked_at=now,
        start_at=start,
        city=city,
        sources=[SourceRef(source_id="s", source_type="t", source_url=url, fetched_at=now)],
    )


def test_repeated_upsert_does_not_duplicate(tmp_path: Path) -> None:
    store = Store(tmp_path / "events.db")
    start = datetime(2026, 9, 22, 12, tzinfo=UTC)
    event = _event("Fintech That Thinks", "https://luma.com/fintechthatthinks", start)
    store.upsert_events([event])
    store.upsert_events([event])
    assert store.count() == 1


def test_upsert_merges_same_canonical_url(tmp_path: Path) -> None:
    store = Store(tmp_path / "events.db")
    start = datetime(2026, 9, 22, 12, tzinfo=UTC)
    a = _event("Fintech That Thinks", "https://luma.com/fintechthatthinks", start)
    a.id = "id-a"
    b = _event("Fintech That Thinks Forum", "https://www.luma.com/fintechthatthinks", start)
    b.id = "id-b"
    b.canonical_url = "https://luma.com/fintechthatthinks"
    a.canonical_url = "https://luma.com/fintechthatthinks"
    store.upsert_events([a])
    store.upsert_events([b])
    assert store.count() == 1
