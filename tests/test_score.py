from datetime import UTC, datetime

from event_radar.config import load_profile
from event_radar.models import (
    AccessRoute,
    AccessStatus,
    AccessType,
    EventRecord,
    LocationMode,
    ObservationKind,
    SourceRef,
)
from event_radar.processing.score import score_event


def test_fintech_week_outscores_nightlife():
    profile = load_profile()
    now = datetime(2026, 9, 11, tzinfo=UTC)
    src = SourceRef(source_id="x", source_type="t", source_url="https://x", fetched_at=now)
    fintech = EventRecord(
        id="f",
        title="Fintech That Thinks: Fintech Sandbox Innovation Forum 2026",
        description="AI, fintech leaders, student tickets, networking",
        organizer="Fintech Sandbox",
        source_url="https://luma.com/fintechthatthinks",
        canonical_url="https://luma.com/fintechthatthinks",
        discovered_at=now,
        last_checked_at=now,
        start_at=datetime(2026, 9, 22, tzinfo=UTC),
        city="Boston",
        location_mode=LocationMode.IN_PERSON,
        sources=[src],
        categories=["AI"],
        standard_price=695,
        access_routes=[
            AccessRoute(type=AccessType.STANDARD_TICKET, price=695, observation_kind=ObservationKind.CONFIRMED_CURRENT, status=AccessStatus.OPEN),
            AccessRoute(
                type=AccessType.STUDENT_TICKET,
                coupon_code="STUDENT2026",
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
                status=AccessStatus.UNCERTAIN,
            ),
        ],
        series_id="boston-fintech-week",
    )
    party = EventRecord(
        id="p",
        title="Comedy Open Mic Nightlife Party",
        description="stand-up comedy and club night",
        source_url="https://luma.com/party",
        canonical_url="https://luma.com/party",
        discovered_at=now,
        last_checked_at=now,
        start_at=datetime(2026, 9, 12, tzinfo=UTC),
        city="Boston",
        sources=[src],
        access_routes=[AccessRoute(type=AccessType.FREE_ADMISSION, price=0, observation_kind=ObservationKind.CONFIRMED_CURRENT)],
    )
    s1 = score_event(fintech, profile, now=now)
    s2 = score_event(party, profile, now=now)
    assert s1.total > s2.total
    assert s1.total >= 70
    assert s1.reasons
    assert any("student" in r.lower() for r in s1.reasons)
