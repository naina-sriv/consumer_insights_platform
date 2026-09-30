from fastapi import FastAPI

from app.routers import health

app = FastAPI(title="Consumer Insights Platform")
app.include_router(health.router, prefix="/api/v1")
