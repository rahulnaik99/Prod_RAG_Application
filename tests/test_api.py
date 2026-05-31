import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    email = "test@example.com"
    password = "securepass123"

    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201
    assert r.json()["email"] == email

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "securepass123"}
    r1 = await client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/auth/register", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/auth/register", json={"email": "wrong@example.com", "password": "correct123"}
    )
    r = await client.post(
        "/auth/login", json={"email": "wrong@example.com", "password": "wrongpass"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    r = await client.post("/chat/ask", json={"question": "hello"})
    assert r.status_code == 403
