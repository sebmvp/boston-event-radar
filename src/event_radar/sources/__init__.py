from __future__ import annotations

from typing import Any

from event_radar.sources.base import SourceAdapter
from event_radar.sources.html_page import HtmlPageAdapter
from event_radar.sources.ics import IcsAdapter
from event_radar.sources.localist import LocalistAdapter
from event_radar.sources.luma import LumaDiscoverAdapter, LumaEventAdapter
from event_radar.sources.newsletter import NewsletterAdapter

ADAPTERS: dict[str, type] = {
    "luma_discover": LumaDiscoverAdapter,
    "luma_event": LumaEventAdapter,
    "localist": LocalistAdapter,
    "ics": IcsAdapter,
    "html_page": HtmlPageAdapter,
    "newsletter": NewsletterAdapter,
}


def build_adapter(config: dict[str, Any]) -> SourceAdapter:
    kind = config.get("type")
    cls = ADAPTERS.get(kind)
    if cls is None:
        raise ValueError(f"Unknown source type: {kind}")
    return cls(config)  # type: ignore[call-arg]


def enabled_sources(sources_doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in sources_doc.get("sources") or [] if s.get("enabled")]
