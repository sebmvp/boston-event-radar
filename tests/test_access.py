from datetime import UTC, datetime

from event_radar.models import AccessStatus, AccessType, ObservationKind, RawEvent
from event_radar.processing.access import extract_access


def _raw(**kwargs) -> RawEvent:
    base = dict(
        source_id="t",
        source_type="test",
        source_url="https://example.com/e",
        title="Test Event",
        fetched_at=datetime.now(UTC),
    )
    base.update(kwargs)
    return RawEvent(**base)


def test_luma_ticket_types_standard_and_expired_early_bird():
    now = datetime(2026, 9, 11, tzinfo=UTC)
    raw = _raw(
        title="Fintech That Thinks",
        ticket_types=[
            {
                "name": "Standard",
                "cents": 69500,
                "valid_end_at": "2026-09-22T03:59:59.000Z",
                "require_approval": False,
            },
            {
                "name": "Early Bird",
                "cents": 49500,
                "valid_end_at": "2026-08-22T03:59:59.000Z",
                "require_approval": False,
            },
        ],
    )
    routes = extract_access(raw, now=now)
    by_type = {r.type: r for r in routes}
    assert by_type[AccessType.STANDARD_TICKET].price == 695
    assert by_type[AccessType.STANDARD_TICKET].observation_kind == ObservationKind.CONFIRMED_CURRENT
    assert by_type[AccessType.STANDARD_TICKET].status == AccessStatus.OPEN
    assert by_type[AccessType.EARLY_BIRD].price == 495
    assert by_type[AccessType.EARLY_BIRD].status == AccessStatus.CLOSED


def test_student_coupon_from_public_url_is_confirmed_but_uncertain_availability():
    raw = _raw(
        title="Boston Fintech Week",
        description="Must be a current undergraduate or graduate student. Student ID required.",
        registration_url="https://luma.com/fintechthatthinks?coupon=STUDENT2026",
        canonical_url="https://luma.com/fintechthatthinks?coupon=STUDENT2026",
    )
    routes = extract_access(raw)
    student = [r for r in routes if r.type == AccessType.STUDENT_TICKET]
    assert student
    assert any(r.coupon_code == "STUDENT2026" for r in student)
    assert all(r.observation_kind != ObservationKind.HISTORICAL for r in student)


def test_founder_coupon_and_free_entrepreneur_copy():
    raw = _raw(
        title="Boston Fintech Week",
        description="Offering free tickets to eligible early-stage fintech entrepreneurs. "
        "Register https://luma.com/fintechthatthinks?coupon=FINTECH-FOUNDER",
        source_url="https://bostonfintechweek.com/",
    )
    routes = extract_access(raw)
    types = {r.type for r in routes}
    assert AccessType.FOUNDER_TICKET in types


def test_volunteer_last_year_is_not_confirmed_current():
    raw = _raw(
        title="Boston Blockchain Week",
        description="Last year volunteers received free admission.",
    )
    routes = extract_access(raw)
    volunteer = [r for r in routes if r.type == AccessType.VOLUNTEER]
    assert not any(
        r.observation_kind == ObservationKind.CONFIRMED_CURRENT and r.confidence >= 0.75 for r in volunteer
    )


def test_structured_free_with_approval():
    raw = _raw(title="AI Mixer", is_free=True, require_approval=True)
    routes = extract_access(raw)
    free = [r for r in routes if r.type == AccessType.FREE_ADMISSION]
    assert free
    assert free[0].status == AccessStatus.APPROVAL_REQUIRED
    assert free[0].price == 0


def test_hackathon_participant_route():
    raw = _raw(title="Imaginary Instrument Hackathon", is_free=True, description="Participants welcome")
    routes = extract_access(raw)
    assert any(r.type == AccessType.HACKATHON_PARTICIPANT for r in routes)
