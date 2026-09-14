from __future__ import annotations

from typing import Any

from event_radar.sources.base import SourceAdapter
from event_radar.sources.html_page import HtmlPageAdapter
from event_radar.sources.ics import IcsAdapter
from event_radar.sources.localist import LocalistAdapter
from event_radar.sources.luma import LumaCalendarAdapter, LumaDiscoverAdapter, LumaEventAdapter
from event_radar.sources.newsletter import NewsletterAdapter
from event_radar.sources.rss import RssAdapter
from event_radar.sources.tribe import TribeEventsAdapter

ADAPTERS: dict[str, type] = {
    "luma_discover": LumaDiscoverAdapter,
    "luma_event": LumaEventAdapter,
    "luma_calendar": LumaCalendarAdapter,
    "localist": LocalistAdapter,
    "ics": IcsAdapter,
    "html_page": HtmlPageAdapter,
    "newsletter": NewsletterAdapter,
    "rss": RssAdapter,
    "tribe": TribeEventsAdapter,
}


def build_adapter(config: dict[str, Any]) -> SourceAdapter:
    kind = str(config.get("type") or "")
    cls = ADAPTERS.get(kind)
    if cls is None:
        raise ValueError(f"Unknown source type: {kind}")
    return cls(config)  # type: ignore[call-arg]


def enabled_sources(sources_doc: dict[str, Any], *, only: str | None = None) -> list[dict[str, Any]]:
    rows = [s for s in sources_doc.get("sources") or [] if s.get("enabled")]
    if not only:
        return rows
    needle = only.lower()
    return [
        s
        for s in rows
        if needle in str(s.get("id", "")).lower()
        or needle in str(s.get("type", "")).lower()
        or needle in str(s.get("org", "")).lower()
    ]
