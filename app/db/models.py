from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyBaseAccessTokenTableUUID,
)

class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class SearchQuery(TimestampMixin, Base):
    __tablename__ = "search_queries"

    id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    city_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "cities.id",
            name="fk_search_queries_city_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )

    phrase: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('queued', 'running', 'completed', 'failed', 'interrupted')",
            name="ck_collection_runs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    method: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="queued",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class QueryResult(Base):
    __tablename__ = "query_results"

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "query_id",
            name="uq_query_results_run_query",
        ),
        CheckConstraint(
            "status IN ('ok', 'error')",
            name="ck_query_results_status",
        ),
        CheckConstraint(
            "total_count IS NULL OR total_count >= 0",
            name="ck_query_results_total_count",
        ),
        Index(
            "ix_query_results_query_collected",
            "query_id",
            "collected_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )

    query_id: Mapped[str] = mapped_column(
        ForeignKey("search_queries.id", ondelete="RESTRICT"),
        nullable=False,
    )

    phrase_snapshot: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    city_id_snapshot: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    category_id_snapshot: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    total_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    raw_response: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class City(TimestampMixin, Base):
    __tablename__ = "cities"

    id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )


class User(SQLAlchemyBaseUserTableUUID, Base):
    pass


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass