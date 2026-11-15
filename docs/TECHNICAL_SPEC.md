# Technical Spec: Multi-Tenant Consumer Insights Platform (Phase 1)
*Companion to the PRD. Build module by module in the order in section 12. Where this spec is silent, choose the simplest option and note it in DECISIONS.md.*

---

## 1. Stack
Python 3.12, FastAPI, SQLAlchemy 2.x (async) + Alembic, Postgres 16 + pgvector, Redis 7, ARQ (worker), Pydantic v2, httpx, pytest, Docker Compose. 

- **Embeddings**: `text-embedding-3-small` (1536 dims) fixed in migration.
- **LLM providers**: Two, behind the gateway (`anthropic` primary, `openai` fallback).

---

## 2. Repo Structure
```
app/
  main.py            # FastAPI app, routers, middleware
  config.py          # pydantic-settings, env vars
  db.py              # engine, session, tenant context
  auth/              # jwt, password hashing, deps (current_user, require_role)
  models/            # SQLAlchemy models
  schemas/           # Pydantic request/response models
  routers/           # auth, datasets, jobs, insights, query, admin
  services/
    ingestion.py     # parse + validate uploads
    chunking.py
    embeddings.py
    rag.py
    insights.py      # prompt build, call gateway, validate, persist
  gateway/
    client.py        # LLMGateway: complete(), embed()
    providers/       # base.py, anthropic.py, openai.py
    cache.py
    ratelimit.py
    pricing.py
  worker/            # arq settings + tasks
  prompts/           # versioned prompt files (v1, v2...)
evals/               # labeled.jsonl, run_eval.py
tests/
alembic/  docker-compose.yml  Dockerfile  README.md  DECISIONS.md
```

---

## 3. Environment Variables
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `JWT_EXPIRE_MINUTES=60`
- `PRIMARY_PROVIDER`
- `FALLBACK_PROVIDER`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `LLM_TIMEOUT_SECONDS=30`
- `CACHE_TTL_SECONDS=86400`
- `TENANT_RPM_LIMIT=60`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIM`
- `MAX_UPLOAD_MB=20`
- `MAX_ROWS_PER_DATASET=20000`

---

## 4. Database Schema
All tenant-owned tables have `tenant_id UUID NOT NULL` with an index. All PKs are `UUID DEFAULT gen_random_uuid()`. All tables have `created_at TIMESTAMPTZ DEFAULT now()`.

| Table | Columns (besides id, created_at) | Notes |
| :--- | :--- | :--- |
| `tenants` | `name text unique` | |
| `users` | `tenant_id`, `email text`, `password_hash text`, `role text CHECK in (admin, analyst, viewer)` | unique (`tenant_id`, `email`) |
| `datasets` | `tenant_id`, `name`, `source_type text CHECK in (reviews, survey, transcript)`, `row_count int`, `status text (uploaded, processed, failed)`, `uploaded_by` | |
| `records` | `tenant_id`, `dataset_id`, `external_id text`, `text text`, `metadata jsonb` | unique (`dataset_id`, `external_id`); index (`tenant_id`, `dataset_id`) |
| `chunks` | `tenant_id`, `record_id`, `chunk_index int`, `content text`, `embedding vector(EMBEDDING_DIM)` | HNSW index on embedding (cosine); index (`tenant_id`) |
| `prompts` | `name text`, `version int`, `template text`, `output_schema text` | unique (`name`, `version`) |
| `jobs` | `tenant_id`, `dataset_id`, `type text (analyze, embed)`, `status text`, `attempts int DEFAULT 0`, `error text`, `progress int DEFAULT 0`, `prompt_id`, `model text`, `started_at`, `finished_at`, `created_by`, `idempotency_key text` | `idempotency_key` unique per tenant |
| `insights` | `tenant_id`, `job_id`, `dataset_id`, `kind text (theme, summary, recommendation)`, `payload jsonb`, `confidence float` | payload validated by Pydantic |
| `insight_sources`| `insight_id`, `record_id` | composite PK; lineage link |
| `llm_calls` | `tenant_id`, `job_id null`, `provider`, `model`, `prompt_id null`, `input_tokens`, `output_tokens`, `cost_usd numeric(10,6)`, `latency_ms`, `cache_hit bool`, `fallback_used bool`, `status text`, `error text` | one row per gateway call |
| `audit_log` | `tenant_id`, `user_id`, `action text`, `entity_type`, `entity_id`, `detail jsonb` | append-only, no update/delete in code |
| `eval_runs` | `prompt_id`, `model`, `dataset_size`, `theme_score float`, `sentiment_f1 float`, `groundedness float`, `detail jsonb` | |

**Tenant isolation (P0)**: Every repository function takes `tenant_id` from the authenticated user and applies it to every query. A helper `scoped(query, tenant_id)` is the only way to build queries on tenant tables.

---

## 5. Auth and Roles
- `POST /auth/register-tenant`: creates tenant + first admin.
- `POST /auth/login`: returns `{access_token, token_type}`. JWT claims: `sub` (user id), `tenant_id`, `role`, `exp`.
- Passwords: bcrypt. Dependency `require_role(*roles)`.
- Permissions:
  - `admin`: all
  - `analyst`: upload, create jobs, query, read
  - `viewer`: read insights only

---

## 6. API Contracts
All routes prefixed `/api/v1`. Errors use `{ "error": {"code": str, "message": str} }`.
Codes: `unauthorized` 401, `forbidden` 403, `not_found` 404 (also for cross-tenant IDs), `validation_error` 422, `rate_limited` 429, `provider_unavailable` 503.

| Method + Path | Role | Request | Response |
| :--- | :--- | :--- | :--- |
| `POST /datasets` | `analyst+` | multipart: `file`, `name`, `source_type` | 201 `{id, name, row_count, status}`; rejects > MAX_UPLOAD_MB or malformed rows with 422 |
| `GET /datasets`, `GET /datasets/{id}` | any | | dataset(s) |
| `POST /jobs` | `analyst+` | `{dataset_id, type, prompt_name?, idempotency_key?}` | 202 `{id, status: "queued"}` |
| `GET /jobs/{id}` | any | | `{id, status, progress, attempts, error, started_at, finished_at}` |
| `GET /jobs/{id}/events` | any | | SSE stream of `{status, progress}` |
| `GET /insights?dataset_id=&job_id=&kind=` | any | | list of insights with sources (`record_ids`) |
| `GET /insights/{id}/lineage` | any | | `{insight, source_records[], prompt{name,version}, model, job_id, llm_calls[]}` |
| `POST /query` | `analyst+` | `{dataset_id, question, top_k?=8}` | `{answer, citations[{record_id, chunk_id, snippet}], model, cached}` |
| `GET /admin/audit?limit=&cursor=` | `admin` | | paginated audit rows |
| `GET /admin/usage?from=&to=` | `admin` | | tokens, cost, latency, cache hit rate grouped by day and model |
| `GET /health` | none | | `{status, db, redis}` |

---

## 7. Job State Machine
`queued` $\rightarrow$ `running` $\rightarrow$ `completed`, or `running` $\rightarrow$ `retrying` $\rightarrow$ `running`, or `running` $\rightarrow$ `failed`.

- ARQ task `analyze_dataset(job_id)`. Set `running`, `started_at`.
- Process records in batches of 50; update progress (0 to 100) after each batch.
- Retries: max 3 attempts, exponential backoff (2s, 8s, 30s). Retry on provider timeout/5xx/rate limit only. Validation failure after 2 LLM re-asks marks that batch failed; job fails if more than 20% of batches fail.
- Idempotency: if `(tenant_id, idempotency_key)` exists, return the existing job. Re-running a job must delete or replace its prior insights (unique on `job_id`).
- Every state change writes an audit row.

---

## 8. LLM Gateway
- **Interface**: `await gateway.complete(tenant_id, prompt, schema=None, job_id=None) -> GatewayResult` and `await gateway.embed(tenant_id, texts) -> list[list[float]]`.
- **Rate limit**: Redis sliding window per tenant, `TENANT_RPM_LIMIT`; exceed raises `RateLimited`.
- **Cache**: key = `sha256(provider_family + model + prompt_version + normalized_prompt)`; store result JSON with `CACHE_TTL_SECONDS`. Skip cache when `temperature > 0`. Log `cache_hit=true`.
- **Fallback**: Call primary with `LLM_TIMEOUT_SECONDS`. On timeout, 5xx, or 429: call fallback once (`fallback_used=true`). If both fail: raise `ProviderUnavailable`.
- **Structured output**: if schema given, parse JSON into Pydantic model; on failure re-ask with validation error appended (max 2 times).
- **Telemetry**: Log a `llm_calls` row for every attempt with tokens, `cost_usd` (from `pricing.py`), and latency.

---

## 9. Insight Schemas (Pydantic)
- `Theme`, `BatchInsight`, `Recommendation`
- Guardrails: reject any output whose `example_record_ids` are not in the input batch.
- Merge call consolidates batch themes into final themes + `Recommendation` list. Each stored insight writes `insight_sources` rows from validated record IDs.

---

## 10. RAG
- **Chunking**: ~400 tokens, 60 overlap, sentence boundaries.
- **Embedding**: batch 64 texts per call via gateway; store in `chunks`.
- **Retrieval**: `ORDER BY embedding <=> :q LIMIT top_k` filtered by `tenant_id` and `dataset_id`. Default `top_k=8`.
- **Answering**: Answer only from numbered chunks, cite numbers, map citations back to `record_id`. If retrieved chunks lack answer, return `"insufficient evidence in this dataset"`.

---

## 11. Eval Harness
- `evals/labeled.jsonl`: ~50 records with `{id, text, gold_sentiment, gold_themes[]}`.
- `run_eval.py --prompt-version N --model X`: computes macro-F1 sentiment, theme match score (threshold 0.75), groundedness. Writes `eval_runs` row.

---

## 12. Build Order
1. Scaffold, Docker Compose, config, /health, Alembic base. *(Done)*
2. Schema migrations, auth, roles, tenant helper. *(Done)*
3. Dataset upload and validation. *(Done)*
4. **Job API, ARQ worker, state machine, retries. Test: forced failure retries 3 times then fails.** *(Current Step)*
5. Gateway (providers, cache, rate limit, fallback, cost logging).
6. Insight generation, schemas, lineage endpoint.
7. Chunking, embeddings, RAG /query.
8. Audit log and admin usage endpoints.
9. Eval harness.
10. Deploy, README with architecture diagram, DECISIONS.md, seeded demo tenants.

---

## 13. Acceptance Criteria
- **Isolation**: Cross-tenant queries return 404.
- **Jobs**: Idempotency key returns same job; retries 3 times on failure; progress reaches 100.
- **Gateway**: Fallback used on primary failure; cache hit skips provider call; rate limit returns 429.
- **Structured output**: Invalid JSON triggers re-ask; hallucinated record IDs rejected.
- **Lineage**: Insight returns source records, prompt version, model.
- **RAG**: Valid citations; unanswerable query returns "insufficient evidence".
- **Eval**: `run_eval.py` produces stored, comparable scores.
- **Ops**: `docker compose up` starts all services; `/health` returns 200.
