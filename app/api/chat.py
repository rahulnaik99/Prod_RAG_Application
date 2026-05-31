import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.redis import get_redis
from app.core.security import get_current_user
from app.db.models import Conversation, Message
from app.db.session import get_db
from app.schemas.schemas import (
    ChatJobResponse,
    ChatRequest,
    ConversationResponse,
)
from app.services.cache import get_cached_answer, get_job_result
from app.services.drain_worker import enqueue
from app.services.openai_service import embed_text
from app.services.weaviate_service import search_documents

router = APIRouter()


@router.post("/ask", response_model=ChatJobResponse)
async def ask(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id: str = current_user["sub"]
    redis = await get_redis()

    # 1. Cache check — same user + same question within TTL
    cached_answer = await get_cached_answer(redis, user_id, payload.question)
    if cached_answer:
        conv_id = payload.conversation_id or str(uuid.uuid4())
        await _persist_messages(db, user_id, conv_id, payload.question, cached_answer)
        return ChatJobResponse(
            job_id=str(uuid.uuid4()),
            status="done",
            answer=cached_answer,
            conversation_id=conv_id,
            source="cache",
        )

    # 2. Embed query (cached in Redis)
    query_vector = await embed_text(payload.question)

    # 3. Retrieve relevant chunks from Weaviate (user-isolated tenant)
    chunks = search_documents(user_id=user_id, query_vector=query_vector, top_k=5)

    # 4. Ensure conversation exists
    conv_id = payload.conversation_id or str(uuid.uuid4())
    await _ensure_conversation(db, user_id, conv_id, payload.question)

    # 5. Push to leaky bucket queue
    job_id = await enqueue(
        redis=redis,
        user_id=user_id,
        question=payload.question,
        conversation_id=conv_id,
        chunks=chunks,
    )
    return ChatJobResponse(job_id=job_id, status="queued", conversation_id=conv_id)


@router.get("/result/{job_id}", response_model=ChatJobResponse)
async def poll_result(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id: str = current_user["sub"]
    redis = await get_redis()

    result = await get_job_result(redis, job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    # Persist messages to DB once the job is done
    if result["status"] == "done" and result.get("answer"):
        conv_id = result.get("conversation_id")
        question_key = f"job_question:{job_id}"
        question = await redis.get(question_key) or ""
        if conv_id and question:
            await _persist_messages(db, user_id, conv_id, question, result["answer"])

    return ChatJobResponse(
        job_id=job_id,
        status=result["status"],
        answer=result.get("answer"),
        conversation_id=result.get("conversation_id"),
        source=result.get("source"),
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id: str = current_user["sub"]
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id: str = current_user["sub"]
    conv = await db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .options(selectinload(Conversation.messages))
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


async def _ensure_conversation(
    db: AsyncSession, user_id: str, conv_id: str, question: str
) -> None:
    existing = await db.get(Conversation, conv_id)
    if not existing:
        title = question[:60] + ("..." if len(question) > 60 else "")
        db.add(Conversation(id=conv_id, user_id=user_id, title=title))
        await db.flush()


async def _persist_messages(
    db: AsyncSession,
    user_id: str,
    conv_id: str,
    question: str,
    answer: str,
) -> None:
    await _ensure_conversation(db, user_id, conv_id, question)
    db.add(Message(conversation_id=conv_id, role="user", content=question))
    db.add(Message(conversation_id=conv_id, role="assistant", content=answer))
    await db.flush()
