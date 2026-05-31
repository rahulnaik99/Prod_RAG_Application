"""
Weaviate Cloud — multi-tenancy per user_id.
Weaviate client is synchronous; all calls are wrapped in asyncio.to_thread()
so they never block the FastAPI event loop.
"""
import asyncio
import uuid
from typing import Optional

import weaviate
import weaviate.classes as wvc
from weaviate.auth import AuthApiKey
from weaviate.exceptions import UnexpectedStatusCodeError

from app.core.config import settings

_client: Optional[weaviate.WeaviateClient] = None


def _get_client() -> weaviate.WeaviateClient:
    global _client
    if _client is None or not _client.is_connected():
        _client = weaviate.connect_to_weaviate_cloud(
            cluster_url=settings.WEAVIATE_URL,
            auth_credentials=AuthApiKey(settings.WEAVIATE_API_KEY),
        )
        _ensure_schema_exists(_client)
    return _client


def _ensure_schema_exists(client: weaviate.WeaviateClient) -> None:
    collection_name = settings.WEAVIATE_CLASS_NAME
    if not client.collections.exists(collection_name):
        client.collections.create(
            name=collection_name,
            multi_tenancy_config=wvc.config.Configure.multi_tenancy(enabled=True),
            properties=[
                wvc.config.Property(
                    name="text",
                    data_type=wvc.config.DataType.TEXT,
                ),
                wvc.config.Property(
                    name="filename",
                    data_type=wvc.config.DataType.TEXT,
                    skip_vectorization=True,
                ),
                wvc.config.Property(
                    name="chunk_index",
                    data_type=wvc.config.DataType.INT,
                    skip_vectorization=True,
                ),
            ],
            vectorizer_config=wvc.config.Configure.Vectorizer.none(),
        )


def _ensure_tenant(client: weaviate.WeaviateClient, user_id: str) -> None:
    collection = client.collections.get(settings.WEAVIATE_CLASS_NAME)
    try:
        collection.tenants.create(tenants=[wvc.tenants.Tenant(name=user_id)])
    except UnexpectedStatusCodeError:
        pass  # Tenant already exists


# ── Sync implementations (always called via asyncio.to_thread) ──────────────

def _store_chunks_sync(
    user_id: str,
    filename: str,
    chunks: list[str],
    vectors: list[list[float]],
) -> int:
    client = _get_client()
    _ensure_tenant(client, user_id)
    collection = client.collections.get(settings.WEAVIATE_CLASS_NAME)
    tenant_collection = collection.with_tenant(user_id)

    with tenant_collection.batch.dynamic() as batch:
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            batch.add_object(
                properties={"text": chunk, "filename": filename, "chunk_index": i},
                vector=vector,
                uuid=str(uuid.uuid4()),
            )
    return len(chunks)


def _search_documents_sync(
    user_id: str,
    query_vector: list[float],
    top_k: int = 5,
) -> list[str]:
    client = _get_client()
    collection = client.collections.get(settings.WEAVIATE_CLASS_NAME)
    tenant_collection = collection.with_tenant(user_id)
    results = tenant_collection.query.near_vector(
        near_vector=query_vector,
        limit=top_k,
        return_properties=["text"],
    )
    return [obj.properties["text"] for obj in results.objects]


# ── Public async API ────────────────────────────────────────────────────────

async def store_chunks(
    user_id: str,
    filename: str,
    chunks: list[str],
    vectors: list[list[float]],
) -> int:
    return await asyncio.to_thread(_store_chunks_sync, user_id, filename, chunks, vectors)


async def search_documents(
    user_id: str,
    query_vector: list[float],
    top_k: int = 5,
) -> list[str]:
    return await asyncio.to_thread(_search_documents_sync, user_id, query_vector, top_k)
