"""Public RSS / Atom adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

from event_radar.http_client import FetchError
from event_radar.models import LocationMode, RawEvent
from event_radar.sources.base import FetchContext, SourceFetchResult, finish_run, start_run


def _text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _child(node: ET.Element, *names: str) -> ET.Element | None:
    for name in names:
        found = node.find(name)
        if found is not None:
            return found
        if "}" not in name:
            for child in list(node):
                if child.tag.endswith("}" + name) or child.tag == name:
                    return child
    return None


def _parse_feed_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def raw_from_rss_item(
    item: ET.Element,
    *,
    source_id: str,
    fetched_at: datetime,
    org: str | None,
    source_url: str,
) -> RawEvent | None:
    title = _text(_child(item, "title", "{http://www.w3.org/2005/Atom}title"))
    if not title:
        return None
    link_el = _child(item, "link", "{http://www.w3.org/2005/Atom}link")
    url = _text(link_el)
    if not url and link_el is not None:
        url = (link_el.get("href") or "").strip()
    guid = _text(_child(item, "guid", "id", "{http://www.w3.org/2005/Atom}id"))
    desc = _text(
        _child(
            item,
            "description",
            "{http://purl.org/rss/1.0/modules/content/}encoded",
            "{http://www.w3.org/2005/Atom}summary",
            "{http://www.w3.org/2005/Atom}content",
        )
    )
    start = _parse_feed_dt(
        _text(_child(item, "pubDate", "published", "{http://www.w3.org/2005/Atom}published", "updated"))
    )
    return RawEvent(
        source_id=source_id,
        source_type="rss",
        external_id=guid or None,
        source_url=url or source_url,
        title=title,
        description=desc or None,
        organizer=org,
        start_at=start,
        location_mode=LocationMode.UNKNOWN,
        registration_url=url or source_url,
        canonical_url=url or source_url,
        fetched_at=fetched_at,
        raw={"guid": guid},
    )


def parse_feed(xml_text: str, *, source_id: str, fetched_at: datetime, org: str | None, source_url: str) -> list[RawEvent]:
    root = ET.fromstring(xml_text)
    items = list(root.findall(".//item"))
    if not items:
        items = list(root.findall(".//{http://www.w3.org/2005/Atom}entry"))
    events: list[RawEvent] = []
    for item in items:
        raw = raw_from_rss_item(item, source_id=source_id, fetched_at=fetched_at, org=org, source_url=source_url)
        if raw:
            events.append(raw)
    return events


class RssAdapter:
    source_type = "rss"

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
            text = ctx.fetcher.get_text(url)
            events = parse_feed(
                text,
                source_id=self.source_id,
                fetched_at=ctx.now,
                org=self.config.get("org"),
                source_url=url,
            )
            finish_run(run, events=events)
            return SourceFetchResult(run=run, events=events)
        except FetchError as exc:
            finish_run(run, events=[], error=str(exc))
            return SourceFetchResult(run=run, events=[])
        except Exception as exc:  # noqa: BLE001
            finish_run(run, events=[], error=str(exc))
            return SourceFetchResult(run=run, events=[])
