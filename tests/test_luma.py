from datetime import UTC, datetime

from event_radar.sources.luma import raw_from_luma_detail, raw_from_luma_entry


def test_raw_from_discover_entry():
    entry = {
        "event": {
            "api_id": "evt-1",
            "name": "AI Leaders Vol. 11 - Boston",
            "url": "abc123",
            "start_at": "2026-09-15T22:00:00.000Z",
            "timezone": "America/New_York",
            "location_type": "offline",
            "geo_address_info": {
                "city": "Boston",
                "full_address": "Cambridge, MA",
            },
            "coordinate": {"latitude": 42.36, "longitude": -71.06},
        },
        "hosts": [{"name": "AI Leaders"}],
        "ticket_info": {"is_free": True, "require_approval": True, "is_sold_out": False, "price": None},
        "waitlist_active": False,
    }
    raw = raw_from_luma_entry(entry, source_id="luma_boston_ai", fetched_at=datetime.now(UTC))
    assert raw is not None
    assert raw.title.startswith("AI Leaders")
    assert raw.is_free is True
    assert raw.require_approval is True
    assert raw.canonical_url == "https://luma.com/abc123"
    assert raw.city == "Boston"


def test_raw_from_detail_ticket_types():
    data = {
        "event": {
            "api_id": "evt-c0BscS7DiwVeBiz",
            "name": "Fintech That Thinks: Fintech Sandbox Innovation Forum 2026",
            "url": "fintechthatthinks",
            "start_at": "2026-09-22T12:00:00.000Z",
            "end_at": "2026-09-23T21:30:00.000Z",
            "timezone": "America/New_York",
            "location_type": "offline",
            "geo_address_info": {"city": "Boston"},
        },
        "hosts": [{"name": "Fintech Sandbox"}],
        "calendar": {"name": "Boston Fintech Week"},
        "ticket_info": {"price": {"cents": 69500, "currency": "usd"}, "is_free": False},
        "ticket_types": [
            {"name": "Standard", "cents": 69500},
            {"name": "Early Bird", "cents": 49500, "valid_end_at": "2026-08-22T03:59:59.000Z"},
        ],
        "categories": [{"name": "AI", "slug": "ai"}],
    }
    raw = raw_from_luma_detail(data, source_id="luma_fintech", fetched_at=datetime.now(UTC))
    assert raw is not None
    assert raw.organizer == "Fintech Sandbox"
    assert len(raw.ticket_types) == 2
    assert "AI" in raw.categories
