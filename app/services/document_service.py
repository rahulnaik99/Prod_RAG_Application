"""
Document service — Azure Blob Storage.
Blob SDK calls are synchronous; we wrap them in asyncio.to_thread()
so they don't block the FastAPI event loop.
"""
import asyncio
import io

from azure.storage.blob import BlobServiceClient
from pypdf import PdfReader

from app.core.config import settings

_blob_client: BlobServiceClient | None = None


def _get_blob_client() -> BlobServiceClient:
    """Return (and lazily create) the shared synchronous BlobServiceClient."""
    global _blob_client
    if _blob_client is None:
        _blob_client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        container = _blob_client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
        if not container.exists():
            _blob_client.create_container(settings.AZURE_STORAGE_CONTAINER)
    return _blob_client


def _upload_sync(user_id: str, filename: str, content: bytes) -> str:
    """Blocking upload — always call via asyncio.to_thread()."""
    blob_path = f"users/{user_id}/documents/{filename}"
    client = _get_blob_client()
    blob = client.get_blob_client(
        container=settings.AZURE_STORAGE_CONTAINER, blob=blob_path
    )
    blob.upload_blob(content, overwrite=True)
    return blob_path


async def upload_to_blob(user_id: str, filename: str, content: bytes) -> str:
    """Async-safe upload to Azure Blob Storage. Returns blob path."""
    return await asyncio.to_thread(_upload_sync, user_id, filename, content)


# ── Text extraction & chunking (CPU-bound, also offloaded) ──────────────────

def extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_from_txt(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    step = chunk_size - overlap
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _process_sync(filename: str, content: bytes) -> list[str]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf(content)
    elif lower.endswith((".txt", ".md")):
        text = extract_text_from_txt(content)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    if not text.strip():
        raise ValueError("Document appears to be empty or unreadable")

    return chunk_text(text)


async def process_document(filename: str, content: bytes) -> list[str]:
    """Async-safe document processing (PDF parse + chunking offloaded to thread)."""
    return await asyncio.to_thread(_process_sync, filename, content)
