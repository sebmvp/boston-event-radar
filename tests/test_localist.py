from datetime import UTC, datetime

from event_radar.sources.localist import raw_from_localist


def test_localist_hackathon():
    item = {
        "event": {
            "id": 99,
            "title": "Imaginary Instrument Hackathon",
            "description_text": "Build instruments. Students welcome.",
            "localist_url": "https://calendar.northeastern.edu/event/imaginary-instrument-hackathon",
            "free": True,
            "ticket_cost": "$0",
            "ticket_url": None,
            "location_name": "Northeastern University",
            "geo": {"city": "Boston", "latitude": 42.3398, "longitude": -71.0892},
            "event_instances": [
                {"event_instance": {"start": "2026-09-20T10:00:00-04:00", "end": "2026-09-20T18:00:00-04:00"}}
            ],
            "tags": [{"name": "engineering"}],
        }
    }
    raw = raw_from_localist(item, source_id="neu", org="Northeastern", fetched_at=datetime.now(UTC))
    assert raw is not None
    assert raw.is_free is True
    assert raw.price == 0
    assert raw.city == "Boston"
    assert raw.start_at is not None
