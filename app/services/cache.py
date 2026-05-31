import hashlib
import json
from typing import Optional

import redis.asyncio as aioredis


EMBED_TTL = 86_400      # 24 hours — embeddings are deterministic
ANSWER_TTL = 3_600      # 1 hour  — answers per user+question
RESULT_TTL = 300        # 5 min   — job results polling window


def _embed_key(text: str) -> str:
    digest = hashlib.md5(text.encode()).hexdigest()
    return f"embed:{digest}"


def _answer_key(user_id: str, question: str) -> str:
    digest = hashlib.md5(question.strip().lower().encode()).hexdigest()
    return f"answer:{user_id}:{digest}"


def _result_key(job_id: str) -> str:
    return f"result:{job_id}"


async def get_cached_embedding(
    redis: aioredis.Redis, text: str
) -> Optional[list[float]]:
    raw = await redis.get(_embed_key(text))
    if raw:
        return json.loads(raw)
    return None


async def cache_embedding(
    redis: aioredis.Redis, text: str, vector: list[float]
) -> None:
    await redis.set(_embed_key(text), json.dumps(vector), ex=EMBED_TTL)


async def get_cached_answer(
    redis: aioredis.Redis, user_id: str, question: str
) -> Optional[str]:
    return await redis.get(_answer_key(user_id, question))


async def cache_answer(
    redis: aioredis.Redis, user_id: str, question: str, answer: str
) -> None:
    await redis.set(_answer_key(user_id, question), answer, ex=ANSWER_TTL)


async def set_job_result(
    redis: aioredis.Redis, job_id: str, payload: dict
) -> None:
    await redis.set(_result_key(job_id), json.dumps(payload), ex=RESULT_TTL)


async def get_job_result(
    redis: aioredis.Redis, job_id: str
) -> Optional[dict]:
    raw = await redis.get(_result_key(job_id))
    if raw:
        return json.loads(raw)
    return None
