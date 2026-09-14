from datetime import UTC, datetime

from event_radar.config import load_profile, load_series
from event_radar.models import ObservationKind, RawEvent, RecurringSeries
from event_radar.pipeline import _attach_historical
from event_radar.processing.normalize import normalize
from event_radar.processing.score import score_event
from event_radar.processing.series import match_series


def test_series_match_and_historical_not_current():
    now = datetime(2026, 9, 11, tzinfo=UTC)
    raw = RawEvent(
        source_id="x",
        source_type="html_page",
        source_url="https://bostonfintechweek.com/",
        title="Boston Fintech Week",
        organizer="Fintech Sandbox",
        city="Boston",
        start_at=datetime(2026, 9, 22, tzinfo=UTC),
        fetched_at=now,
        canonical_url="https://bostonfintechweek.com/",
    )
    event = normalize(raw, now=now)
    series_list = [RecurringSeries.model_validate(s) for s in load_series()["series"]]
    series = match_series(event, series_list)
    assert series is not None
    assert series.id == "boston-fintech-week"
    _attach_historical(event, series)
    hist = [r for r in event.access_routes if r.observation_kind == ObservationKind.HISTORICAL]
    assert hist
    assert event.best_current_access() is None or event.best_current_access().observation_kind != ObservationKind.HISTORICAL
    event.series_id = series.id
    score = score_event(event, load_profile(), now=now)
    assert score.total > 0
    assert "volunteer" not in " ".join(r.type.value for r in event.access_routes if r.observation_kind == ObservationKind.CONFIRMED_CURRENT)


def test_satellite_fintech_event_is_not_the_week():
    now = datetime(2026, 9, 11, tzinfo=UTC)
    raw = RawEvent(
        source_id="x",
        source_type="luma_discover",
        source_url="https://luma.com/fzwj0mfg",
        title="Fintech that Thinks: Career Advisory and Networking Summit",
        organizer="Someone",
        city="Boston",
        start_at=datetime(2026, 9, 25, tzinfo=UTC),
        fetched_at=now,
        canonical_url="https://luma.com/fzwj0mfg",
    )
    event = normalize(raw, now=now)
    series_list = [RecurringSeries.model_validate(s) for s in load_series()["series"]]
    assert match_series(event, series_list) is None
