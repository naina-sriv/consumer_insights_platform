# PRD: Multi-Tenant Consumer Insights Platform
**Owner**: Naina | **Status**: Active (Phase 1 Build) | **Timeline**: 6 weeks | **Stack**: Python, FastAPI, Postgres + pgvector, Redis, Docker

---

## 1. Overview
A multi-tenant platform where brands upload consumer data (survey responses, product reviews, interview transcripts) and get AI-generated, explainable insights. Every insight is traceable to its source data, prompt version, and model.

**Purpose**: A production-style portfolio project demonstrating async AI workflows, LLM gateways, RAG, multi-tenancy, and auditability.

---

## 2. Problem
Brands hold large volumes of unstructured feedback but lack fast, trustworthy ways to extract themes and answers. AI outputs are often unauditable, so teams cannot trust them.

---

## 3. Goals and Non-Goals

### Goals
- Turn uploaded datasets into structured insights (themes, sentiment, recommendations).
- Answer natural-language questions over qualitative data with cited sources.
- Isolate tenant data strictly.
- Make every output auditable and measurable (eval harness).

### Non-Goals
- Polished frontend (minimal UI or Swagger docs is enough).
- Billing, SSO, custom model training.
- Analytics/dashboard layer (deferred to Phase 2, section 11a).
- Real-time streaming ingestion (Kafka is optional stretch).

---

## 4. Users & RBAC

| Role | Permissions & Needs |
| :--- | :--- |
| **Admin** | Manage tenant users, view audit log, inspect usage/cost metrics. |
| **Analyst** | Upload data, run jobs, ask natural language questions, review insights. |
| **Viewer** | Read insights and dashboards only (read-only). |

---

## 5. Functional Requirements (P0 / P1 / P2)

| ID | Requirement | Priority | Status in Codebase |
| :--- | :--- | :--- | :--- |
| **F1** | **Auth**: JWT login, roles (`admin`/`analyst`/`viewer`), tenant-scoped tokens | P0 | Implemented (`admin`/`analyst`; need `viewer` validation) |
| **F2** | **Tenant Isolation**: Every query filtered by `tenant_id` (`scoped()` helper) | P0 | Implemented & verified via `test_isolation.py` |
| **F3** | **Dataset Upload**: CSV/JSON/TXT schema validation, file size limit (20MB), max 20k rows, bulk row storage | P0 | Implemented (`POST /api/v1/datasets`) |
| **F4** | **Async Job Engine**: Enqueue analysis job, worker execution (ARQ), retries with backoff, status endpoint, live progress via SSE | P0 | In Progress (`app/worker/` stubs exist) |
| **F5** | **LLM Gateway**: Unified interface over 2 providers, fallback on error/timeout, Redis response cache, token/cost logging, per-tenant rate limits | P0 | Planned (`app/gateway/` stub) |
| **F6** | **Structured Insights**: Pydantic-validated JSON (themes, sentiment, recommendations); retry on invalid output | P0 | Planned |
| **F7** | **RAG Pipeline**: Chunk & embed text into `pgvector`, retrieval + answer synthesis with source citations | P0 | Planned (`chunks` model exists) |
| **F8** | **Lineage**: Each insight stores source row IDs (`insight_sources`), prompt version, model, timestamp | P0 | Planned (`insight_sources` table exists) |
| **F9** | **Audit Log**: Record uploads, job runs, queries, role changes | P1 | Table exists (`audit_log`) |
| **F10** | **Eval Harness**: Labeled benchmark set (~50 items), script scoring theme/sentiment accuracy and groundedness per prompt/model version | P0 | Planned (`evals/` directory exists) |
| **F11** | **Usage Dashboard Endpoint**: Tokens, cost, latency per tenant | P1 | Table exists (`llm_calls`) |
| **F12** | **Kafka Ingestion**: Behavioral events streaming | P2 | Stretch |

---

## 6. Key User Flows
1. **Analyze**: Analyst uploads dataset $\rightarrow$ `POST /jobs` $\rightarrow$ Worker chunks & calls gateway $\rightarrow$ Insights saved with lineage $\rightarrow$ Job marked completed.
2. **Ask**: Analyst sends natural language question $\rightarrow$ System retrieves top-$k$ chunks via cosine similarity $\rightarrow$ LLM answers with citations $\rightarrow$ Response returns source IDs.
3. **Audit**: Admin opens an insight $\rightarrow$ inspects exact source rows, prompt version, latency, token count, cost, and model used.

---

## 7. Architecture

```
Client -> FastAPI (auth, tenancy, API)
            |-> Postgres (data, pgvector, audit)
            |-> Redis (queue, cache, rate limits)
            '-> Worker (ARQ) -> LLM Gateway -> Primary / Fallback Provider
```

### Core Tables
- `tenants`
- `users`
- `datasets`
- `records`
- `chunks` (`pgvector`)
- `jobs`
- `insights`
- `insight_sources`
- `prompts` (versioned)
- `llm_calls`
- `audit_log`
- `eval_runs`

---

## 8. Non-Functional Requirements & Performance Targets
- **Reliability**: Jobs are idempotent; failed jobs retry $3\times$ with exponential backoff; provider fallback on failure.
- **Performance**: API p95 $< 300\text{ ms}$ (non-LLM); RAG answer $< 8\text{ s}$; cached repeat queries $< 100\text{ ms}$.
- **Security**: Hashed passwords (bcrypt), JWT expiry (60m), secrets via `.env`, strict multi-tenant isolation.
- **Observability**: Structured JSON logs, request IDs, per-call LLM cost/latency tracking.
- **Quality**: Eval score tracked per prompt/model version; regressions caught before deploy.

---

## 9. Phase 2: Data Analytics Layer (Post-Phase 1)
- **D1**: Dimensional modeling SQL views (`fact_reviews`, `fact_insights`, `dim_tenant`, `dim_product`, `dim_date`, `dim_theme`).
- **D2**: Analytics SQL pack (CTEs, window functions) for theme trends, sentiment by product segment, top complaint drivers.
- **D3**: Data quality report on upload (null rate, duplicates, schema violations).
- **D4**: Streamlit or Metabase dashboard.
- **D5**: Written case study with charts & recommendations.
- **D6**: LLM usage analytics.
