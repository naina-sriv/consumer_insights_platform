# Architecture Decisions Log (DECISIONS.md)

This log records major design and implementation choices, tradeoffs, and rationale for the Multi-Tenant Consumer Insights Platform.

---

### ADR 001: PostgreSQL with `pgvector` vs. Dedicated Vector Database (Pinecone / Qdrant)
- **Decision**: Use PostgreSQL 16 with `pgvector` (HNSW cosine similarity index) for storing and querying text embeddings.
- **Why**: Keeps transactional consumer records, tenant isolation scopes, audit logs, and vector embeddings within a single ACID-compliant database. Eliminates dual-write synchronization issues and cross-system consistency hazards.
- **Tradeoff**: Vertical scaling ceiling compared to distributed vector engines; acceptable for up to tens of millions of vectors before requiring horizontal partitioning.

### ADR 002: ARQ + Redis vs. Celery / RabbitMQ for Async Workers
- **Decision**: Use `arq` with Redis 7 as the background job engine.
- **Why**: Native `asyncio` support in Python with zero thread/gevent friction, lightweight footprint, and direct integration with modern async FastAPI and SQLAlchemy.
- **Tradeoff**: Less complex enterprise routing (e.g. topic exchanges) than RabbitMQ/Celery, but simpler to deploy, monitor, and reason about.

### ADR 003: Row-Level Application Multi-Tenancy with Centralized `scoped()` Helper
- **Decision**: Enforce tenant isolation at the application query level via `scoped(query, tenant_id)` on all tenant-owned models.
- **Why**: Simpler to manage in SQLAlchemy Async than dynamic schema-per-tenant, while guaranteeing strict isolation verified through automated test suites.
- **Future Stretch**: Enforce PostgreSQL Row-Level Security (RLS) via session-local variables (`SET LOCAL app.tenant_id`) in Phase 1 stretch.

### ADR 004: Embedding Dimension and Model
- **Decision**: Fix embedding dimension to 1536 dims (`text-embedding-3-small`).
- **Why**: Provides high-performance semantic retrieval at very low cost per 1k tokens, natively supported in `pgvector` with HNSW indexing.

### ADR 005: Backend-Agnostic GUID & Vector Types for Fast, Isolated Testing
- **Decision**: Define custom SQLAlchemy `GUID` and `UniversalVector` `TypeDecorator` implementations.
- **Why**: In production, they bind directly to native PostgreSQL `UUID` and `pgvector.Vector`. In developer and CI test suites without active Docker containers, they seamlessly bind to SQLite `CHAR(36)` and `TEXT`, allowing ultra-fast in-memory test execution without network dependencies.
- **Tradeoff**: Minimal boilerplate in `domain.py`, vastly improved developer velocity and test reliability.

### ADR 006: Keyset Pagination for Background Worker Batch Processing
- **Decision**: Process records during job execution via keyset pagination (`WHERE id > :last_id ORDER BY id LIMIT :batch_size`) rather than `OFFSET`.
- **Why**: `OFFSET` pagination exhibits $O(N^2)$ scan complexity as dataset size grows to 20,000+ records. Keyset pagination operates in strict $O(N)$ index-seek time and eliminates duplicate/missed row hazards during ongoing writes.
