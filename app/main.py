from fastapi import FastAPI

from app.routers import health, auth, datasets, jobs

app = FastAPI(title="Consumer Insights Platform")
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(datasets.router, prefix="/api/v1/datasets", tags=["datasets"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
