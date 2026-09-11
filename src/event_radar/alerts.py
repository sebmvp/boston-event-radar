"""Optional Telegram alerts. Never required for the core pipeline."""

from __future__ import annotations

import os

import httpx

from event_radar.models import EventRecord, ObservationKind


def format_alert(event: EventRecord) -> str:
    score = event.score.total if event.score else 0
    when = event.start_at.strftime("%b %d") if event.start_at else "date TBD"
    where = event.city or event.venue or "Boston area"
    why = ""
    if event.score and event.score.reasons:
        why = "; ".join(event.score.reasons[:3])
    route = event.best_current_access()
    standard = f"${event.standard_price:.0f}" if event.standard_price is not None else "unknown"
    if route:
        price = "FREE" if route.price == 0 else (f"${route.price:.0f}" if route.price is not None else "n/a")
        best = f"{route.type.value.replace('_', ' ')} ({price}, {route.status.value})"
    else:
        best = "unknown"
    extra = [
        r.type.value.replace("_", " ")
        for r in event.access_routes
        if r.observation_kind != ObservationKind.HISTORICAL and r is not route
    ]
    extra_line = f"Also found: {', '.join(extra[:3])}" if extra else ""
    urgency = "HIGH" if score >= 80 else ("MEDIUM" if score >= 60 else "LOW")
    url = event.registration_url or event.canonical_url
    lines = [
        f"🔥 {score}/100 — {event.title}",
        f"{when} · {where}",
        "",
        f"Why it matters: {why or 'see score breakdown'}",
        f"Standard: {standard}",
        f"Best route: {best}",
        extra_line,
        f"Urgency: {urgency}",
        "",
        url,
    ]
    return "\n".join(line for line in lines if line is not None)


def send_telegram(text: str, *, token: str | None = None, chat_id: str | None = None) -> bool:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=20) as client:
        response = client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()
    return True


def notify_high_priority(events: list[EventRecord], *, threshold: int = 70) -> int:
    sent = 0
    for event in events:
        if not event.score or event.score.total < threshold:
            continue
        if send_telegram(format_alert(event)):
            sent += 1
    return sent
