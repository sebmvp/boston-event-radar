from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from event_radar.http_client import HttpFetcher
from event_radar.models import RawEvent, SourceRun


@dataclass
class FetchContext:
    fetcher: HttpFetcher
    now: datetime
    lookahead_days: int = 75
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceFetchResult:
    run: SourceRun
    events: list[RawEvent] = field(default_factory=list)


class SourceAdapter(Protocol):
    source_id: str
    source_type: str

    def discover(self, ctx: FetchContext) -> SourceFetchResult: ...


def start_run(source_id: str, source_type: str, now: datetime | None = None) -> SourceRun:
    now = now or datetime.now(UTC)
    return SourceRun(source_id=source_id, source_type=source_type, started_at=now)


def finish_run(
    run: SourceRun,
    *,
    events: list[RawEvent],
    parse_errors: int = 0,
    error: str | None = None,
) -> SourceRun:
    run.finished_at = datetime.now(UTC)
    run.events_discovered = len(events)
    run.parse_errors = parse_errors
    run.ok = error is None
    run.failure_reason = error
    return run
