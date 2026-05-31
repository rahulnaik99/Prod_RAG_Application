import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents, health
from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def _run_migrations() -> None:
    """Run Alembic migrations at startup (safe for multiple replicas — Alembic uses a DB lock)."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run DB migrations (Alembic locks the DB, safe across replicas)
    await asyncio.to_thread(_run_migrations)

    redis = await get_redis()

    # Only run the drain worker on the first worker process to avoid duplicate processing.
    # In production with --workers N, each process runs lifespan independently.
    # We use a Redis SETNX lock so only one process becomes the drain worker owner.
    drain_task = None
    is_drain_owner = await redis.set("drain_worker_lock", "1", nx=True, ex=30)
    if is_drain_owner:
        from app.services.drain_worker import drain_worker
        drain_task = asyncio.create_task(_drain_with_lock_renewal(redis))
        logger.info("This worker process owns the drain worker")
    else:
        logger.info("Another worker process owns the drain worker — skipping")

    yield

    if drain_task:
        drain_task.cancel()
        try:
            await drain_task
        except asyncio.CancelledError:
            pass
        await redis.delete("drain_worker_lock")

    await redis.aclose()


async def _drain_with_lock_renewal(redis) -> None:
    """Run the drain worker and renew the Redis lock every 10s so it doesn't expire."""
    from app.services.drain_worker import drain_worker

    async def renew_lock():
        while True:
            await asyncio.sleep(10)
            await redis.expire("drain_worker_lock", 30)

    renew_task = asyncio.create_task(renew_lock())
    try:
        await drain_worker(redis)
    finally:
        renew_task.cancel()


app = FastAPI(
    title="RAG Application API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
