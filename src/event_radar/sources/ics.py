"""Public ICS/iCal adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from icalendar import Calendar

from event_radar.http_client import FetchError
from event_radar.models import LocationMode, RawEvent
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    dt = getattr(value, "dt", value)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    try:
        return datetime.combine(dt, datetime.min.time(), tzinfo=UTC)
    except TypeError:
        return None


def raw_from_vevent(component: Any, *, source_id: str, source_url: str, fetched_at: datetime, org: str | None) -> RawEvent | None:
    summary = component.get("summary")
    title = str(summary).strip() if summary else ""
    if not title:
        return None
    uid = str(component.get("uid") or "") or None
    description = str(component.get("description") or "") or None
    location = str(component.get("location") or "") or None
    url = str(component.get("url") or "") or source_url
    return RawEvent(
        source_id=source_id,
        source_type="ics",
        external_id=uid,
        source_url=url,
        title=title,
        description=description,
        organizer=org,
        start_at=_as_dt(component.get("dtstart")),
        end_at=_as_dt(component.get("dtend")),
        timezone=None,
        venue=location,
        city=None,
        address=location,
        location_mode=LocationMode.VIRTUAL if location and "http" in location.lower() else LocationMode.UNKNOWN,
        registration_url=url,
        canonical_url=url,
        fetched_at=fetched_at,
        raw={"uid": uid},
    )


class IcsAdapter:
    source_type = "ics"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = config["id"]

    def discover(self, ctx: FetchContext) -> SourceFetchResult:
        run = start_run(self.source_id, self.source_type, ctx.now)
        events: list[RawEvent] = []
        errors = 0
        url = self.config.get("url")
        if not url:
            finish_run(run, events=[], error="missing url")
            return SourceFetchResult(run=run, events=[])
        try:
            payload = ctx.fetcher.get_bytes(url)
            calendar = Calendar.from_ical(payload)
            org = self.config.get("org")
            horizon = ctx.now
            from datetime import timedelta

            until = horizon + timedelta(days=ctx.lookahead_days)
            for component in calendar.walk("VEVENT"):
                try:
                    raw = raw_from_vevent(
                        component,
                        source_id=self.source_id,
                        source_url=url,
                        fetched_at=ctx.now,
                        org=org,
                    )
                    if raw is None:
                        errors += 1
                        continue
                    if raw.start_at and (raw.start_at < horizon - timedelta(days=1) or raw.start_at > until):
                        continue
                    events.append(raw)
                except Exception:
                    errors += 1
            finish_run(run, events=events, parse_errors=errors)
        except FetchError as exc:
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        return SourceFetchResult(run=run, events=events)
