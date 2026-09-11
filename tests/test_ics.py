from datetime import UTC, datetime

from icalendar import Calendar, Event

from event_radar.sources.ics import raw_from_vevent


def test_ics_vevent():
    cal = Calendar()
    vevent = Event()
    vevent.add("uid", "abc@mit.edu")
    vevent.add("summary", "Statistics and Data Science Seminar")
    vevent.add("dtstart", datetime(2026, 9, 18, 16, 0, tzinfo=UTC))
    vevent.add("dtend", datetime(2026, 9, 18, 17, 0, tzinfo=UTC))
    vevent.add("location", "MIT Building 2")
    vevent.add("url", "https://calendar.mit.edu/event/sds")
    vevent.add("description", "Talk on causal inference")
    cal.add_component(vevent)
    parsed = cal.walk("VEVENT")[0]
    raw = raw_from_vevent(
        parsed,
        source_id="mit_ics",
        source_url="https://calendar.mit.edu/calendar.ics",
        fetched_at=datetime.now(UTC),
        org="MIT",
    )
    assert raw is not None
    assert "Data Science" in raw.title
    assert raw.organizer == "MIT"
    assert raw.start_at is not None
