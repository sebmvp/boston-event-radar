"""Deterministic access-route extraction from structured fields and text."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from event_radar.models import (
    AccessRoute,
    AccessStatus,
    AccessType,
    Evidence,
    ObservationKind,
    RawEvent,
)

_STUDENT_RE = re.compile(r"\bstudent(?:s)?\s+(ticket|pass|discount|rate|admission|pricing)\b", re.I)
_STUDENT_ID_RE = re.compile(r"student id|current undergraduate or graduate student", re.I)
_VOLUNTEER_RE = re.compile(r"\bvolunteer(?:ing|s)?\b.{0,40}\b(apply|application|sign[- ]up|opportunity|call)\b|\b(apply|application).{0,40}\bvolunteer", re.I)
_VOLUNTEER_WEAK_RE = re.compile(r"\bvolunteer(?:ing)?\b", re.I)
_FREE_RE = re.compile(r"\b(free admission|free event|no cost|complimentary|free to attend|free ticket)\b", re.I)
_EARLY_RE = re.compile(r"\bearly[ -]?bird\b", re.I)
_WAITLIST_RE = re.compile(r"\bwaitlist\b", re.I)
_APPLY_RE = re.compile(r"\b(apply|application required|request to join|request-to-join|approval required)\b", re.I)
_FOUNDER_RE = re.compile(r"\b(founder ticket|founder pass|early-stage (fintech )?entrepreneur)", re.I)
_SCHOLARSHIP_RE = re.compile(r"\bscholarship\b", re.I)
_HACKATHON_RE = re.compile(r"\bhackathon\b", re.I)
_COUPON_RE = re.compile(r"[?&]coupon=([A-Z0-9_-]+)", re.I)
_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PRICE_RE = re.compile(r"\$(\d[\d,]*(?:\.\d{2})?)")


def extract_access(raw: RawEvent, now: datetime | None = None) -> list[AccessRoute]:
    now = now or datetime.now(UTC)
    blob = " ".join(
        part for part in [raw.title, raw.description or "", raw.source_url, raw.canonical_url or ""] if part
    )
    routes: list[AccessRoute] = []

    routes.extend(_from_ticket_types(raw, now))
    routes.extend(_from_structured_flags(raw, blob))
    routes.extend(_from_text(raw, blob))
    routes.extend(_from_coupons(raw, blob))

    return _dedupe_routes(routes)


def _from_ticket_types(raw: RawEvent, now: datetime) -> list[AccessRoute]:
    routes: list[AccessRoute] = []
    for ticket in raw.ticket_types:
        name = str(ticket.get("name") or "Ticket")
        cents = ticket.get("cents")
        price = (cents / 100.0) if isinstance(cents, int) else ticket.get("price")
        end_raw = ticket.get("valid_end_at")
        start_raw = ticket.get("valid_start_at")
        end_at = _parse_dt(end_raw)
        start_at = _parse_dt(start_raw)
        disabled = bool(ticket.get("is_disabled"))
        hidden = bool(ticket.get("is_hidden"))
        approval = bool(ticket.get("require_approval"))
        sold = bool(ticket.get("is_sold_out")) or (
            ticket.get("spots_remaining") == 0
        )
        status = AccessStatus.OPEN
        if sold:
            status = AccessStatus.SOLD_OUT
        elif disabled or (end_at and end_at < now) or (start_at and start_at > now and disabled):
            status = AccessStatus.CLOSED
        elif end_at and end_at < now:
            status = AccessStatus.CLOSED
        elif approval:
            status = AccessStatus.APPROVAL_REQUIRED
        access_type = _type_from_ticket_name(name, price)
        evidence = Evidence(
            field="ticket_type",
            text=f"{name} price={price} valid_end={end_raw}",
            source_url=raw.source_url,
            extracted_from="luma_ticket_types",
            confidence=0.95,
        )
        routes.append(
            AccessRoute(
                type=access_type,
                price=float(price) if price is not None else None,
                status=status,
                eligibility=name,
                deadline=end_at,
                application_url=raw.registration_url or raw.canonical_url or raw.source_url,
                evidence=[evidence],
                confidence=0.95 if not hidden else 0.7,
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
                notes="hidden ticket type" if hidden else None,
            )
        )
    return routes


def _from_structured_flags(raw: RawEvent, blob: str) -> list[AccessRoute]:
    routes: list[AccessRoute] = []
    url = raw.registration_url or raw.canonical_url or raw.source_url
    if raw.is_free and not raw.ticket_types:
        status = AccessStatus.APPROVAL_REQUIRED if raw.require_approval else AccessStatus.OPEN
        if raw.sold_out:
            status = AccessStatus.SOLD_OUT
        routes.append(
            AccessRoute(
                type=AccessType.FREE_ADMISSION,
                price=0.0,
                status=status,
                application_url=url,
                evidence=[
                    Evidence(
                        field="is_free",
                        text="source flagged is_free=true",
                        source_url=raw.source_url,
                        extracted_from="structured",
                        confidence=0.9,
                    )
                ],
                confidence=0.9,
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
            )
        )
    elif raw.price is not None and not raw.ticket_types:
        status = AccessStatus.APPROVAL_REQUIRED if raw.require_approval else AccessStatus.OPEN
        routes.append(
            AccessRoute(
                type=AccessType.STANDARD_TICKET,
                price=raw.price,
                status=status,
                application_url=url,
                evidence=[
                    Evidence(
                        field="price",
                        text=f"structured price={raw.price}",
                        source_url=raw.source_url,
                        extracted_from="structured",
                        confidence=0.85,
                    )
                ],
                confidence=0.85,
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
            )
        )
    if raw.require_approval and not any(r.status == AccessStatus.APPROVAL_REQUIRED for r in routes):
        routes.append(
            AccessRoute(
                type=AccessType.INVITE_REQUEST,
                price=raw.price if raw.price is not None else (0.0 if raw.is_free else None),
                status=AccessStatus.APPROVAL_REQUIRED,
                application_url=url,
                evidence=[
                    Evidence(
                        field="require_approval",
                        text="source flagged require_approval=true",
                        source_url=raw.source_url,
                        extracted_from="structured",
                        confidence=0.9,
                    )
                ],
                confidence=0.9,
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
            )
        )
    if raw.waitlist:
        routes.append(
            AccessRoute(
                type=AccessType.WAITLIST,
                status=AccessStatus.WAITLIST,
                application_url=url,
                evidence=[
                    Evidence(
                        field="waitlist",
                        text="source flagged waitlist",
                        source_url=raw.source_url,
                        extracted_from="structured",
                        confidence=0.9,
                    )
                ],
                confidence=0.9,
                observation_kind=ObservationKind.CONFIRMED_CURRENT,
            )
        )
    return routes


def _from_text(raw: RawEvent, blob: str) -> list[AccessRoute]:
    routes: list[AccessRoute] = []
    url = raw.registration_url or raw.canonical_url or raw.source_url
    emails = _EMAIL_RE.findall(blob)

    def add(access_type: AccessType, *, text: str, confidence: float, status: AccessStatus = AccessStatus.UNKNOWN, extra: dict[str, Any] | None = None) -> None:
        extra = extra or {}
        routes.append(
            AccessRoute(
                type=access_type,
                price=extra.get("price"),
                status=status,
                eligibility=extra.get("eligibility"),
                application_url=url,
                contact_email=emails[0] if emails else None,
                evidence=[
                    Evidence(
                        field="description",
                        text=text[:280],
                        source_url=raw.source_url,
                        extracted_from="text",
                        confidence=confidence,
                    )
                ],
                confidence=confidence,
                observation_kind=ObservationKind.INFERRED
                if confidence < 0.8
                else ObservationKind.CONFIRMED_CURRENT,
                coupon_code=extra.get("coupon"),
                notes=extra.get("notes"),
            )
        )

    if _STUDENT_RE.search(blob) or _STUDENT_ID_RE.search(blob):
        snippet = _snippet(blob, "student")
        add(
            AccessType.STUDENT_TICKET,
            text=snippet,
            confidence=0.82 if _STUDENT_ID_RE.search(blob) else 0.7,
            status=AccessStatus.UNCERTAIN,
            extra={"eligibility": "Current undergraduate or graduate student" if _STUDENT_ID_RE.search(blob) else "Student"},
        )
    if _VOLUNTEER_RE.search(blob):
        add(AccessType.VOLUNTEER, text=_snippet(blob, "volunteer"), confidence=0.75, status=AccessStatus.UNKNOWN)
    elif _VOLUNTEER_WEAK_RE.search(blob) and "last year" not in blob.lower():
        add(
            AccessType.VOLUNTEER,
            text=_snippet(blob, "volunteer"),
            confidence=0.45,
            status=AccessStatus.UNCERTAIN,
            extra={"notes": "weak volunteer mention; not treated as a confirmed open program"},
        )
    if _FREE_RE.search(blob) and raw.is_free is not False:
        add(AccessType.FREE_ADMISSION, text=_snippet(blob, "free"), confidence=0.65, status=AccessStatus.UNKNOWN, extra={"price": 0.0})
    if _EARLY_RE.search(blob):
        price = _nearby_price(blob, "early")
        add(AccessType.EARLY_BIRD, text=_snippet(blob, "early"), confidence=0.6, extra={"price": price})
    if _WAITLIST_RE.search(blob) and not raw.waitlist:
        add(AccessType.WAITLIST, text=_snippet(blob, "waitlist"), confidence=0.6, status=AccessStatus.WAITLIST)
    if _APPLY_RE.search(blob) and not raw.require_approval:
        add(AccessType.INVITE_REQUEST, text=_snippet(blob, "apply"), confidence=0.55, status=AccessStatus.APPROVAL_REQUIRED)
    if _FOUNDER_RE.search(blob):
        add(
            AccessType.FOUNDER_TICKET,
            text=_snippet(blob, "founder") or _snippet(blob, "entrepreneur"),
            confidence=0.7,
            status=AccessStatus.APPROVAL_REQUIRED,
            extra={"eligibility": "Eligible early-stage founder / entrepreneur"},
        )
    if _SCHOLARSHIP_RE.search(blob):
        add(AccessType.SCHOLARSHIP, text=_snippet(blob, "scholarship"), confidence=0.6)
    if _HACKATHON_RE.search(raw.title) or (_HACKATHON_RE.search(blob) and "participant" in blob.lower()):
        add(
            AccessType.HACKATHON_PARTICIPANT,
            text=_snippet(blob, "hackathon") or raw.title,
            confidence=0.7,
            extra={"price": 0.0 if raw.is_free else raw.price},
        )
    return routes


def _from_coupons(raw: RawEvent, blob: str) -> list[AccessRoute]:
    routes: list[AccessRoute] = []
    urls = [raw.source_url, raw.canonical_url or "", raw.registration_url or "", blob]
    for text in urls:
        for match in _COUPON_RE.finditer(text):
            code = match.group(1).upper()
            access_type = AccessType.UNKNOWN
            eligibility = f"Coupon {code}"
            if "STUDENT" in code:
                access_type = AccessType.STUDENT_TICKET
                eligibility = "Student coupon"
            elif "FOUNDER" in code:
                access_type = AccessType.FOUNDER_TICKET
                eligibility = "Founder coupon"
            routes.append(
                AccessRoute(
                    type=access_type,
                    status=AccessStatus.UNCERTAIN,
                    eligibility=eligibility,
                    application_url=raw.registration_url or raw.canonical_url or raw.source_url,
                    evidence=[
                        Evidence(
                            field="coupon",
                            text=match.group(0),
                            source_url=raw.source_url,
                            extracted_from="url",
                            confidence=0.8,
                        )
                    ],
                    confidence=0.8,
                    observation_kind=ObservationKind.CONFIRMED_CURRENT,
                    coupon_code=code,
                    notes="Coupon present on a public page; availability still needs a live registration check",
                )
            )
    return routes


def _type_from_ticket_name(name: str, price: float | None) -> AccessType:
    lower = name.lower()
    if "early" in lower:
        return AccessType.EARLY_BIRD
    if "student" in lower:
        return AccessType.STUDENT_TICKET
    if "volunteer" in lower:
        return AccessType.VOLUNTEER
    if "founder" in lower:
        return AccessType.FOUNDER_TICKET
    if "waitlist" in lower:
        return AccessType.WAITLIST
    if price == 0 or (price is None and "free" in lower):
        return AccessType.FREE_ADMISSION
    if "standard" in lower or "general" in lower or "ga " in lower:
        return AccessType.STANDARD_TICKET
    return AccessType.STANDARD_TICKET


def _dedupe_routes(routes: list[AccessRoute]) -> list[AccessRoute]:
    merged: dict[tuple[str, str | None, str], AccessRoute] = {}
    for route in routes:
        key = (route.type.value, route.coupon_code, route.observation_kind.value)
        existing = merged.get(key)
        if existing is None:
            merged[key] = route
            continue
        if route.confidence > existing.confidence:
            route.evidence = existing.evidence + route.evidence
            merged[key] = route
        else:
            existing.evidence.extend(route.evidence)
            if existing.price is None:
                existing.price = route.price
            if existing.status == AccessStatus.UNKNOWN:
                existing.status = route.status
    return list(merged.values())


def _snippet(blob: str, needle: str, width: int = 140) -> str:
    idx = blob.lower().find(needle.lower())
    if idx < 0:
        return blob[:width]
    start = max(0, idx - 40)
    return blob[start : idx + width]


def _nearby_price(blob: str, needle: str) -> float | None:
    idx = blob.lower().find(needle.lower())
    window = blob[max(0, idx - 80) : idx + 80]
    match = _PRICE_RE.search(window)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
