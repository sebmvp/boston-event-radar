from __future__ import annotations

import os

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from event_radar.alerts import format_alert, notify_high_priority
from event_radar.config import CONFIG_DIR, DATA_DIR, db_path, load_profile, load_series, load_sources
from event_radar.models import AccessStatus, AccessType, EventRecord, ObservationKind
from event_radar.pipeline import run_discover
from event_radar.processing.filter import is_upcoming
from event_radar.storage import Store

load_dotenv()
app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _store() -> Store:
    return Store()


def _when(event: EventRecord) -> str:
    if not event.start_at:
        return "TBD"
    start = event.start_at.strftime("%a %b %d %H:%M")
    if event.end_at and event.end_at.date() != event.start_at.date():
        return f"{start}–{event.end_at.strftime('%b %d')}"
    return start


def _best(event: EventRecord) -> str:
    route = event.best_current_access()
    if not route:
        return "unknown"
    price = "free" if route.price == 0 else (f"${route.price:.0f}" if route.price is not None else "?")
    return f"{route.type.value} {price} ({route.status.value})"


def _urgency(event: EventRecord) -> str:
    score = event.score.total if event.score else 0
    if any(
        r.type in {AccessType.STUDENT_TICKET, AccessType.VOLUNTEER, AccessType.EARLY_BIRD}
        and r.observation_kind != ObservationKind.HISTORICAL
        and r.status == AccessStatus.UNCERTAIN
        for r in event.access_routes
    ):
        return "HIGH"
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    return "LOW"


def _render_event(event: EventRecord) -> None:
    score = event.score.total if event.score else "?"
    console.print()
    console.rule(f"[bold]🔥 {score}/100 — {event.title}")
    console.print(f"[bold]WHEN[/]       {_when(event)} {event.timezone or ''}".rstrip())
    where = ", ".join(p for p in [event.venue, event.city] if p) or event.location_mode.value
    console.print(f"[bold]WHERE[/]      {where}")
    why = "; ".join(event.score.reasons[:4]) if event.score else ""
    console.print(f"[bold]WHY[/]        {why or 'n/a'}")
    if event.score and event.score.penalties:
        console.print(f"[bold]CAVEATS[/]    {'; '.join(event.score.penalties[:3])}")
    std = f"${event.standard_price:.0f}" if event.standard_price is not None else "unknown"
    low = f"${event.lowest_known_price:.0f}" if event.lowest_known_price is not None else "unknown"
    console.print(f"[bold]STANDARD[/]   {std}")
    console.print(f"[bold]LOWEST[/]     {low}")
    console.print(f"[bold]BEST ACCESS[/] {_best(event)}")
    current = [r for r in event.access_routes if r.observation_kind != ObservationKind.HISTORICAL]
    extras = [r for r in current if r is not event.best_current_access()]
    if extras:
        labels = ", ".join(f"{r.type.value}" for r in extras[:4])
        console.print(f"[bold]ALSO FOUND[/] {labels}")
    console.print(f"[bold]URGENCY[/]    {_urgency(event)} · score {score}/100")
    action = "Review the listing and decide whether to RSVP."
    best = event.best_current_access()
    if best and best.type == AccessType.STUDENT_TICKET:
        action = "Request student access now. Volunteer/founder routes may be fallback."
    elif best and best.type == AccessType.VOLUNTEER:
        action = "Email the volunteer contact / apply before slots fill."
    elif best and best.type == AccessType.FREE_ADMISSION and best.status == AccessStatus.APPROVAL_REQUIRED:
        action = "Request to join / apply — approval required."
    elif best and best.status == AccessStatus.APPROVAL_REQUIRED:
        action = "Submit the request-to-join now."
    console.print(f"[bold]ACTION[/]     {action}")
    sources = ", ".join(f"{s.source_id}" for s in event.sources)
    console.print(f"[bold]SOURCES[/]    {sources}")
    console.print(f"[bold]URL[/]        {event.registration_url or event.canonical_url}")
    if event.access_routes:
        console.print("[bold]ROUTES[/]")
        for route in event.access_routes:
            kind = route.observation_kind.value
            flag = "" if kind == ObservationKind.CONFIRMED_CURRENT.value else f" ({kind})"
            price = "free" if route.price == 0 else (f"${route.price:.0f}" if route.price is not None else "n/a")
            ev = route.evidence[0].text[:90] if route.evidence else ""
            ev_url = route.evidence[0].source_url if route.evidence else None
            console.print(
                f"  - {route.type.value}: {price} · {route.status.value}{flag}"
                + (f" · coupon {route.coupon_code}" if route.coupon_code else "")
                + (f" · {route.eligibility}" if route.eligibility else "")
                + (f" · {route.contact_email}" if route.contact_email else "")
            )
            if ev:
                console.print(f"      evidence: {ev}")
            if ev_url:
                console.print(f"      evidence url: {ev_url}")
    if event.score:
        console.print(f"[dim]{format_alert(event)}[/]")


@app.command()
def discover(
    source: str | None = typer.Option(None, help="Only this source id/type (e.g. luma, mit_localist)"),
    notify: bool = typer.Option(False, help="Send Telegram alerts for high-priority events"),
) -> None:
    """Fetch enabled sources, normalize, dedupe, score, and store."""
    store = _store()
    events, runs = run_discover(store=store, source=source)
    console.print(f"Stored {len(events)} events from {len(runs)} sources.")
    failed = [r for r in runs if not r.ok]
    for run in runs:
        status = "ok" if run.ok else f"FAIL {run.failure_reason}"
        console.print(f"  {run.source_id}: {run.events_discovered} raw · errors={run.parse_errors} · {status}")
    if failed:
        console.print(f"[yellow]{len(failed)} source(s) failed; other sources still stored.[/]")
    top = sorted(
        [e for e in events if is_upcoming(e)],
        key=lambda e: (e.score.total if e.score else 0),
        reverse=True,
    )[:8]
    for event in top:
        _render_event(event)
    if notify:
        profile = load_profile()
        threshold = int(profile.get("scoring", {}).get("high_priority_threshold", 70))
        sent = notify_high_priority(events, threshold=threshold)
        console.print(f"Telegram sent: {sent}")


@app.command("list")
def list_events(
    min_score: int = typer.Option(0, help="Minimum score"),
    limit: int = typer.Option(25, help="Max rows"),
    upcoming: bool = typer.Option(True, help="Only upcoming (default)"),
) -> None:
    """List stored events by score."""
    events = _store().list_events(min_score=min_score or None, limit=limit, upcoming_only=upcoming)
    table = Table(title="Boston Event Radar")
    table.add_column("id", style="dim", max_width=8)
    table.add_column("score", justify="right")
    table.add_column("when")
    table.add_column("event")
    table.add_column("access")
    table.add_column("city")
    for event in events:
        table.add_row(
            event.id[:8],
            str(event.score.total if event.score else ""),
            _when(event),
            event.title[:48],
            _best(event),
            event.city or "",
        )
    console.print(table)
    if not events:
        console.print("No events stored yet. Run: event-radar discover")


@app.command()
def upcoming(
    min_score: int = typer.Option(40, help="Minimum score"),
    limit: int = typer.Option(20, help="Max rows"),
) -> None:
    """Upcoming events worth a look."""
    list_events(min_score=min_score, limit=limit, upcoming=True)


@app.command()
def opportunities(
    min_score: int = typer.Option(40),
    limit: int = typer.Option(20),
) -> None:
    """Events with a cheap, student, volunteer, or application route."""
    wanted = {
        "free_admission",
        "student_ticket",
        "student_discount",
        "volunteer",
        "scholarship",
        "founder_ticket",
        "hackathon_participant",
        "invite_request",
    }
    events = _store().list_events(min_score=min_score, limit=400, upcoming_only=True)
    shown = 0
    for event in events:
        routes = [
            r
            for r in event.access_routes
            if r.observation_kind != ObservationKind.HISTORICAL
            and r.type.value in wanted
            and r.status not in {AccessStatus.CLOSED, AccessStatus.SOLD_OUT}
        ]
        if not routes:
            continue
        _render_event(event)
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        console.print("No current cheap/student/volunteer routes stored.")


@app.command()
def show(event_id: str) -> None:
    """Show one event by id prefix or full id."""
    event = _store().get_event(event_id)
    if event is None:
        console.print(f"Not found: {event_id}")
        raise typer.Exit(1)
    _render_event(event)


@app.command()
def status() -> None:
    """Show latest source fetch health."""
    _print_source_status()


@app.command("source-status")
def source_status() -> None:
    """Alias for status."""
    _print_source_status()


def _print_source_status() -> None:
    store = _store()
    by_id = store.latest_run_by_source()
    table = Table(title="Source health (latest run per source)")
    table.add_column("source")
    table.add_column("ok")
    table.add_column("events")
    table.add_column("errors")
    table.add_column("finished")
    table.add_column("failure")
    for source_id, run in sorted(by_id.items()):
        table.add_row(
            source_id,
            "yes" if run.ok else "no",
            str(run.events_discovered),
            str(run.parse_errors),
            run.finished_at.isoformat(timespec="seconds") if run.finished_at else "",
            (run.failure_reason or "")[:60],
        )
    console.print(table)
    console.print(f"Stored events: {store.count()}")


@app.command()
def sources() -> None:
    """List configured sources (enabled and disabled)."""
    doc = load_sources()
    table = Table(title="Source registry")
    table.add_column("id")
    table.add_column("type")
    table.add_column("enabled")
    table.add_column("category")
    table.add_column("org / notes")
    for src in doc.get("sources") or []:
        table.add_row(
            str(src.get("id")),
            str(src.get("type")),
            "yes" if src.get("enabled") else "no",
            str(src.get("category") or ""),
            str(src.get("org") or src.get("notes") or src.get("url") or src.get("base_url") or "")[:50],
        )
    console.print(table)
    orgs = _store().list_organizers(limit=15)
    if orgs:
        console.print("\nDiscovered organizers / calendars:")
        for org in orgs:
            extra = f" ({org.calendar_api_id})" if org.calendar_api_id else ""
            console.print(f"  - {org.name}{extra} · seen {org.event_count}x")


@app.command()
def watchlist() -> None:
    """Recurring flagship events to monitor (historical ≠ current)."""
    series = load_series().get("series") or []
    table = Table(title="Watchlist")
    table.add_column("id")
    table.add_column("name")
    table.add_column("month")
    table.add_column("historical")
    table.add_column("watch urls")
    for item in series:
        hist = item.get("historical") or {}
        hist_bits = ", ".join(f"{k}={v}" for k, v in hist.items() if v)
        urls = ", ".join(item.get("watch_urls") or [])
        table.add_row(
            str(item.get("id")),
            str(item.get("name")),
            str(item.get("expected_month") or "?"),
            hist_bits or "—",
            urls[:60],
        )
    console.print(table)
    console.print("[dim]Historical flags are WATCH signals, not currently-open access.[/]")


@app.command()
def doctor() -> None:
    """Check database, config, optional Telegram, and network sanity."""
    ok = True

    def check(label: str, passed: bool, detail: str) -> None:
        nonlocal ok
        mark = "ok" if passed else "FAIL"
        if not passed:
            ok = False
        console.print(f"[{'green' if passed else 'red'}]{mark}[/]  {label} — {detail}")

    check("config/sources.yaml", (CONFIG_DIR / "sources.yaml").exists(), str(CONFIG_DIR / "sources.yaml"))
    check("config/profile.yaml", (CONFIG_DIR / "profile.yaml").exists(), str(CONFIG_DIR / "profile.yaml"))
    try:
        doc = load_sources()
        n = len([s for s in doc.get("sources") or [] if s.get("enabled")])
        check("enabled sources", n >= 1, f"{n} enabled")
    except Exception as exc:
        check("load sources", False, str(exc))
        n = 0
    path = db_path()
    try:
        store = Store(path)
        store.count()
        check("sqlite", True, str(path))
    except Exception as exc:
        check("sqlite", False, str(exc))
    cache = DATA_DIR / "cache"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        probe = cache / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        check("cache dir writable", True, str(cache))
    except Exception as exc:
        check("cache dir writable", False, str(exc))
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        check("telegram", True, "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID set")
    else:
        console.print("[yellow]skip[/]  telegram — not configured (core pipeline does not need it)")
    try:
        import httpx

        response = httpx.get("https://api.lu.ma/discover/get-paginated-events", params={"latitude": "42.36", "longitude": "-71.06", "pagination_limit": "1"}, timeout=15, headers={"Accept": "application/json", "Origin": "https://luma.com"})
        check("luma public JSON", response.status_code == 200, f"HTTP {response.status_code}")
    except Exception as exc:
        check("luma public JSON", False, str(exc))
    playwright = False
    try:
        import importlib.util

        playwright = importlib.util.find_spec("playwright") is not None
    except Exception:
        playwright = False
    console.print(f"[dim]playwright installed: {playwright} (not required)[/]")
    if not ok:
        raise typer.Exit(1)
    console.print("[green]doctor passed[/]")


if __name__ == "__main__":
    app()
