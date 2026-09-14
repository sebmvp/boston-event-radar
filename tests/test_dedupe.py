from datetime import UTC, datetime, timedelta

from event_radar.models import AccessRoute, AccessType, EventRecord, ObservationKind, SourceRef
from event_radar.processing.dedupe import deduplicate, normalize_title, same_event


def _event(title: str, url: str, **kwargs) -> EventRecord:
    now = datetime(2026, 9, 11, tzinfo=UTC)
    start = kwargs.pop("start_at", now)
    sources = kwargs.pop("sources", None) or [
        SourceRef(source_id="a", source_type="t", source_url=url, fetched_at=now)
    ]
    return EventRecord(
        id=kwargs.pop("id", title),
        title=title,
        source_url=url,
        canonical_url=url,
        discovered_at=now,
        last_checked_at=now,
        start_at=start,
        sources=sources,
        **kwargs,
    )


def test_normalize_title_strips_year_and_punct():
    assert normalize_title("Boston Fintech Week 2026!") == "boston fintech week"


def test_same_url_is_same_event():
    a = _event("Fintech That Thinks", "https://luma.com/fintechthatthinks?coupon=X")
    b = _event("Fintech That Thinks: Forum", "https://www.luma.com/fintechthatthinks")
    # coupon query stripped by host+path
    a.canonical_url = "https://luma.com/fintechthatthinks"
    b.canonical_url = "https://luma.com/fintechthatthinks"
    assert same_event(a, b)


def test_merge_keeps_student_route_from_secondary_source():
    now = datetime(2026, 9, 22, tzinfo=UTC)
    luma = _event(
        "Fintech That Thinks",
        "https://luma.com/fintechthatthinks",
        organizer="Fintech Sandbox",
        city="Boston",
        start_at=now,
        access_routes=[
            AccessRoute(type=AccessType.STANDARD_TICKET, price=695, observation_kind=ObservationKind.CONFIRMED_CURRENT)
        ],
        sources=[SourceRef(source_id="luma", source_type="luma_event", source_url="https://luma.com/fintechthatthinks", fetched_at=now)],
    )
    html = _event(
        "Boston Fintech Week",
        "https://bostonfintechweek.com/",
        organizer="Fintech Sandbox",
        city="Boston",
        start_at=now,
        access_routes=[
            AccessRoute(
                type=AccessType.STUDENT_TICKET,
                coupon_code="STUDENT2026",
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
            )
        ],
        sources=[SourceRef(source_id="html", source_type="html_page", source_url="https://bostonfintechweek.com/", fetched_at=now)],
    )
    # Force match via similar title + same time + organizer
    html.title = "Fintech That Thinks: Fintech Sandbox Innovation Forum"
    merged = deduplicate([luma, html])
    assert len(merged) == 1
    types = {r.type for r in merged[0].access_routes}
    assert AccessType.STANDARD_TICKET in types
    assert AccessType.STUDENT_TICKET in types
    assert {s.source_id for s in merged[0].sources} == {"luma", "html"}


def test_does_not_merge_two_different_ai_events():
    now = datetime(2026, 9, 15, tzinfo=UTC)
    a = _event("AI Mixer Boston", "https://luma.com/mixer-a", start_at=now, city="Boston")
    b = _event(
        "AI Mixer Boston Volume 2",
        "https://luma.com/mixer-b",
        start_at=now + timedelta(days=7),
        city="Boston",
    )
    assert not same_event(a, b)
    merged = deduplicate([a, b])
    assert len(merged) == 2
