from datetime import UTC, datetime

from event_radar.alerts import format_alert
from event_radar.models import (
    AccessRoute,
    AccessType,
    EventRecord,
    ObservationKind,
    ScoreBreakdown,
    SourceRef,
)


def test_alert_format_contains_core_fields():
    now = datetime(2026, 9, 11, tzinfo=UTC)
    event = EventRecord(
        id="e",
        title="Example Event",
        source_url="https://example.com",
        canonical_url="https://example.com",
        registration_url="https://example.com/reg",
        discovered_at=now,
        last_checked_at=now,
        start_at=datetime(2026, 9, 22, tzinfo=UTC),
        city="Boston",
        standard_price=695,
        sources=[SourceRef(source_id="s", source_type="t", source_url="https://example.com", fetched_at=now)],
        access_routes=[
            AccessRoute(type=AccessType.STANDARD_TICKET, price=695, observation_kind=ObservationKind.CONFIRMED_CURRENT),
            AccessRoute(type=AccessType.STUDENT_TICKET, price=0, observation_kind=ObservationKind.CONFIRMED_CURRENT, status="uncertain"),
        ],
        score=ScoreBreakdown(total=92, reasons=["AI + fintech + strong professional networking"]),
    )
    text = format_alert(event)
    assert "92/100" in text
    assert "Example Event" in text
    assert "Boston" in text
    assert "student" in text.lower()
    assert "https://example.com/reg" in text
