from __future__ import annotations

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from event_radar.alerts import format_alert, notify_high_priority
from event_radar.config import load_profile
from event_radar.models import AccessStatus, EventRecord, ObservationKind
from event_radar.pipeline import run_discover
from event_radar.storage import Store

load_dotenv()
app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _store() -> Store:
    return Store()


def _when(event: EventRecord) -> str:
    if not event.start_at:
        return "TBD"
    end = f"–{event.end_at.strftime('%b %d')}" if event.end_at else ""
    return event.start_at.strftime("%a %b %d %H:%M") + end


def _best(event: EventRecord) -> str:
    route = event.best_current_access()
    if not route:
        return "unknown"
    price = "free" if route.price == 0 else (f"${route.price:.0f}" if route.price is not None else "?")
    return f"{route.type.value} {price} ({route.status.value})"


def _render_event(event: EventRecord) -> None:
    score = event.score.total if event.score else "?"
    console.print()
    console.rule(f"[bold]{event.title}")
    console.print(f"[bold]WHEN[/]       {_when(event)} {event.timezone or ''}".rstrip())
    where = ", ".join(p for p in [event.venue, event.city] if p) or event.location_mode.value
    console.print(f"[bold]WHERE[/]      {where}")
    why = "; ".join(event.score.reasons[:4]) if event.score else ""
    console.print(f"[bold]WHY[/]        {why or 'n/a'}")
    if event.score and event.score.penalties:
        console.print(f"[bold]CAVEATS[/]    {'; '.join(event.score.penalties[:3])}")
    std = f"${event.standard_price:.0f}" if event.standard_price is not None else "unknown"
    low = f"${event.lowest_known_price:.0f}" if event.lowest_known_price is not None else "unknown"
    console.print(f"[bold]PRICE[/]      standard {std} · lowest known {low}")
    console.print(f"[bold]BEST ACCESS[/] {_best(event)}")
    urgency = "HIGH" if isinstance(score, int) and score >= 80 else ("MEDIUM" if isinstance(score, int) and score >= 60 else "LOW")
    console.print(f"[bold]URGENCY[/]    {urgency} · score {score}/100")
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
            console.print(
                f"  - {route.type.value}: {price} · {route.status.value}{flag}"
                + (f" · coupon {route.coupon_code}" if route.coupon_code else "")
                + (f" · {route.eligibility}" if route.eligibility else "")
            )
            if ev:
                console.print(f"      evidence: {ev}")
    if event.score:
        console.print(f"[dim]{format_alert(event)}[/]")


@app.command()
def discover(
    notify: bool = typer.Option(False, help="Send Telegram alerts for high-priority events"),
) -> None:
    """Fetch enabled sources, normalize, dedupe, score, and store."""
    store = _store()
    events, runs = run_discover(store=store)
    console.print(f"Stored {len(events)} events from {len(runs)} sources.")
    failed = [r for r in runs if not r.ok]
    for run in runs:
        status = "ok" if run.ok else f"FAIL {run.failure_reason}"
        console.print(f"  {run.source_id}: {run.events_discovered} raw · errors={run.parse_errors} · {status}")
    if failed:
        console.print(f"[yellow]{len(failed)} source(s) failed; other sources still stored.[/]")
    top = sorted(events, key=lambda e: (e.score.total if e.score else 0), reverse=True)[:8]
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
) -> None:
    """List stored events by score."""
    events = _store().list_events(min_score=min_score or None, limit=limit)
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
    events = _store().list_events(min_score=min_score, limit=200)
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
    store = _store()
    runs = store.latest_runs()
    table = Table(title="Source runs")
    table.add_column("source")
    table.add_column("ok")
    table.add_column("events")
    table.add_column("errors")
    table.add_column("finished")
    table.add_column("failure")
    for run in runs:
        table.add_row(
            run.source_id,
            "yes" if run.ok else "no",
            str(run.events_discovered),
            str(run.parse_errors),
            run.finished_at.isoformat(timespec="seconds") if run.finished_at else "",
            (run.failure_reason or "")[:60],
        )
    console.print(table)
    console.print(f"Stored events: {store.count()}")


if __name__ == "__main__":
    app()
