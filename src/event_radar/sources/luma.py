"""Luma public discover + event detail adapters.

These hit the same JSON endpoints luma.com uses for public calendar pages.
They do not use a paid Luma API key and do not log in.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from event_radar.http_client import FetchError
from event_radar.models import LocationMode, RawEvent
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run

API_BASE = "https://api.lu.ma"
WEB_ORIGIN = "https://luma.com"


def _luma_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Origin": WEB_ORIGIN,
        "Referer": f"{WEB_ORIGIN}/",
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cents_price(info: dict[str, Any] | None) -> float | None:
    if not info:
        return None
    price = info.get("price") if "price" in info else info
    if isinstance(price, dict) and isinstance(price.get("cents"), int):
        return price["cents"] / 100.0
    if isinstance(info.get("cents"), int):
        return info["cents"] / 100.0
    return None


def _location_mode(event: dict[str, Any]) -> LocationMode:
    kind = (event.get("location_type") or "").lower()
    if kind in {"offline", "in_person", "in-person"}:
        return LocationMode.IN_PERSON
    if kind in {"online", "virtual"}:
        return LocationMode.VIRTUAL
    if kind in {"hybrid"}:
        return LocationMode.HYBRID
    return LocationMode.UNKNOWN


def _city_ok(city: str | None, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    if not city:
        return True
    city_l = city.lower()
    return any(city_l.startswith(item.lower()) for item in allowlist)


def raw_from_luma_entry(
    entry: dict[str, Any],
    *,
    source_id: str,
    fetched_at: datetime,
) -> RawEvent | None:
    event = entry.get("event") or {}
    title = (event.get("name") or "").strip()
    slug = event.get("url")
    if not title or not slug:
        return None
    geo = event.get("geo_address_info") or {}
    coord = event.get("coordinate") or geo.get("place_coordinate") or {}
    ticket = entry.get("ticket_info") or {}
    hosts = entry.get("hosts") or []
    organizer = hosts[0]["name"] if hosts and hosts[0].get("name") else None
    calendar = entry.get("calendar") or {}
    if not organizer:
        organizer = calendar.get("name")
    url = f"{WEB_ORIGIN}/{slug}"
    return RawEvent(
        source_id=source_id,
        source_type="luma_discover",
        external_id=event.get("api_id"),
        source_url=url,
        title=title,
        description=None,
        organizer=organizer,
        start_at=_parse_dt(event.get("start_at") or entry.get("start_at")),
        end_at=_parse_dt(event.get("end_at")),
        timezone=event.get("timezone"),
        venue=geo.get("description") or geo.get("address") or geo.get("full_address"),
        city=geo.get("city"),
        address=geo.get("full_address") or geo.get("short_address"),
        latitude=coord.get("latitude") if isinstance(coord, dict) else None,
        longitude=coord.get("longitude") if isinstance(coord, dict) else None,
        location_mode=_location_mode(event),
        categories=[],
        registration_url=url,
        canonical_url=url,
        price=_cents_price(ticket),
        is_free=ticket.get("is_free"),
        require_approval=ticket.get("require_approval"),
        waitlist=bool(entry.get("waitlist_active") or event.get("waitlist_enabled")),
        sold_out=ticket.get("is_sold_out"),
        ticket_types=[],
        fetched_at=fetched_at,
        raw={"guest_count": entry.get("guest_count"), "ticket_info": ticket},
    )


def raw_from_luma_detail(data: dict[str, Any], *, source_id: str, fetched_at: datetime) -> RawEvent | None:
    event = data.get("event") or {}
    title = (event.get("name") or "").strip()
    slug = event.get("url")
    if not title or not slug:
        return None
    entry = {
        "event": event,
        "ticket_info": data.get("ticket_info") or {},
        "hosts": data.get("hosts") or [],
        "calendar": data.get("calendar") or {},
        "waitlist_active": (data.get("ticket_info") or {}).get("is_sold_out") is False
        and event.get("waitlist_enabled"),
        "start_at": data.get("start_at"),
    }
    raw = raw_from_luma_entry(entry, source_id=source_id, fetched_at=fetched_at)
    if raw is None:
        return None
    raw.source_type = "luma_event"
    raw.ticket_types = list(data.get("ticket_types") or [])
    cats = data.get("categories") or []
    raw.categories = [c.get("name") or c.get("slug") for c in cats if c.get("name") or c.get("slug")]
    raw.end_at = raw.end_at or _parse_dt(event.get("end_at"))
    return raw


class LumaDiscoverAdapter:
    source_type = "luma_discover"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = config["id"]

    def discover(self, ctx: FetchContext) -> SourceFetchResult:
        run = start_run(self.source_id, self.source_type, ctx.now)
        events: list[RawEvent] = []
        errors = 0
        slugs = self.config.get("slugs") or [None]
        pages = int(ctx.extra.get("luma_pages") or 3)
        page_size = int(ctx.extra.get("luma_page_size") or 50)
        allowlist = self.config.get("city_allowlist") or []
        try:
            for slug in slugs:
                cursor = None
                for _ in range(pages):
                    params = {
                        "latitude": str(self.config["latitude"]),
                        "longitude": str(self.config["longitude"]),
                        "pagination_limit": str(page_size),
                    }
                    if slug:
                        params["slug"] = slug
                    if cursor:
                        params["pagination_cursor"] = cursor
                    url = f"{API_BASE}/discover/get-paginated-events?{urlencode(params)}"
                    data = ctx.fetcher.get_json(url, headers=_luma_headers())
                    for entry in data.get("entries") or []:
                        try:
                            raw = raw_from_luma_entry(entry, source_id=self.source_id, fetched_at=ctx.now)
                            if raw is None:
                                errors += 1
                                continue
                            if not _city_ok(raw.city, allowlist):
                                continue
                            events.append(raw)
                        except Exception:
                            errors += 1
                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor")
                    if not cursor:
                        break
            finish_run(run, events=events, parse_errors=errors)
        except FetchError as exc:
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        return SourceFetchResult(run=run, events=events)


class LumaEventAdapter:
    source_type = "luma_event"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = config["id"]

    def discover(self, ctx: FetchContext) -> SourceFetchResult:
        run = start_run(self.source_id, self.source_type, ctx.now)
        events: list[RawEvent] = []
        slug = self.config.get("slug") or self.config.get("event_api_id")
        if not slug:
            finish_run(run, events=[], error="missing slug")
            return SourceFetchResult(run=run, events=[])
        url = f"{API_BASE}/event/get?{urlencode({'event_api_id': slug})}"
        try:
            data = ctx.fetcher.get_json(url, headers=_luma_headers())
            raw = raw_from_luma_detail(data, source_id=self.source_id, fetched_at=ctx.now)
            if raw:
                events.append(raw)
            finish_run(run, events=events, parse_errors=0 if raw else 1)
        except FetchError as exc:
            finish_run(run, events=events, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=events, error=str(exc))
        return SourceFetchResult(run=run, events=events)
