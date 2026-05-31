from openai import AsyncOpenAI

from app.core.config import settings
from app.core.redis import get_redis
from app.services.cache import cache_embedding, get_cached_embedding

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def embed_text(text: str) -> list[float]:
    """Returns embedding, served from Redis cache when available."""
    redis = await get_redis()
    cached = await get_cached_embedding(redis, text)
    if cached:
        return cached

    response = await get_openai_client().embeddings.create(
        model=settings.OPENAI_EMBED_MODEL,
        input=text,
    )
    vector = response.data[0].embedding
    await cache_embedding(redis, text, vector)
    return vector


async def call_openai_chat(question: str, chunks: list[str]) -> str:
    """Build RAG prompt from retrieved chunks and get GPT answer."""
    context = "\n\n---\n\n".join(chunks) if chunks else "No relevant documents found."

    system_prompt = (
        "You are a helpful assistant that answers questions based only on the "
        "provided document context. If the answer is not in the context, say so clearly. "
        "Do not make up information."
    )
    user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

    response = await get_openai_client().chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1024,
        temperature=0.2,
    )
    return response.choices[0].message.content
