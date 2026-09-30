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

- [x] Step 1: scaffold, Docker Compose, config, /health, Alembic
- [ ] Step 2: schema, auth, roles, tenant-scoped queries
