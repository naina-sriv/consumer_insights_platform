import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.db import dispose_engine
from app.routers import auth, datasets, health, jobs
from app.worker.queue import close_arq_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle resources (startup and shutdown)."""
    logger.info("Initializing Consumer Insights Platform services...")
    yield
    logger.info("Shutting down services and releasing resources...")
    await close_arq_pool()
    await dispose_engine()


app = FastAPI(
    title="Consumer Insights Platform",
    description="Multi-tenant platform that turns qualitative consumer data into structured, traceable AI insights.",
    version="1.0.0",
    lifespan=lifespan,
)

# Exception handlers ensuring uniform error contract
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request parameters or payload",
                "details": exc.errors(),
            }
        },
    )


# Register API Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(datasets.router, prefix="/api/v1/datasets", tags=["datasets"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
