from arq.connections import RedisSettings
from app.config import settings

from app.worker.tasks import analyze_dataset

class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [analyze_dataset]
