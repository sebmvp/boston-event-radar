"""SQLite persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from event_radar.config import DATA_DIR
from event_radar.models import EventRecord, SourceRun


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


class Store:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (DATA_DIR / "events.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)

    def upsert_events(self, events: list[EventRecord]) -> None:
        with Session(self.engine) as session:
            for event in events:
                row = session.get(EventRow, event.id)
                payload = event.model_dump_json()
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
                    row.updated_at = event.last_checked_at
            session.commit()

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

    def list_events(self, *, min_score: int | None = None, limit: int = 50) -> list[EventRecord]:
        with Session(self.engine) as session:
            stmt = select(EventRow).order_by(EventRow.score.desc().nullslast(), EventRow.start_at)
            if min_score is not None:
                stmt = stmt.where(EventRow.score >= min_score)
            stmt = stmt.limit(limit)
            return [EventRecord.model_validate_json(row.payload) for row in session.scalars(stmt)]

    def get_event(self, event_id: str) -> EventRecord | None:
        with Session(self.engine) as session:
            row = session.get(EventRow, event_id)
            if row is None and len(event_id) >= 8:
                stmt = select(EventRow).where(EventRow.id.startswith(event_id))
                row = session.scalars(stmt).first()
            return EventRecord.model_validate_json(row.payload) if row else None

    def latest_runs(self) -> list[SourceRun]:
        with Session(self.engine) as session:
            stmt = select(SourceRunRow).order_by(SourceRunRow.id.desc()).limit(40)
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

    def count(self) -> int:
        with Session(self.engine) as session:
            return int(session.scalar(select(func.count()).select_from(EventRow)) or 0)
