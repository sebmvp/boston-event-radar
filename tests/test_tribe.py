from datetime import datetime
from zoneinfo import ZoneInfo

from event_radar.sources.tribe import raw_from_tribe


def test_tribe_parses_local_timezone_not_utc():
    item = {
        "id": 11124,
        "title": "Inside MassRobotics: Open House for Robotics Startups",
        "description": "<p>Join us at MassRobotics during Startup Boston Week.</p>",
        "url": "https://www.massrobotics.org/event/inside-massrobotics-open-house-for-robotics-startups/",
        "website": "https://luma.com/zobtuzci",
        "start_date": "2026-09-16 14:00:00",
        "end_date": "2026-09-16 16:00:00",
        "timezone": "America/New_York",
        "cost": "",
        "cost_details": {"values": []},
        "venue": {"venue": "MassRobotics", "city": "Boston"},
        "is_virtual": False,
        "categories": [{"name": "Public"}],
    }
    raw = raw_from_tribe(item, source_id="massrobotics", org="MassRobotics", fetched_at=datetime.now(ZoneInfo("UTC")))
    assert raw is not None
    assert raw.city == "Boston"
    assert raw.start_at is not None
    assert raw.start_at.tzinfo is not None
    assert raw.start_at.hour == 14
    assert raw.registration_url == "https://luma.com/zobtuzci"
    assert "Startup Boston Week" in (raw.description or "")
