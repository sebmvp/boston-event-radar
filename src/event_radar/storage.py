"""SQLite persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from event_radar.config import DATA_DIR
from event_radar.config import db_path as default_db_path
from event_radar.models import EventRecord, OrganizerRecord, SourceRun
from event_radar.processing.dedupe import canonical_host_path, merge_events, same_event


def _remote_title(event: EventRecord) -> bool:
    title = (event.title or "").lower()
    if "nyc" in title or "new york" in title:
        return True
    if "houston" in title and "boston" not in title:
        return True
    return False


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(Text)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lowest_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    series_id: Mapped[str | None] = mapped_column(String, nullable=True)
    canonical_key: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRunRow(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String)
    source_type: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    events_discovered: Mapped[int] = mapped_column(Integer, default=0)
    parse_errors: Mapped[int] = mapped_column(Integer, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrganizerRow(Base):
    __tablename__ = "organizers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(Text)
    calendar_api_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_count: Mapped[int] = mapped_column(Integer, default=1)


class Store:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        with self.engine.connect() as conn:
            cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(events)").fetchall()}
            if "canonical_key" not in cols:
                conn.exec_driver_sql("ALTER TABLE events ADD COLUMN canonical_key VARCHAR")
                conn.commit()

    def upsert_events(self, events: list[EventRecord]) -> list[EventRecord]:
        stored: list[EventRecord] = []
        with Session(self.engine) as session:
            for event in events:
                existing = self._find_existing(session, event)
                if existing is not None and existing.id != event.id:
                    event = merge_events([existing, event])
                    event.id = existing.id
                elif existing is not None:
                    event = merge_events([existing, event])
                    event.id = existing.id
                payload = event.model_dump_json()
                row = session.get(EventRow, event.id)
                key = canonical_host_path(event.canonical_url) or None
                if row is None:
                    session.add(
                        EventRow(
                            id=event.id,
                            title=event.title,
                            payload=payload,
                            start_at=event.start_at,
                            city=event.city,
                            score=event.score.total if event.score else None,
                            lowest_price=event.lowest_known_price,
                            series_id=event.series_id,
                            canonical_key=key,
                            updated_at=event.last_checked_at,
                        )
                    )
                else:
                    row.title = event.title
                    row.payload = payload
                    row.start_at = event.start_at
                    row.city = event.city
                    row.score = event.score.total if event.score else None
                    row.lowest_price = event.lowest_known_price
                    row.series_id = event.series_id
                    row.canonical_key = key
                    row.updated_at = event.last_checked_at
                stored.append(event)
            session.commit()
        return stored

    def _find_existing(self, session: Session, event: EventRecord) -> EventRecord | None:
        row = session.get(EventRow, event.id)
        if row is None:
            key = canonical_host_path(event.canonical_url)
            if key:
                stmt = select(EventRow).where(EventRow.canonical_key == key)
                row = session.scalars(stmt).first()
        if row is None:
            # last-resort: compare a handful of same-day rows
            if event.start_at is not None:
                stmt = select(EventRow).where(EventRow.start_at == event.start_at).limit(25)
                for candidate in session.scalars(stmt):
                    other = EventRecord.model_validate_json(candidate.payload)
                    if same_event(event, other):
                        return other
            return None
        return EventRecord.model_validate_json(row.payload)

    def record_run(self, run: SourceRun) -> None:
        with Session(self.engine) as session:
            session.add(
                SourceRunRow(
                    source_id=run.source_id,
                    source_type=run.source_type,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    ok=run.ok,
                    events_discovered=run.events_discovered,
                    parse_errors=run.parse_errors,
                    failure_reason=run.failure_reason,
                )
            )
            session.commit()

    def upsert_organizer(self, organizer: OrganizerRecord) -> None:
        with Session(self.engine) as session:
            row = session.get(OrganizerRow, organizer.id)
            if row is None and organizer.calendar_api_id:
                stmt = select(OrganizerRow).where(OrganizerRow.calendar_api_id == organizer.calendar_api_id)
                row = session.scalars(stmt).first()
            if row is None:
                session.add(
                    OrganizerRow(
                        id=organizer.id,
                        name=organizer.name,
                        payload=organizer.model_dump_json(),
                        calendar_api_id=organizer.calendar_api_id,
                        last_seen_at=organizer.last_seen_at,
                        event_count=organizer.event_count,
                    )
                )
            else:
                prev = OrganizerRecord.model_validate_json(row.payload)
                prev.last_seen_at = organizer.last_seen_at
                prev.event_count = prev.event_count + 1
                if organizer.calendar_api_id:
                    prev.calendar_api_id = organizer.calendar_api_id
                for url in organizer.urls:
                    if url not in prev.urls:
                        prev.urls.append(url)
                row.name = prev.name
                row.payload = prev.model_dump_json()
                row.calendar_api_id = prev.calendar_api_id
                row.last_seen_at = prev.last_seen_at
                row.event_count = prev.event_count
            session.commit()

    def list_organizers(self, limit: int = 50) -> list[OrganizerRecord]:
        with Session(self.engine) as session:
            stmt = select(OrganizerRow).order_by(OrganizerRow.event_count.desc()).limit(limit)
            return [OrganizerRecord.model_validate_json(row.payload) for row in session.scalars(stmt)]

    def list_events(
        self,
        *,
        min_score: int | None = None,
        limit: int = 50,
        upcoming_only: bool = False,
        now: datetime | None = None,
    ) -> list[EventRecord]:
        from event_radar.processing.filter import is_upcoming

        with Session(self.engine) as session:
            stmt = select(EventRow).order_by(EventRow.score.desc().nullslast(), EventRow.start_at)
            if min_score is not None:
                stmt = stmt.where(EventRow.score >= min_score)
            rows = list(session.scalars(stmt.limit(limit * 8 if upcoming_only else limit)))
            events = [EventRecord.model_validate_json(row.payload) for row in rows]
        if upcoming_only:
            events = [e for e in events if is_upcoming(e, now) and not _remote_title(e)]
        return events[:limit]

    def get_event(self, event_id: str) -> EventRecord | None:
        with Session(self.engine) as session:
            row = session.get(EventRow, event_id)
            if row is None and len(event_id) >= 8:
                stmt = select(EventRow).where(EventRow.id.startswith(event_id))
                row = session.scalars(stmt).first()
            return EventRecord.model_validate_json(row.payload) if row else None

    def latest_runs(self) -> list[SourceRun]:
        with Session(self.engine) as session:
            stmt = select(SourceRunRow).order_by(SourceRunRow.id.desc()).limit(80)
            rows = list(session.scalars(stmt))
            return [
                SourceRun(
                    source_id=r.source_id,
                    source_type=r.source_type,
                    started_at=r.started_at,
                    finished_at=r.finished_at,
                    ok=r.ok,
                    events_discovered=r.events_discovered,
                    parse_errors=r.parse_errors,
                    failure_reason=r.failure_reason,
                )
                for r in rows
            ]

    def latest_run_by_source(self) -> dict[str, SourceRun]:
        out: dict[str, SourceRun] = {}
        for run in self.latest_runs():
            if run.source_id not in out:
                out[run.source_id] = run
        return out

    def count(self) -> int:
        with Session(self.engine) as session:
            return int(session.scalar(select(func.count()).select_from(EventRow)) or 0)


def organizer_id(name: str, calendar_api_id: str | None = None) -> str:
    key = calendar_api_id or name.lower().strip()
    return str(uuid5(NAMESPACE_URL, f"organizer:{key}"))
