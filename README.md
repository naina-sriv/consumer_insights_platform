# Consumer Insights Platform

Multi-tenant platform that turns uploaded consumer data into structured, traceable AI insights.
See the PRD and Technical Spec for scope. Build order is in spec section 11.

## Run

    cp .env.example .env
    docker compose up --build
    curl localhost:8000/api/v1/health

## Test

    pip install -r requirements.txt
    pytest

## Status

- [x] Step 1: scaffold, Docker Compose, config, /health, Alembic base
- [x] Step 2: schema migrations, auth, roles, tenant helper
- [x] Step 3: dataset upload and validation
- [x] Step 4: job API, ARQ worker, state machine, retries
- [ ] Step 5: gateway (providers, cache, rate limit, fallback, cost logging)
- [ ] Step 6: insight generation, schemas, lineage endpoint
- [ ] Step 7: chunking, embeddings, RAG /query
- [ ] Step 8: audit log and admin usage endpoints
- [ ] Step 9: eval harness
- [ ] Step 10: deploy, README with architecture diagram, DECISIONS.md, seeded demo tenants
