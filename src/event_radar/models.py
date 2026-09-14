"""Normalized event, access, series, and scoring models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field


class ObservationKind(StrEnum):
    CONFIRMED_CURRENT = "confirmed_current"
    HISTORICAL = "historical"
    INFERRED = "inferred"


class AccessType(StrEnum):
    STANDARD_TICKET = "standard_ticket"
    FREE_ADMISSION = "free_admission"
    STUDENT_TICKET = "student_ticket"
    STUDENT_DISCOUNT = "student_discount"
    VOLUNTEER = "volunteer"
    SCHOLARSHIP = "scholarship"
    COMMUNITY_PASS = "community_pass"
    EARLY_BIRD = "early_bird"
    FOUNDER_TICKET = "founder_ticket"
    JOB_SEEKER = "job_seeker"
    UNIVERSITY_AFFILIATION = "university_affiliation"
    HACKATHON_PARTICIPANT = "hackathon_participant"
    SPEAKER_APPLICATION = "speaker_application"
    WAITLIST = "waitlist"
    INVITE_REQUEST = "invite_request"
    ORGANIZER_OUTREACH = "organizer_outreach"
    FREE_SATELLITE = "free_satellite"
    UNKNOWN = "unknown"


class AccessStatus(StrEnum):
    OPEN = "open"
    APPROVAL_REQUIRED = "approval_required"
    WAITLIST = "waitlist"
    CLOSED = "closed"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"
    UNCERTAIN = "uncertain"


class LocationMode(StrEnum):
    IN_PERSON = "in_person"
    VIRTUAL = "virtual"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class Evidence(BaseModel):
    field: str
    text: str
    source_url: str | None = None
    extracted_from: str = "text"
    confidence: float = 0.5


class AccessRoute(BaseModel):
    type: AccessType
    price: float | None = None
    currency: str = "USD"
    status: AccessStatus = AccessStatus.UNKNOWN
    eligibility: str | None = None
    deadline: datetime | None = None
    application_url: str | None = None
    contact_email: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = 0.5
    observation_kind: ObservationKind = ObservationKind.INFERRED
    coupon_code: str | None = None
    notes: str | None = None


class SourceRef(BaseModel):
    source_id: str
    source_type: str
    source_url: str
    external_id: str | None = None
    fetched_at: datetime
    raw_excerpt: str | None = None


class ScoreBreakdown(BaseModel):
    total: int
    topic_relevance: int = 0
    professional_value: int = 0
    access_affordability: int = 0
    student_volunteer: int = 0
    organizer_quality: int = 0
    scarcity_urgency: int = 0
    travel: int = 0
    uniqueness: int = 0
    confidence: int = 0
    reasons: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)


class EventRecord(BaseModel):
    id: str
    title: str
    description: str | None = None
    organizer: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    source_url: str
    canonical_url: str
    discovered_at: datetime
    last_checked_at: datetime
    last_verified_at: datetime | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    venue: str | None = None
    city: str | None = None
    address: str | None = None
    location_mode: LocationMode = LocationMode.UNKNOWN
    latitude: float | None = None
    longitude: float | None = None
    categories: list[str] = Field(default_factory=list)
    registration_url: str | None = None
    registration_state: str | None = None
    standard_price: float | None = None
    lowest_known_price: float | None = None
    application_deadline: datetime | None = None
    registration_deadline: datetime | None = None
    access_routes: list[AccessRoute] = Field(default_factory=list)
    score: ScoreBreakdown | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    series_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def best_current_access(self) -> AccessRoute | None:
        current = [
            r
            for r in self.access_routes
            if r.observation_kind == ObservationKind.CONFIRMED_CURRENT
            and r.status not in {AccessStatus.CLOSED, AccessStatus.SOLD_OUT}
        ]
        if not current:
            current = [
                r
                for r in self.access_routes
                if r.observation_kind != ObservationKind.HISTORICAL
                and r.status not in {AccessStatus.CLOSED, AccessStatus.SOLD_OUT}
            ]
        if not current:
            return None

        def sort_key(route: AccessRoute) -> tuple[int, float, float]:
            rank = {
                AccessType.STUDENT_TICKET: 0,
                AccessType.STUDENT_DISCOUNT: 0,
                AccessType.VOLUNTEER: 1,
                AccessType.FREE_ADMISSION: 2,
                AccessType.SCHOLARSHIP: 2,
                AccessType.HACKATHON_PARTICIPANT: 2,
                AccessType.FOUNDER_TICKET: 3,
            }
            type_rank = rank.get(route.type, 10)
            preferred = type_rank < 10
            if route.price is not None:
                price = route.price
            else:
                price = 0.0 if preferred else 10_000.0
            return (type_rank, price, -route.confidence)

        return sorted(current, key=sort_key)[0]


class OrganizerRecord(BaseModel):
    id: str
    name: str
    kind: str = "unknown"
    calendar_api_id: str | None = None
    urls: list[str] = Field(default_factory=list)
    discovered_from: str | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    event_count: int = 1


class RecurringSeries(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    organizer: str | None = None
    expected_month: int | None = None
    watch_urls: list[str] = Field(default_factory=list)
    historical: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    next_watch_date: datetime | None = None


class SourceRun(BaseModel):
    source_id: str
    source_type: str
    started_at: datetime
    finished_at: datetime | None = None
    ok: bool = False
    events_discovered: int = 0
    parse_errors: int = 0
    failure_reason: str | None = None
    next_recommended_run: datetime | None = None


class RawEvent(BaseModel):
    source_id: str
    source_type: str
    external_id: str | None = None
    source_url: str
    title: str
    description: str | None = None
    organizer: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    venue: str | None = None
    city: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_mode: LocationMode = LocationMode.UNKNOWN
    categories: list[str] = Field(default_factory=list)
    registration_url: str | None = None
    canonical_url: str | None = None
    price: float | None = None
    is_free: bool | None = None
    require_approval: bool | None = None
    waitlist: bool | None = None
    sold_out: bool | None = None
    ticket_types: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fetched_at: datetime
    raw: dict[str, Any] = Field(default_factory=dict)


def event_id_for(title: str, start_at: datetime | None, city: str | None) -> str:
    date_part = start_at.date().isoformat() if start_at else "undated"
    key = f"{_norm(title)}|{date_part}|{_norm(city or '')}"
    return str(uuid5(NAMESPACE_URL, key))


def _norm(value: str) -> str:
    return " ".join(value.lower().split())
