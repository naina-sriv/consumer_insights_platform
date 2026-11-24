from arq.connections import RedisSettings

from app.config import settings
from app.worker.tasks import analyze_dataset


class WorkerSettings:
    """ARQ Worker configuration."""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [analyze_dataset]
    max_jobs = 10
    poll_delay = 0.5
    job_timeout = 3600
