"""
YAGA PROJECT - Conexión a PostgreSQL
Copyright (c) 2026 YAGA Project
"""
import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://yaga_user:Yaga2026SecurePass@localhost:5432/yaga_db")

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
