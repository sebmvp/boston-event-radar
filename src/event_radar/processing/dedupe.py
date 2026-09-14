"""Deterministic + fuzzy event deduplication. Provenance is unioned."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from html import unescape
from urllib.parse import urlparse

from rapidfuzz import fuzz

from event_radar.models import AccessRoute, EventRecord, ObservationKind, SourceRef

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_YEAR_RE = re.compile(r"\b20\d{2}\b")
_STOP = {
    "the",
    "a",
    "an",
    "and",
    "of",
    "at",
    "in",
    "for",
    "with",
    "on",
}


def normalize_title(title: str) -> str:
    text = title.lower()
    text = _YEAR_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    tokens = [tok for tok in text.split() if tok and tok not in _STOP]
    return " ".join(tokens)


def canonical_host_path(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower()
    return f"{host}{path}"


def same_event(a: EventRecord, b: EventRecord) -> bool:
    url_a = canonical_host_path(a.canonical_url)
    url_b = canonical_host_path(b.canonical_url)
    if url_a and url_a == url_b:
        return True
    if a.id == b.id:
        return True
    title_a = normalize_title(a.title)
    title_b = normalize_title(b.title)
    if not title_a or not title_b:
        return False
    ratio = fuzz.token_set_ratio(title_a, title_b)
    time_ok = _time_close(a.start_at, b.start_at)
    city_ok = _city_close(a.city, b.city)
    venue_ok = _venue_close(a.venue, b.venue)
    organizer_ok = _organizer_close(a.organizer, b.organizer)
    if ratio >= 92 and time_ok:
        return True
    if ratio >= 85 and time_ok and (venue_ok or organizer_ok or city_ok):
        return True
    if ratio >= 80 and time_ok and venue_ok and organizer_ok:
        return True
    return False


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def merge_events(group: list[EventRecord]) -> EventRecord:
    newest = max(group, key=lambda ev: _aware(ev.last_checked_at) or datetime.min.replace(tzinfo=UTC))
    primary = newest.model_copy(deep=True)
    primary.title = unescape(primary.title)
    if primary.description:
        primary.description = unescape(primary.description)
    sources: list[SourceRef] = []
    seen_sources: set[tuple[str, str]] = set()
    routes: list[AccessRoute] = []
    categories: list[str] = []
    for ev in group:
        for src in ev.sources:
            key = (src.source_id, src.source_url)
            if key not in seen_sources:
                seen_sources.add(key)
                sources.append(src)
        if ev is newest:
            routes.extend(ev.access_routes)
        else:
            ev_checked = _aware(ev.last_checked_at)
            new_checked = _aware(newest.last_checked_at)
            same_run = bool(ev_checked and new_checked and abs(ev_checked - new_checked) <= timedelta(minutes=2))
            for route in ev.access_routes:
                if route.observation_kind == ObservationKind.CONFIRMED_CURRENT:
                    routes.append(route)
                elif same_run:
                    routes.append(route)
                elif route.observation_kind == ObservationKind.HISTORICAL and newest.series_id:
                    routes.append(route)
        for cat in ev.categories:
            if cat not in categories:
                categories.append(cat)
        if ev.description and len(ev.description) > len(primary.description or ""):
            ev_checked = _aware(ev.last_checked_at)
            pri_checked = _aware(primary.last_checked_at)
            if ev_checked and pri_checked and ev_checked >= pri_checked - timedelta(minutes=2):
                primary.description = unescape(ev.description)
        if not primary.organizer and ev.organizer:
            primary.organizer = ev.organizer
        if not primary.venue and ev.venue:
            primary.venue = ev.venue
        if not primary.city and ev.city:
            primary.city = ev.city
        if not primary.address and ev.address:
            primary.address = ev.address
        if primary.latitude is None and ev.latitude is not None:
            primary.latitude = ev.latitude
            primary.longitude = ev.longitude
        if not primary.registration_url and ev.registration_url:
            primary.registration_url = ev.registration_url
        if ev.standard_price is not None:
            if primary.standard_price is None or ev.standard_price > primary.standard_price:
                primary.standard_price = ev.standard_price
        prices = [p for p in [primary.lowest_known_price, ev.lowest_known_price] if p is not None]
        primary.lowest_known_price = min(prices) if prices else None
        ev_start = _aware(ev.start_at)
        primary_start = _aware(primary.start_at)
        if ev_start and (primary_start is None or ev_start < primary_start):
            primary.start_at = ev_start
        ev_end = _aware(ev.end_at)
        primary_end = _aware(primary.end_at)
        if ev_end and (primary_end is None or ev_end > primary_end):
            primary.end_at = ev_end
        primary_checked = _aware(primary.last_checked_at)
        ev_checked = _aware(ev.last_checked_at)
        if primary_checked and ev_checked:
            primary.last_checked_at = max(primary_checked, ev_checked)
        elif ev_checked:
            primary.last_checked_at = ev_checked
        primary_disc = _aware(primary.discovered_at)
        ev_disc = _aware(ev.discovered_at)
        if primary_disc and ev_disc:
            primary.discovered_at = min(primary_disc, ev_disc)
        elif ev_disc:
            primary.discovered_at = ev_disc
    primary.series_id = newest.series_id
    if not newest.series_id:
        routes = [r for r in routes if r.observation_kind != ObservationKind.HISTORICAL]
    primary.sources = sources
    primary.categories = categories
    primary.access_routes = _merge_routes(routes)
    if primary.access_routes:
        priced = [r.price for r in primary.access_routes if r.price is not None]
        if priced:
            primary.lowest_known_price = min(priced)
    return primary


def deduplicate(events: list[EventRecord]) -> list[EventRecord]:
    clusters: list[list[EventRecord]] = []
    for event in events:
        placed = False
        for cluster in clusters:
            if any(same_event(event, existing) for existing in cluster):
                cluster.append(event)
                placed = True
                break
        if not placed:
            clusters.append([event])
    return [merge_events(cluster) if len(cluster) > 1 else cluster[0] for cluster in clusters]


def _merge_routes(routes: list[AccessRoute]) -> list[AccessRoute]:
    merged: dict[tuple[str, str | None, str], AccessRoute] = {}
    for route in routes:
        key = (route.type.value, route.coupon_code, route.observation_kind.value)
        existing = merged.get(key)
        if existing is None:
            merged[key] = route.model_copy(deep=True)
            continue
        if route.confidence > existing.confidence:
            keep = route.model_copy(deep=True)
            keep.evidence = existing.evidence + route.evidence
            if keep.price is None:
                keep.price = existing.price
            merged[key] = keep
        else:
            existing.evidence.extend(route.evidence)
            if existing.price is None:
                existing.price = route.price
    return list(merged.values())


def _time_close(a: datetime | None, b: datetime | None, hours: int = 6) -> bool:
    a = _aware(a)
    b = _aware(b)
    if a is None or b is None:
        return False
    return abs(a - b) <= timedelta(hours=hours)


def _city_close(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    return a.lower().split(",")[0].strip() == b.lower().split(",")[0].strip()


def _venue_close(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return fuzz.token_set_ratio(a.lower(), b.lower()) >= 85


def _organizer_close(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return fuzz.token_set_ratio(a.lower(), b.lower()) >= 85
