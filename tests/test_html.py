from datetime import UTC, datetime

from event_radar.processing.access import extract_access
from event_radar.sources.html_page import parse_html_event

HTML = """
<html><head><title>Boston Fintech Week, presented by Fintech Sandbox</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebSite","name":"Boston Fintech Week 2026"}
</script>
</head>
<body>
<meta name="description" content="Boston Fintech Week 2026 is happening on Sep 22 - 25.">
<strong class="pricing__price">Student Tickets</strong>
<span>Must be a *current* undergraduate or graduate student. Student ID and email address required to register.</span>
<a href="https://luma.com/fintechthatthinks?coupon=STUDENT2026">student</a>
<a href="https://luma.com/fintechthatthinks?coupon=FINTECH-FOUNDER">founder</a>
<p>Offering free tickets to eligible early-stage fintech entrepreneurs who meet the general requirements.</p>
<p>Early Bird Tickets</p>
<p>2026 tickets on sale now</p>
</body></html>
"""


def test_html_page_extracts_fintech_week_and_access_signals():
    now = datetime.now(UTC)
    events = parse_html_event(
        HTML,
        source_id="html_boston_fintech_week",
        url="https://bostonfintechweek.com/",
        fetched_at=now,
        title_hint="Boston Fintech Week",
        organizer_hint="Fintech Sandbox",
        city_hint="Boston",
    )
    assert events
    raw = events[0]
    assert "Fintech" in raw.title
    assert raw.organizer == "Fintech Sandbox"
    routes = extract_access(raw)
    types = {r.type.value for r in routes}
    coupons = {r.coupon_code for r in routes if r.coupon_code}
    assert "student_ticket" in types
    assert "STUDENT2026" in coupons
    assert "FINTECH-FOUNDER" in coupons
