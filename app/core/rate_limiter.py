# © YAGA Project — Todos los derechos reservados
"""
Rate limiter por usuario_id respaldado en Valkey.
Complementa slowapi (rate limit por IP) con ventanas deslizantes
por identidad, usado para login y acciones sensibles.
"""
from fastapi import HTTPException

from core.redis import redis_client


async def check_user_rate_limit(
    usuario_id: str,
    action: str,
    max_attempts: int,
    window_seconds: int,
) -> int:
    """Incrementa el contador en Valkey y lanza 429 si excede el límite.

    Retorna el número actual de intentos dentro de la ventana.
    """
    key = f"ratelimit:{action}:{usuario_id}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, window_seconds)
    if current > max_attempts:
        ttl = await redis_client.ttl(key)
        if ttl < 0:
            ttl = window_seconds
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos. Espera {ttl}s.",
            headers={"Retry-After": str(ttl)},
        )
    return current


async def reset_user_rate_limit(usuario_id: str, action: str) -> None:
    """Limpia el contador tras una acción exitosa."""
    await redis_client.delete(f"ratelimit:{action}:{usuario_id}")
