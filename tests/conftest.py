"""
pytest fixtures — mock all external dependencies so tests run
in CI without a real DB, Redis, Weaviate, or Azure Blob.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch


# ── Patch heavy startup work before the app module is imported ──────────────

@pytest.fixture(autouse=True, scope="session")
def mock_settings_env(tmp_path_factory):
    """Provide minimal env vars so pydantic-settings doesn't complain."""
    import os
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/testdb")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
    os.environ.setdefault(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
        "K1SZFPTOtr/KCo4HkGEsLJDHLAxlMJEHF6QOZ3iXKJEJBuiLhQ==;"
        "BlobEndpoint=http://localhost:10000/devstoreaccount1;",
    )
    os.environ.setdefault("WEAVIATE_URL", "https://test.weaviate.cloud")
    os.environ.setdefault("WEAVIATE_API_KEY", "test-key")
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")


@pytest.fixture(autouse=True)
def mock_migrations(monkeypatch):
    """Skip Alembic migrations during tests."""
    monkeypatch.setattr("app.main._run_migrations", lambda: None)


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Replace Redis with an in-memory async mock."""
    store: dict = {}

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=lambda k: store.get(k))
    redis_mock.set = AsyncMock(side_effect=lambda k, v, **_: store.update({k: v}))
    redis_mock.llen = AsyncMock(return_value=0)
    redis_mock.rpush = AsyncMock(return_value=1)
    redis_mock.lpop = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(side_effect=lambda *a, **kw: store.update({a[0]: a[1]}) or True)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.aclose = AsyncMock()

    async def fake_get_redis():
        return redis_mock

    monkeypatch.setattr("app.core.redis.get_redis", fake_get_redis)
    monkeypatch.setattr("app.core.redis._redis", redis_mock)
    return redis_mock


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """Replace SQLAlchemy async session with an in-memory mock."""
    from unittest.mock import AsyncMock, MagicMock

    # Simple in-memory user store for auth tests
    _users: dict = {}

    session_mock = AsyncMock()
    session_mock.add = MagicMock()
    session_mock.flush = AsyncMock()
    session_mock.commit = AsyncMock()
    session_mock.rollback = AsyncMock()
    session_mock.refresh = AsyncMock()

    async def fake_scalar(stmt):
        # Minimal support: detect User queries by email
        from app.db.models import User
        whereclause = stmt.whereclause
        if whereclause is not None:
            # Extract email value from the WHERE clause for login/register
            try:
                email_val = whereclause.right.value
                return _users.get(email_val)
            except AttributeError:
                pass
        return None

    async def fake_get(model, pk):
        from app.db.models import User
        if model is User:
            for u in _users.values():
                if u.id == pk:
                    return u
        return None

    def fake_add(obj):
        from app.db.models import User
        if isinstance(obj, User):
            _users[obj.email] = obj

    async def fake_flush():
        pass

    async def fake_refresh(obj):
        pass

    session_mock.scalar = fake_scalar
    session_mock.get = fake_get
    session_mock.add = fake_add
    session_mock.flush = fake_flush
    session_mock.refresh = fake_refresh

    async def fake_get_db():
        yield session_mock

    monkeypatch.setattr("app.db.session.get_db", fake_get_db)
    monkeypatch.setattr("app.api.auth.get_db", fake_get_db)
    monkeypatch.setattr("app.api.chat.get_db", fake_get_db)
    return session_mock


@pytest_asyncio.fixture
async def client():
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
