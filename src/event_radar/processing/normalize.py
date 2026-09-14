"""Normalize raw source events into EventRecord shells (pre-dedupe)."""

from __future__ import annotations

from datetime import UTC, datetime
from html import unescape

from event_radar.models import EventRecord, RawEvent, SourceRef, event_id_for
from event_radar.processing.access import extract_access


def normalize(raw: RawEvent, now: datetime | None = None) -> EventRecord:
    now = now or datetime.now(UTC)
    start = raw.start_at
    if start and start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    end = raw.end_at
    if end and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    title = unescape(raw.title.strip())
    description = unescape(raw.description) if raw.description else None
    canonical = raw.canonical_url or raw.source_url
    record = EventRecord(
        id=event_id_for(title, start, raw.city),
        title=title,
        description=description,
        organizer=raw.organizer,
        sources=[
            SourceRef(
                source_id=raw.source_id,
                source_type=raw.source_type,
                source_url=raw.source_url,
                external_id=raw.external_id,
                fetched_at=raw.fetched_at,
                raw_excerpt=(raw.description or "")[:240] or None,
            )
        ],
        source_url=raw.source_url,
        canonical_url=canonical,
        discovered_at=now,
        last_checked_at=now,
        last_verified_at=now,
        start_at=start,
        end_at=end,
        timezone=raw.timezone,
        venue=raw.venue,
        city=raw.city,
        address=raw.address,
        location_mode=raw.location_mode,
        latitude=raw.latitude,
        longitude=raw.longitude,
        categories=list(raw.categories or raw.tags),
        registration_url=raw.registration_url or canonical,
        registration_state=_registration_state(raw),
        standard_price=_standard_price(raw),
        lowest_known_price=_lowest_price(raw),
        access_routes=extract_access(raw, now=now),
        extra={
            "source_type": raw.source_type,
            "calendar_api_id": (raw.raw or {}).get("calendar_api_id"),
            "calendar_name": (raw.raw or {}).get("calendar_name"),
            "luma_slug": (raw.raw or {}).get("slug"),
            "related_pages": (raw.raw or {}).get("related_pages") or [],
        },
    )
    record.lowest_known_price = _lowest_from_routes(record)
    return record


def _registration_state(raw: RawEvent) -> str | None:
    if raw.sold_out:
        return "sold_out"
    if raw.waitlist:
        return "waitlist"
    if raw.require_approval:
        return "approval_required"
    if raw.is_free:
        return "free"
    if raw.price is not None:
        return "paid"
    return None


def _standard_price(raw: RawEvent) -> float | None:
    for ticket in raw.ticket_types:
        name = str(ticket.get("name") or "").lower()
        if "standard" in name or "general" in name:
            cents = ticket.get("cents")
            if isinstance(cents, int):
                return cents / 100.0
    if raw.price is not None:
        return raw.price
    return 0.0 if raw.is_free else None


def _lowest_price(raw: RawEvent) -> float | None:
    prices: list[float] = []
    if raw.is_free:
        prices.append(0.0)
    if raw.price is not None:
        prices.append(raw.price)
    for ticket in raw.ticket_types:
        cents = ticket.get("cents")
        if isinstance(cents, int):
            prices.append(cents / 100.0)
    return min(prices) if prices else None


def _lowest_from_routes(record: EventRecord) -> float | None:
    prices = [r.price for r in record.access_routes if r.price is not None]
    if record.lowest_known_price is not None:
        prices.append(record.lowest_known_price)
    return min(prices) if prices else record.lowest_known_price
