import os
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Text, BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/telemetry",
)


class Base(DeclarativeBase):
    pass


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    machine_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    total_events: Mapped[int] = mapped_column(BigInteger, default=0)
    total_sessions: Mapped[int] = mapped_column(BigInteger, default=0)
    user_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sessions = relationship("Session", back_populates="machine", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="machine", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    machine_id: Mapped[str] = mapped_column(String(36), ForeignKey("machines.machine_id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0)

    machine = relationship("Machine", back_populates="sessions")

    __table_args__ = (
        Index("idx_session_machine_time", "machine_id", "start_time"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.session_id"), nullable=False, index=True)
    machine_id: Mapped[str] = mapped_column(String(36), ForeignKey("machines.machine_id"), nullable=False, index=True)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    workbench: Mapped[str] = mapped_column(String(64), default="")
    command: Mapped[str] = mapped_column(Text, nullable=False)
    freecad_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    machine = relationship("Machine", back_populates="events")
    session = relationship("Session")

    __table_args__ = (
        Index("idx_events_machine_time", "machine_id", "timestamp"),
        Index("idx_events_source", "source"),
    )


engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
