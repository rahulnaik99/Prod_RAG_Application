from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.core.security import get_current_user
from app.schemas.schemas import DocumentUploadResponse
from app.services.document_service import process_document, upload_to_blob
from app.services.openai_service import embed_text
from app.services.weaviate_service import store_chunks

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = (".pdf", ".txt", ".md")


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile,
    current_user: dict = Depends(get_current_user),
):
    user_id: str = current_user["sub"]

    if not (file.filename or "").lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload PDF, TXT, or MD files.",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    # 1. Store raw file in Azure Blob Storage (async-safe)
    await upload_to_blob(user_id, file.filename, content)

    # 2. Extract text and split into chunks (async-safe)
    try:
        chunks = await process_document(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 3. Embed each chunk (cached in Redis automatically)
    vectors = [await embed_text(chunk) for chunk in chunks]

    # 4. Store in Weaviate under user's isolated tenant (async-safe)
    stored = await store_chunks(
        user_id=user_id,
        filename=file.filename,
        chunks=chunks,
        vectors=vectors,
    )

    return DocumentUploadResponse(
        filename=file.filename,
        chunks_stored=stored,
        message=f"Successfully indexed {stored} chunks from {file.filename}",
    )
