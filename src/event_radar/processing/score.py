"""Deterministic scoring with a transparent explanation."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from event_radar.models import (
    AccessStatus,
    AccessType,
    EventRecord,
    ObservationKind,
    ScoreBreakdown,
)
from event_radar.processing.text import has_term

EARTH_KM = 6371.0

LOW_SIGNAL = (
    "nightlife",
    "comedy",
    "open mic",
    "dating",
    "club night",
    "rave",
    "pilates",
    "yoga",
    "happy hour",
    "party",
    "concert",
    "sports vs",
    "tennis vs",
    "field hockey",
    "red sox",
)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def score_event(event: EventRecord, profile: dict[str, Any], now: datetime | None = None) -> ScoreBreakdown:
    now = now or datetime.now(UTC)
    weights = profile.get("scoring", {}).get("weights", {})
    reasons: list[str] = []
    penalties: list[str] = []
    blob = " ".join(
        [
            event.title,
            event.description or "",
            event.organizer or "",
            " ".join(event.categories),
        ]
    ).lower()

    topic = _topic_score(blob, profile, reasons, penalties)
    professional = _professional_score(blob, event, reasons, penalties)
    affordability = _affordability_score(event, reasons)
    student = _student_volunteer_score(event, profile, reasons)
    organizer = _organizer_score(event, profile, reasons)
    urgency = _urgency_score(event, now, reasons)
    travel = _travel_score(event, profile, reasons, penalties)
    uniqueness = _uniqueness_score(event, reasons)
    confidence = _confidence_score(event, reasons)

    parts = {
        "topic_relevance": (topic, weights.get("topic_relevance", 25)),
        "professional_value": (professional, weights.get("professional_value", 20)),
        "access_affordability": (affordability, weights.get("access_affordability", 15)),
        "student_volunteer": (student, weights.get("student_volunteer", 10)),
        "organizer_quality": (organizer, weights.get("organizer_quality", 8)),
        "scarcity_urgency": (urgency, weights.get("scarcity_urgency", 8)),
        "travel": (travel, weights.get("travel", 7)),
        "uniqueness": (uniqueness, weights.get("uniqueness", 4)),
        "confidence": (confidence, weights.get("confidence", 3)),
    }
    total = 0
    scaled: dict[str, int] = {}
    weight_sum = sum(w for _, w in parts.values()) or 1
    for name, (value, weight) in parts.items():
        scaled[name] = int(round(value * 100))
        total += value * weight
    total_int = int(round(100 * total / weight_sum))
    total_int = max(0, min(100, total_int))
    return ScoreBreakdown(
        total=total_int,
        topic_relevance=scaled["topic_relevance"],
        professional_value=scaled["professional_value"],
        access_affordability=scaled["access_affordability"],
        student_volunteer=scaled["student_volunteer"],
        organizer_quality=scaled["organizer_quality"],
        scarcity_urgency=scaled["scarcity_urgency"],
        travel=scaled["travel"],
        uniqueness=scaled["uniqueness"],
        confidence=scaled["confidence"],
        reasons=reasons,
        penalties=penalties,
    )


def _topic_score(blob: str, profile: dict[str, Any], reasons: list[str], penalties: list[str]) -> float:
    highs = [k.lower() for k in profile.get("priorities", {}).get("high", [])]
    hits = [kw for kw in highs if has_term(blob, kw)]
    score = min(1.0, 0.22 * len(hits))
    if hits:
        reasons.append("topics: " + ", ".join(hits[:6]))
    for bad in LOW_SIGNAL:
        if bad in blob and not hits:
            penalties.append(f"low-signal topic: {bad}")
            return 0.05
        if bad in blob:
            penalties.append(f"mixed with {bad}")
            score *= 0.7
    return score


def _professional_score(blob: str, event: EventRecord, reasons: list[str], penalties: list[str]) -> float:
    types_high = [
        "conference",
        "tech week",
        "hackathon",
        "mixer",
        "demo",
        "showcase",
        "workshop",
        "panel",
        "career",
        "networking",
        "forum",
        "summit",
        "pitch",
    ]
    hits = [t for t in types_high if t in blob or t in event.title.lower()]
    score = 0.25
    if hits:
        score = min(1.0, 0.3 + 0.15 * len(hits))
        reasons.append("event type: " + ", ".join(hits[:4]))
    if "networking" in blob or "mixer" in blob:
        score = min(1.0, score + 0.1)
    if any(bad in blob for bad in ("vs.", "vs ", "athletics", "intramural")):
        penalties.append("looks like athletics")
        score = min(score, 0.15)
    return score


def _affordability_score(event: EventRecord, reasons: list[str]) -> float:
    current = [
        r
        for r in event.access_routes
        if r.observation_kind == ObservationKind.CONFIRMED_CURRENT
        and r.status not in {AccessStatus.CLOSED, AccessStatus.SOLD_OUT}
    ]
    prices = [r.price for r in current if r.price is not None]
    if any(r.type == AccessType.FREE_ADMISSION and r.price == 0 for r in current):
        reasons.append("confirmed free admission")
        return 1.0
    if any(r.type in {AccessType.STUDENT_TICKET, AccessType.VOLUNTEER, AccessType.SCHOLARSHIP} for r in current):
        reasons.append("cheap/student/volunteer route present")
        return 0.9
    if any(r.type in {AccessType.STUDENT_TICKET, AccessType.FOUNDER_TICKET} for r in event.access_routes):
        reasons.append("student/founder route found (check status)")
        return 0.75
    if prices:
        lowest = min(prices)
        reasons.append(f"lowest confirmed price ${lowest:.0f}")
        if lowest <= 0:
            return 1.0
        if lowest <= 25:
            return 0.8
        if lowest <= 100:
            return 0.45
        if lowest <= 300:
            return 0.2
        return 0.05
    if event.lowest_known_price == 0:
        return 0.7
    return 0.35


def _student_volunteer_score(event: EventRecord, profile: dict[str, Any], reasons: list[str]) -> float:
    if not profile.get("student"):
        return 0.3
    types = {r.type for r in event.access_routes if r.observation_kind != ObservationKind.HISTORICAL}
    score = 0.2
    if AccessType.STUDENT_TICKET in types or AccessType.STUDENT_DISCOUNT in types:
        reasons.append("student ticket/discount signal")
        score = 0.9
    if AccessType.VOLUNTEER in types:
        reasons.append("volunteer signal")
        score = max(score, 0.85)
    if AccessType.UNIVERSITY_AFFILIATION in types:
        score = max(score, 0.7)
    if AccessType.HACKATHON_PARTICIPANT in types:
        score = max(score, 0.8)
    return score


def _organizer_score(event: EventRecord, profile: dict[str, Any], reasons: list[str]) -> float:
    boosts = [o.lower() for o in profile.get("organizer_boosts", [])]
    org = (event.organizer or "").lower()
    title = event.title.lower()
    for boost in boosts:
        if boost in org or boost in title:
            reasons.append(f"organizer/brand: {boost}")
            return 0.95
    if event.organizer:
        return 0.45
    return 0.25


def _urgency_score(event: EventRecord, now: datetime, reasons: list[str]) -> float:
    score = 0.3
    for route in event.access_routes:
        if route.observation_kind == ObservationKind.HISTORICAL:
            continue
        if route.status == AccessStatus.SOLD_OUT:
            continue
        if route.type in {AccessType.STUDENT_TICKET, AccessType.EARLY_BIRD, AccessType.VOLUNTEER}:
            score = max(score, 0.7)
        if route.status == AccessStatus.UNCERTAIN and route.type == AccessType.STUDENT_TICKET:
            reasons.append("student route may close; verify now")
            score = max(score, 0.8)
        if route.deadline:
            hours = (route.deadline - now).total_seconds() / 3600
            if 0 < hours < 72:
                reasons.append("deadline within 72h")
                score = max(score, 0.95)
            elif 0 < hours < 14 * 24:
                score = max(score, 0.7)
    if event.start_at:
        days = (event.start_at - now).total_seconds() / 86400
        if 0 <= days <= 7:
            reasons.append("happens within a week")
            score = max(score, 0.65)
        elif 0 <= days <= 21:
            score = max(score, 0.5)
    return min(1.0, score)


def _travel_score(event: EventRecord, profile: dict[str, Any], reasons: list[str], penalties: list[str]) -> float:
    geo = profile.get("target_geo", {})
    preferred = [c.lower() for c in geo.get("preferred_cities", [])]
    city = (event.city or "").lower()
    if event.location_mode.value == "virtual":
        reasons.append("virtual")
        return 0.85
    if city and any(city.startswith(p) for p in preferred):
        reasons.append(f"city: {event.city}")
        return 1.0
    lat0, lon0 = geo.get("latitude"), geo.get("longitude")
    if event.latitude is not None and event.longitude is not None and lat0 and lon0:
        km = haversine_km(float(lat0), float(lon0), event.latitude, event.longitude)
        max_km = float(geo.get("max_km") or 35)
        if km <= max_km:
            reasons.append(f"~{km:.0f} km from Boston center")
            return max(0.4, 1.0 - km / (max_km * 1.5))
        penalties.append(f"{km:.0f} km away")
        return 0.15
    if geo.get("amherst_penalty") and city.startswith("amherst"):
        penalties.append("Amherst campus — far from Boston")
        return 0.2
    if not city:
        return 0.4
    return 0.35


def _uniqueness_score(event: EventRecord, reasons: list[str]) -> float:
    title = event.title.lower()
    if any(word in title for word in ("week", "summit", "conference", "hackathon", "forum")):
        reasons.append("flagship-style event")
        return 0.85
    if event.series_id:
        reasons.append(f"watched series {event.series_id}")
        return 0.8
    return 0.4


def _confidence_score(event: EventRecord, reasons: list[str]) -> float:
    confirmed = [r for r in event.access_routes if r.observation_kind == ObservationKind.CONFIRMED_CURRENT]
    if len(event.sources) > 1:
        reasons.append(f"{len(event.sources)} independent sources")
    score = 0.35 + 0.2 * min(2, len(event.sources)) + 0.15 * min(2, len(confirmed))
    if event.start_at is None:
        score -= 0.2
    return max(0.1, min(1.0, score))
