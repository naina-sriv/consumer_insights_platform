import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import CHAR

from app.config import settings
from app.db import Base


def utcnow() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class GUID(TypeDecorator):
    """
    Platform-agnostic GUID / UUID type.

    Uses PostgreSQL native UUID type when on Postgres,
    falls back to CHAR(36) on SQLite and other dialects.
    Transparently handles both uuid.UUID instances and string representations.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value if dialect.name == "postgresql" else str(value)
        parsed = uuid.UUID(str(value))
        return parsed if dialect.name == "postgresql" else str(parsed)

    def process_result_value(self, value: Any, dialect: Any) -> Optional[uuid.UUID]:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class UniversalVector(TypeDecorator):
    """
    Platform-agnostic Vector type.

    Uses pgvector Vector on PostgreSQL, falls back to Text on other engines (e.g. SQLite for tests).
    """

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 1536):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value))
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} name={self.name!r}>"


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin, analyst, viewer
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # reviews, survey, transcript
    row_count = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="uploaded")  # uploaded, processed, failed
    uploaded_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name!r} rows={self.row_count}>"


class Record(Base):
    __tablename__ = "records"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    dataset_id = Column(GUID(), ForeignKey("datasets.id"), nullable=False)
    external_id = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("dataset_id", "external_id", name="uq_record_dataset_external_id"),
    )

    def __repr__(self) -> str:
        return f"<Record id={self.id} external_id={self.external_id!r}>"


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    record_id = Column(GUID(), ForeignKey("records.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(UniversalVector(settings.embedding_dim), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    template = Column(Text, nullable=False)
    output_schema = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_name_version"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    dataset_id = Column(GUID(), ForeignKey("datasets.id"), nullable=False)
    type = Column(String, nullable=False, default="analyze")  # analyze, embed
    status = Column(String, nullable=False, default="queued")  # queued, running, retrying, completed, failed
    attempts = Column(Integer, nullable=False, default=0)
    progress = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    prompt_id = Column(GUID(), ForeignKey("prompts.id"), nullable=True)
    prompt_version = Column(Text, nullable=True)
    model = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_job_tenant_idempotency_key"),
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} status={self.status} progress={self.progress}%>"


class Insight(Base):
    __tablename__ = "insights"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    job_id = Column(GUID(), ForeignKey("jobs.id"), nullable=False)
    kind = Column(String, nullable=False)  # theme, summary, recommendation
    payload = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class InsightSource(Base):
    __tablename__ = "insight_sources"

    insight_id = Column(GUID(), ForeignKey("insights.id"), primary_key=True)
    record_id = Column(GUID(), ForeignKey("records.id"), primary_key=True)


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    job_id = Column(GUID(), ForeignKey("jobs.id"), nullable=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    prompt_version = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    latency_ms = Column(Integer, nullable=False, default=0)
    cache_hit = Column(Boolean, nullable=False, default=False)
    fallback_used = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(GUID(), nullable=False)
    detail = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action!r} entity_id={self.entity_id}>"


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(GUID(), ForeignKey("prompts.id"), nullable=True)
    model = Column(String, nullable=False)
    dataset_size = Column(Integer, nullable=False)
    theme_score = Column(Float, nullable=False)
    sentiment_f1 = Column(Float, nullable=False)
    groundedness = Column(Float, nullable=False)
    detail = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
