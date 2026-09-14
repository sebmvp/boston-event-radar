"""End-to-end discover pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from event_radar.config import load_keywords, load_profile, load_series, load_sources
from event_radar.http_client import FetchError, HttpFetcher
from event_radar.models import (
    AccessRoute,
    AccessStatus,
    AccessType,
    EventRecord,
    Evidence,
    ObservationKind,
    OrganizerRecord,
    RecurringSeries,
    SourceRun,
)
from event_radar.processing.dedupe import deduplicate, merge_events
from event_radar.processing.filter import is_upcoming, topical_enough
from event_radar.processing.normalize import normalize
from event_radar.processing.score import score_event
from event_radar.processing.series import match_series
from event_radar.sources import build_adapter, enabled_sources
from event_radar.sources.base import FetchContext
from event_radar.sources.luma import fetch_luma_detail, luma_slug_from_url
from event_radar.storage import Store, organizer_id

KEEP_ALWAYS_TYPES = {"luma_event", "html_page", "newsletter", "luma_calendar"}


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


def _hydrate_luma_details(events: list[EventRecord], ctx: FetchContext, top_n: int) -> None:
    if top_n <= 0:
        return
    candidates: list[tuple[EventRecord, str]] = []
    for event in events:
        slug = event.extra.get("luma_slug") or luma_slug_from_url(event.registration_url or event.canonical_url)
        if not slug:
            continue
        has_types = any(
            ev.extracted_from == "luma_ticket_types" for route in event.access_routes for ev in route.evidence
        )
        if has_types:
            continue
        candidates.append((event, slug))
    seen: set[str] = set()
    hydrated = 0
    for event, slug in candidates:
        if slug in seen or hydrated >= top_n:
            break
        seen.add(slug)
        try:
            raw = fetch_luma_detail(ctx, slug, source_id=event.sources[0].source_id if event.sources else "luma_hydrate")
        except (FetchError, Exception):
            continue
        if raw is None:
            continue
        detailed = normalize(raw, now=ctx.now)
        merged = merge_events([event, detailed])
        event.access_routes = merged.access_routes
        event.standard_price = merged.standard_price
        event.lowest_known_price = merged.lowest_known_price
        event.sources = merged.sources
        if merged.description and (not event.description or len(merged.description) > len(event.description or "")):
            event.description = merged.description
        if merged.categories:
            event.categories = merged.categories
        hydrated += 1


def _record_organizers(store: Store, events: list[EventRecord], now: datetime) -> None:
    for event in events:
        cal_id = event.extra.get("calendar_api_id")
        name = event.extra.get("calendar_name") or event.organizer
        if not name and not cal_id:
            continue
        display = str(name or cal_id)
        oid = organizer_id(display, str(cal_id) if cal_id else None)
        store.upsert_organizer(
            OrganizerRecord(
                id=oid,
                name=display,
                kind="luma_calendar" if cal_id else "organizer",
                calendar_api_id=str(cal_id) if cal_id else None,
                urls=[event.canonical_url],
                discovered_from=event.sources[0].source_id if event.sources else None,
                first_seen_at=now,
                last_seen_at=now,
                event_count=1,
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
    source: str | None = None,
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
    for cfg in enabled_sources(sources_doc, only=source):
        adapter = build_adapter(cfg)
        result = adapter.discover(ctx)
        store.record_run(result.run)
        runs.append(result.run)
        always = cfg.get("type") in KEEP_ALWAYS_TYPES or not cfg.get("filter_by_keywords")
        for raw in result.events:
            record = normalize(raw, now=now)
            if not topical_enough(record, keywords, always_keep=always):
                continue
            title_l = record.title.lower()
            if any(tok in title_l for tok in ("climate week nyc", " houston", "chicago", "berkeley", "santa clara")):
                if not any(c in (record.city or "").lower() for c in ("boston", "cambridge", "somerville")):
                    continue
                if "nyc" in title_l or "new york" in title_l:
                    continue
            if record.start_at and not is_upcoming(record, now, grace_hours=24) and cfg.get("type") != "html_page":
                continue
            normalized.append(record)
    merged = deduplicate(normalized)
    _hydrate_luma_details(merged, ctx, int(discover_cfg.get("hydrate_luma_details_for_top_n") or 0))
    for event in merged:
        series = match_series(event, series_list)
        if series:
            event.series_id = series.id
            _attach_historical(event, series)
        event.score = score_event(event, profile, now=now)
    _record_organizers(store, merged, now)
    stored = store.upsert_events(merged)
    return stored, runs
