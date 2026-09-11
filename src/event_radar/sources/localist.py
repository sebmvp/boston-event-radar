"""Localist university calendar JSON adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from event_radar.http_client import FetchError
from event_radar.models import LocationMode, RawEvent
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def _parse_price(ticket_cost: str | None) -> float | None:
    if not ticket_cost:
        return None
    text = ticket_cost.replace(",", "").strip()
    if text in {"$0", "0", "free", "Free"}:
        return 0.0
    cleaned = text.replace("$", "").split("-")[0].strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def raw_from_localist(item: dict[str, Any], *, source_id: str, org: str | None, fetched_at: datetime) -> RawEvent | None:
    event = item.get("event") or item
    title = (event.get("title") or "").strip()
    if not title:
        return None
    instances = event.get("event_instances") or []
    start = end = None
    if instances:
        inst = (instances[0] or {}).get("event_instance") or instances[0]
        start = _parse_dt(inst.get("start"))
        end = _parse_dt(inst.get("end"))
    geo = event.get("geo") or {}
    url = event.get("localist_url") or event.get("url") or ""
    ticket_cost = event.get("ticket_cost")
    is_free = event.get("free")
    if is_free is True:
        is_free_flag: bool | None = True
    elif is_free is False:
        is_free_flag = False
    else:
        is_free_flag = True if ticket_cost in {"$0", "0"} else None
    loc_mode = LocationMode.VIRTUAL if (event.get("stream_url") and not event.get("location_name")) else LocationMode.IN_PERSON
    if event.get("experience") == "virtual":
        loc_mode = LocationMode.VIRTUAL
    tags = [t.get("name") if isinstance(t, dict) else str(t) for t in (event.get("tags") or [])]
    filters = event.get("filters") or {}
    for group in filters.values() if isinstance(filters, dict) else []:
        if isinstance(group, list):
            for node in group:
                name = node.get("name") if isinstance(node, dict) else None
                if name:
                    tags.append(name)
    return RawEvent(
        source_id=source_id,
        source_type="localist",
        external_id=str(event.get("id")) if event.get("id") is not None else None,
        source_url=url,
        title=title,
        description=event.get("description_text") or event.get("description"),
        organizer=org,
        start_at=start,
        end_at=end,
        timezone=None,
        venue=event.get("location_name") or event.get("location"),
        city=(geo.get("city") if isinstance(geo, dict) else None),
        address=event.get("address") or (geo.get("street") if isinstance(geo, dict) else None),
        latitude=(geo.get("latitude") if isinstance(geo, dict) else None),
        longitude=(geo.get("longitude") if isinstance(geo, dict) else None),
        location_mode=loc_mode,
        categories=tags,
        registration_url=event.get("ticket_url") or url,
        canonical_url=url,
        price=_parse_price(ticket_cost),
        is_free=is_free_flag,
        require_approval=None,
        waitlist=None,
        sold_out=None,
        tags=tags,
        fetched_at=fetched_at,
        raw={"ticket_cost": ticket_cost, "has_register": event.get("has_register")},
    )


class LocalistAdapter:
    source_type = "localist"

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
        days = int(self.config.get("days") or ctx.lookahead_days)
        per_page = int(ctx.extra.get("localist_per_page") or 50)
        org = self.config.get("org")
        try:
            page = 1
            while page <= 6:
                params = {"days": days, "pp": per_page, "page": page}
                url = f"{base}/api/2/events?{urlencode(params)}"
                data = ctx.fetcher.get_json(url)
                rows = data.get("events") or []
                if not rows:
                    break
                for item in rows:
                    try:
                        raw = raw_from_localist(item, source_id=self.source_id, org=org, fetched_at=ctx.now)
                        if raw is None:
                            errors += 1
                            continue
                        events.append(raw)
                    except Exception:
                        errors += 1
                if len(rows) < per_page:
                    break
                page += 1
            finish_run(run, events=events, parse_errors=errors)
        except FetchError as exc:
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=events, parse_errors=errors, error=str(exc))
        return SourceFetchResult(run=run, events=events)
