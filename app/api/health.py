from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("")
async def health():
    return {"status": "ok", "env": settings.APP_ENV, "cloud": "azure"}
