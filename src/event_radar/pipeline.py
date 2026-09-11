"""End-to-end discover pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from event_radar.config import load_keywords, load_profile, load_series, load_sources
from event_radar.http_client import HttpFetcher
from event_radar.models import (
    AccessRoute,
    AccessStatus,
    AccessType,
    EventRecord,
    Evidence,
    ObservationKind,
    RecurringSeries,
    SourceRun,
)
from event_radar.processing.dedupe import deduplicate
from event_radar.processing.filter import topical_enough
from event_radar.processing.normalize import normalize
from event_radar.processing.score import score_event
from event_radar.processing.series import match_series
from event_radar.sources import build_adapter, enabled_sources
from event_radar.sources.base import FetchContext
from event_radar.storage import Store

KEEP_ALWAYS_TYPES = {"luma_event", "html_page", "newsletter"}


def _series_models(doc: dict[str, Any]) -> list[RecurringSeries]:
    out: list[RecurringSeries] = []
    for item in doc.get("series") or []:
        out.append(RecurringSeries.model_validate(item))
    return out


def _attach_historical(event: EventRecord, series: RecurringSeries) -> None:
    hist = series.historical or {}
    notes = (
        f"Historical evidence from series '{series.name}'. "
        "This is not confirmation the route is open this year."
    )
    mapping = {
        "student_tickets": AccessType.STUDENT_TICKET,
        "volunteer": AccessType.VOLUNTEER,
        "founder_tickets": AccessType.FOUNDER_TICKET,
        "early_bird": AccessType.EARLY_BIRD,
    }
    existing = {(r.type, r.observation_kind) for r in event.access_routes}
    for key, access_type in mapping.items():
        value = hist.get(key)
        if value is True and (access_type, ObservationKind.HISTORICAL) not in existing:
            event.access_routes.append(
                AccessRoute(
                    type=access_type,
                    status=AccessStatus.UNKNOWN,
                    observation_kind=ObservationKind.HISTORICAL,
                    confidence=0.4,
                    notes=notes,
                    evidence=[
                        Evidence(
                            field="series_history",
                            text=f"{key}=true on series {series.id}",
                            extracted_from="series_config",
                            confidence=0.4,
                        )
                    ],
                )
            )


def run_discover(
    *,
    store: Store | None = None,
    sources_doc: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    keywords: dict[str, Any] | None = None,
    series_doc: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> tuple[list[EventRecord], list[SourceRun]]:
    now = now or datetime.now(UTC)
    sources_doc = sources_doc or load_sources()
    profile = profile or load_profile()
    keywords = keywords or load_keywords()
    series_list = _series_models(series_doc or load_series())
    store = store or Store()
    http_cfg = sources_doc.get("http") or {}
    discover_cfg = sources_doc.get("discover") or {}
    fetcher = HttpFetcher(
        user_agent=http_cfg.get("user_agent", "BostonEventRadar/0.1"),
        timeout_sec=float(http_cfg.get("timeout_sec", 25)),
        retries=int(http_cfg.get("retries", 3)),
        per_host_delay_sec=float(http_cfg.get("per_host_delay_sec", 1.2)),
        cache_ttl_sec=int(http_cfg.get("cache_ttl_sec", 3600)),
    )
    ctx = FetchContext(
        fetcher=fetcher,
        now=now,
        lookahead_days=int(discover_cfg.get("lookahead_days", 75)),
        extra=discover_cfg,
    )
    runs: list[SourceRun] = []
    normalized: list[EventRecord] = []
    for cfg in enabled_sources(sources_doc):
        adapter = build_adapter(cfg)
        result = adapter.discover(ctx)
        store.record_run(result.run)
        runs.append(result.run)
        always = cfg.get("type") in KEEP_ALWAYS_TYPES or not cfg.get("filter_by_keywords")
        for raw in result.events:
            record = normalize(raw, now=now)
            if not topical_enough(record, keywords, always_keep=always):
                continue
            normalized.append(record)
    merged = deduplicate(normalized)
    for event in merged:
        series = match_series(event, series_list)
        if series:
            event.series_id = series.id
            _attach_historical(event, series)
        event.score = score_event(event, profile, now=now)
    store.upsert_events(merged)
    return merged, runs
