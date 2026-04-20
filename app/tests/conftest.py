# © YAGA Project — Todos los derechos reservados
"""
Fixtures compartidas. Sustituye `core.redis.redis_client` por una instancia
async de fakeredis para que refresh_service pueda ejecutarse sin Valkey real.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import fakeredis.aioredis


@pytest_asyncio.fixture
async def fake_redis(monkeypatch):
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    # Monkeypatch el cliente importado por refresh_service
    monkeypatch.setattr("services.refresh_service.redis_client", client)
    yield client
    await client.aclose()
