"""WordPress The Events Calendar (Tribe) public REST adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from event_radar.http_client import FetchError
from event_radar.models import LocationMode, RawEvent
from event_radar.processing.geo import city_allowed
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run


def _parse_dt(value: str | None, tz_name: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("America/New_York")
        dt = dt.replace(tzinfo=tz)
    return dt


def _plain(html: str | None) -> str | None:
    if not html:
        return None
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True) or None


def _venue_city(venue: Any) -> tuple[str | None, str | None, str | None, float | None, float | None]:
    if isinstance(venue, list):
        venue = venue[0] if venue else {}
    if not isinstance(venue, dict) or not venue:
        return None, None, None, None, None
    city = venue.get("city")
    name = venue.get("venue") or venue.get("name")
    address = venue.get("address") or venue.get("address_1")
    lat = venue.get("lat") or venue.get("geo_lat")
    lng = venue.get("lng") or venue.get("geo_lng")
    try:
        lat_f = float(lat) if lat not in (None, "") else None
        lng_f = float(lng) if lng not in (None, "") else None
    except (TypeError, ValueError):
        lat_f = lng_f = None
    return name, city, address, lat_f, lng_f


def _parse_cost(event: dict[str, Any]) -> tuple[float | None, bool | None]:
    cost = event.get("cost")
    if isinstance(cost, str) and cost.strip():
        text = cost.strip().lower().replace(",", "")
        if text in {"free", "0", "$0", "$0.00"}:
            return 0.0, True
        cleaned = text.replace("$", "").split("-")[0].strip()
        try:
            return float(cleaned), False
        except ValueError:
            pass
    details = event.get("cost_details") or {}
    values = details.get("values") if isinstance(details, dict) else None
    if isinstance(values, list) and values:
        try:
            amount = float(str(values[0]).replace("$", "").replace(",", ""))
            return amount, amount == 0
        except ValueError:
            return None, None
    return None, None


def raw_from_tribe(event: dict[str, Any], *, source_id: str, org: str | None, fetched_at: datetime) -> RawEvent | None:
    title = (event.get("title") or "").strip()
    if not title:
        return None
    tz_name = event.get("timezone")
    start = _parse_dt(event.get("utc_start_date"), "UTC") if event.get("utc_start_date") else _parse_dt(event.get("start_date"), tz_name)
    end = _parse_dt(event.get("utc_end_date"), "UTC") if event.get("utc_end_date") else _parse_dt(event.get("end_date"), tz_name)
    venue_name, city, address, lat, lng = _venue_city(event.get("venue"))
    price, is_free = _parse_cost(event)
    website = event.get("website") or None
    url = event.get("url") or website or ""
    cats = event.get("categories") or []
    tags = [c.get("name") for c in cats if isinstance(c, dict) and c.get("name")]
    virtual = bool(event.get("is_virtual"))
    location_mode = LocationMode.VIRTUAL if virtual else LocationMode.IN_PERSON
    if virtual and venue_name:
        location_mode = LocationMode.HYBRID
    organizer = org
    org_field = event.get("organizer")
    if isinstance(org_field, list) and org_field and isinstance(org_field[0], dict):
        organizer = org_field[0].get("organizer") or organizer
    elif isinstance(org_field, dict):
        organizer = org_field.get("organizer") or organizer
    return RawEvent(
        source_id=source_id,
        source_type="tribe",
        external_id=str(event.get("id")) if event.get("id") is not None else None,
        source_url=url,
        title=title,
        description=_plain(event.get("description") or event.get("excerpt")),
        organizer=organizer,
        start_at=start,
        end_at=end,
        timezone=tz_name or "America/New_York",
        venue=venue_name,
        city=city,
        address=address,
        latitude=lat,
        longitude=lng,
        location_mode=location_mode,
        categories=[str(t) for t in tags],
        registration_url=website or url,
        canonical_url=url,
        price=price,
        is_free=is_free,
        tags=[str(t) for t in tags],
        fetched_at=fetched_at,
        raw={"website": website, "cost": event.get("cost")},
    )


class TribeEventsAdapter:
    source_type = "tribe"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = config["id"]

    def discover(self, ctx: FetchContext) -> SourceFetchResult:
        run = start_run(self.source_id, self.source_type, ctx.now)
        events: list[RawEvent] = []
        errors = 0
        base = (self.config.get("base_url") or "").rstrip("/")
        if not base:
            finish_run(run, events=[], error="missing base_url")
            return SourceFetchResult(run=run, events=[])
        per_page = int(self.config.get("per_page") or 50)
        org = self.config.get("org")
        allowlist = self.config.get("city_allowlist") or []
        start_date = ctx.now.date().isoformat()
        try:
            page = 1
            while page <= 8:
                url = (
                    f"{base}/wp-json/tribe/events/v1/events"
                    f"?per_page={per_page}&page={page}&start_date={start_date}&status=publish"
                )
                data = ctx.fetcher.get_json(url)
                rows = data.get("events") or []
                if not rows:
                    break
                for item in rows:
                    try:
                        raw = raw_from_tribe(item, source_id=self.source_id, org=org, fetched_at=ctx.now)
                        if raw is None:
                            errors += 1
                            continue
                        if not raw.city and self.config.get("city_hint"):
                            venue_l = (raw.venue or "").lower()
                            title_l = raw.title.lower()
                            remote = ("houston", "chicago", "berkeley", "santa clara", "nyc", "new york", "san francisco")
                            if any(tok in title_l for tok in remote):
                                continue
                            if any(tok in venue_l for tok in ("boston", "cambridge", "somerville", "massrobotics", "greentown boston")) or not raw.venue:
                                raw.city = str(self.config.get("city_hint"))
                        if not city_allowed(
                            city=raw.city,
                            latitude=raw.latitude,
                            longitude=raw.longitude,
                            allowlist=allowlist,
                            virtual=raw.location_mode == LocationMode.VIRTUAL,
                        ):
                            continue
                        events.append(raw)
                    except Exception:
                        errors += 1
                total_pages = int(data.get("total_pages") or page)
                if page >= total_pages or len(rows) < per_page:
                    break
                page += 1
            finish_run(run, events=events, parse_errors=errors)
        except FetchError as exc:
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        return SourceFetchResult(run=run, events=events)
