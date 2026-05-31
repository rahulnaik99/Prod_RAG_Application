"""
Leaky Bucket Rate Limiter
─────────────────────────
- Requests go into a Redis LIST (the bucket)
- drain_worker() pops one item every DRAIN_RATE seconds (the leak)
- If the bucket exceeds MAX_SIZE the caller gets 429 immediately
- OpenAI never sees traffic bursts — only a steady drip
"""

import asyncio
import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import HTTPException

from app.core.config import settings
from app.services.cache import cache_answer, set_job_result
from app.services.openai_service import call_openai_chat

logger = logging.getLogger(__name__)

QUEUE_KEY = "openai_queue"
QUESTION_KEY_TTL = 600  # 10 min — enough for polling window + buffer


async def enqueue(
    redis: aioredis.Redis,
    user_id: str,
    question: str,
    conversation_id: str,
    chunks: list[str],
) -> str:
    """Push a job onto the leaky bucket queue. Returns job_id."""
    queue_len = await redis.llen(QUEUE_KEY)
    if queue_len >= settings.OPENAI_QUEUE_MAX_SIZE:
        raise HTTPException(
            status_code=429,
            detail="Server is busy. Please try again in a few seconds.",
            headers={"Retry-After": "5"},
        )

    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "user_id": user_id,
        "question": question,
        "conversation_id": conversation_id,
        "chunks": chunks,
    }
    await redis.rpush(QUEUE_KEY, json.dumps(payload))
    await set_job_result(redis, job_id, {"status": "queued"})

    # FIX: store the question so poll_result can persist messages to DB
    await redis.set(f"job_question:{job_id}", question, ex=QUESTION_KEY_TTL)

    return job_id


async def drain_worker(redis: aioredis.Redis) -> None:
    """
    Background task — the 'leak' in the leaky bucket.
    Pops one job per DRAIN_RATE seconds and calls OpenAI.
    """
    logger.info("Drain worker started at %.1fs per request", settings.OPENAI_DRAIN_RATE_SECONDS)
    while True:
        try:
            raw = await redis.lpop(QUEUE_KEY)
            if raw:
                payload = json.loads(raw)
                job_id = payload["job_id"]
                await set_job_result(redis, job_id, {"status": "processing"})

                try:
                    answer = await call_openai_chat(
                        question=payload["question"],
                        chunks=payload["chunks"],
                    )
                    await cache_answer(
                        redis,
                        user_id=payload["user_id"],
                        question=payload["question"],
                        answer=answer,
                    )
                    await set_job_result(
                        redis,
                        job_id,
                        {
                            "status": "done",
                            "answer": answer,
                            "conversation_id": payload["conversation_id"],
                            "source": "openai",
                        },
                    )
                except Exception as exc:
                    logger.error("OpenAI call failed for job %s: %s", job_id, exc)
                    await set_job_result(
                        redis,
                        job_id,
                        {"status": "error", "answer": "Sorry, something went wrong. Please retry."},
                    )
        except asyncio.CancelledError:
            logger.info("Drain worker shutting down")
            break
        except Exception as exc:
            logger.error("Drain worker error: %s", exc)

        await asyncio.sleep(settings.OPENAI_DRAIN_RATE_SECONDS)
