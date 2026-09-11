"""Public HTML event page adapter: JSON-LD Event + access-signal text."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from event_radar.http_client import FetchError
from event_radar.models import LocationMode, RawEvent
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _walk_jsonld(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_walk_jsonld(item))
        return found
    if not isinstance(node, dict):
        return found
    types = node.get("@type")
    type_list = types if isinstance(types, list) else [types]
    if any(str(t).lower() == "event" for t in type_list if t):
        found.append(node)
    graph = node.get("@graph")
    if graph:
        found.extend(_walk_jsonld(graph))
    return found


def parse_html_event(
    html: str,
    *,
    source_id: str,
    url: str,
    fetched_at: datetime,
    title_hint: str | None = None,
    organizer_hint: str | None = None,
    city_hint: str | None = None,
) -> list[RawEvent]:
    soup = BeautifulSoup(html, "lxml")
    events: list[RawEvent] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        for node in _walk_jsonld(data):
            title = (node.get("name") or title_hint or "").strip()
            if not title:
                continue
            loc = node.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            address = loc.get("address") if isinstance(loc, dict) else None
            city = city_hint
            addr_text = None
            if isinstance(address, dict):
                city = address.get("addressLocality") or city
                addr_text = address.get("streetAddress")
            elif isinstance(address, str):
                addr_text = address
            events.append(
                RawEvent(
                    source_id=source_id,
                    source_type="html_page",
                    external_id=node.get("@id"),
                    source_url=url,
                    title=title,
                    description=node.get("description"),
                    organizer=organizer_hint,
                    start_at=_parse_dt(node.get("startDate")),
                    end_at=_parse_dt(node.get("endDate")),
                    venue=loc.get("name") if isinstance(loc, dict) else None,
                    city=city,
                    address=addr_text,
                    location_mode=LocationMode.UNKNOWN,
                    registration_url=node.get("url") or url,
                    canonical_url=node.get("url") or url,
                    fetched_at=fetched_at,
                    raw={"jsonld": True},
                )
            )
    page_text = soup.get_text(" ", strip=True)
    hrefs = [
        a.get("href")
        for a in soup.find_all("a", href=True)
        if a.get("href")
    ]
    interesting = [
        href
        for href in hrefs
        if any(tok in href.lower() for tok in ("luma.com", "lu.ma", "coupon=", "eventbrite", "register"))
    ]
    href_blob = "\n".join(interesting)
    description = (page_text[:4000] + "\n" + href_blob).strip()
    luma = next((h for h in interesting if "luma.com" in h.lower() or "lu.ma" in h.lower()), None)
    if not events:
        title = title_hint or (soup.title.get_text(strip=True) if soup.title else url)
        events.append(
            RawEvent(
                source_id=source_id,
                source_type="html_page",
                source_url=url,
                title=title,
                description=description,
                organizer=organizer_hint,
                start_at=None,
                end_at=None,
                city=city_hint,
                location_mode=LocationMode.IN_PERSON,
                registration_url=luma or url,
                canonical_url=(luma.split("?")[0] if luma else url),
                fetched_at=fetched_at,
                raw={"jsonld": False},
            )
        )
    else:
        for ev in events:
            ev.description = ((ev.description or "") + "\n" + description).strip()
            if luma:
                ev.registration_url = luma
                ev.canonical_url = luma.split("?")[0]
    return events


class HtmlPageAdapter:
    source_type = "html_page"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.source_id = config["id"]

    def discover(self, ctx: FetchContext) -> SourceFetchResult:
        run = start_run(self.source_id, self.source_type, ctx.now)
        url = self.config.get("url")
        if not url:
            finish_run(run, events=[], error="missing url")
            return SourceFetchResult(run=run, events=[])
        try:
            html = ctx.fetcher.get_text(url)
            events = parse_html_event(
                html,
                source_id=self.source_id,
                url=url,
                fetched_at=ctx.now,
                title_hint=self.config.get("title_hint"),
                organizer_hint=self.config.get("organizer_hint"),
                city_hint=self.config.get("city_hint"),
            )
            finish_run(run, events=events)
            return SourceFetchResult(run=run, events=events)
        except FetchError as exc:
            finish_run(run, events=[], error=str(exc))
            return SourceFetchResult(run=run, events=[])
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=[], error=str(exc))
            return SourceFetchResult(run=run, events=[])
