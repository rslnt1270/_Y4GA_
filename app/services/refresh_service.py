# © YAGA Project — Todos los derechos reservados
"""
services/refresh_service.py — Refresh tokens con rotación en Valkey (Sprint 10).

Store: Valkey (vía core.redis.redis_client, decode_responses=True → strings).

Schema:
    refresh:<token_id>    Hash  {usuario_id, familia_id, emitido_en,
                                 expira_en_sliding, cap_absoluto, ip,
                                 user_agent, rotated_to}
                          TTL   30 días (60 s tras rotar, para carreras)

    familia:<familia_id>  Hash  {usuario_id, creado_en, cap_absoluto,
                                 revocada, motivo}
                          TTL   60 días (cap absoluto de la familia)

    idx_usuario:<uid>     Set<familia_id>
                          TTL   60 días (se refresca al crear familia)

Política:
    - Sliding window: cada rotación extiende el TTL a min(30d, cap_absoluto).
    - Cap absoluto: 60 días desde el login inicial — no se mueve con rotación.
    - Reuse detection: si un token con `rotated_to` seteado vuelve a usarse,
      se revoca la familia completa (motivo="reuse_detected").
    - Logout: borra el token actual; otras familias del usuario siguen vivas.
    - Revocación global por usuario: para reset_password y /arco/rectificacion.

Este servicio NO escribe en `auditoria`. Los callers (endpoints) registran el
evento vía services.audit_service.log_action con el motivo específico.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.redis import redis_client

REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 3600   # sliding por token
FAMILIA_CAP_SECONDS       = 60 * 24 * 3600   # cap absoluto por familia
ROTATED_TTL_SECONDS       = 60               # entry rotado sobrevive 60 s


class RefreshTokenError(Exception):
    """Cualquier fallo → el endpoint responde 401 sin exponer el motivo."""


class ReuseDetected(RefreshTokenError):
    """El mismo token se usó 2 veces: la familia fue revocada."""


def _new_token_id() -> str:
    # 32 bytes → 43 chars URL-safe. No es UUID (evita confusión con PKs de DB).
    return secrets.token_urlsafe(32)


def _k_refresh(tid: str) -> str:  return f"refresh:{tid}"
def _k_familia(fid: str) -> str:  return f"familia:{fid}"
def _k_idx_user(uid: str) -> str: return f"idx_usuario:{uid}"


@dataclass
class RefreshEmission:
    token_id: str
    familia_id: str
    usuario_id: str
    expira_en_sliding: datetime
    cap_absoluto: datetime

    @property
    def ttl_cookie_seconds(self) -> int:
        delta = self.expira_en_sliding - datetime.now(tz=timezone.utc)
        return max(int(delta.total_seconds()), 1)


# ── API pública ───────────────────────────────────────────────────────────────

async def create_refresh_token(
    usuario_id: str,
    ip: str,
    user_agent: str,
) -> RefreshEmission:
    """Nuevo login/register: crea familia + primer token."""
    token_id   = _new_token_id()
    familia_id = str(uuid.uuid4())
    ahora      = datetime.now(tz=timezone.utc)
    sliding    = ahora + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)
    cap        = ahora + timedelta(seconds=FAMILIA_CAP_SECONDS)

    async with redis_client.pipeline(transaction=False) as pipe:
        pipe.hset(_k_familia(familia_id), mapping={
            "usuario_id":   usuario_id,
            "creado_en":    ahora.isoformat(),
            "cap_absoluto": cap.isoformat(),
            "revocada":     "0",
            "motivo":       "",
            "ip":           ip or "",
            "user_agent":   (user_agent or "")[:512],
        })
        pipe.expire(_k_familia(familia_id), FAMILIA_CAP_SECONDS)

        pipe.hset(_k_refresh(token_id), mapping={
            "usuario_id":        usuario_id,
            "familia_id":        familia_id,
            "emitido_en":        ahora.isoformat(),
            "expira_en_sliding": sliding.isoformat(),
            "cap_absoluto":      cap.isoformat(),
            "ip":                ip or "",
            "user_agent":        (user_agent or "")[:512],
            "rotated_to":        "",
        })
        pipe.expire(_k_refresh(token_id), REFRESH_TOKEN_TTL_SECONDS)

        pipe.sadd(_k_idx_user(usuario_id), familia_id)
        pipe.expire(_k_idx_user(usuario_id), FAMILIA_CAP_SECONDS)

        await pipe.execute()

    return RefreshEmission(token_id, familia_id, usuario_id, sliding, cap)


async def validate_and_rotate(
    token_id: str,
    ip: str,
    user_agent: str,
) -> RefreshEmission:
    """
    Valida el refresh y emite un nuevo token en la misma familia.
    Raise RefreshTokenError/ReuseDetected — el endpoint traduce todo a 401.
    """
    if not token_id:
        raise RefreshTokenError("empty_token")

    data = await redis_client.hgetall(_k_refresh(token_id))
    if not data:
        raise RefreshTokenError("not_found")

    # Reuse detection: este token ya se rotó antes
    if data.get("rotated_to"):
        familia_id = data.get("familia_id", "")
        if familia_id:
            await _mark_family_revoked(familia_id, motivo="reuse_detected")
        raise ReuseDetected("reuse")

    familia_id = data["familia_id"]
    usuario_id = data["usuario_id"]

    familia = await redis_client.hgetall(_k_familia(familia_id))
    if not familia or familia.get("revocada") == "1":
        raise RefreshTokenError("familia_revocada")

    cap = datetime.fromisoformat(familia["cap_absoluto"])
    ahora = datetime.now(tz=timezone.utc)
    if ahora >= cap:
        raise RefreshTokenError("cap_expirado")

    new_tid = _new_token_id()
    sliding = min(ahora + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS), cap)
    ttl_nuevo = max(int((sliding - ahora).total_seconds()), 1)

    async with redis_client.pipeline(transaction=False) as pipe:
        pipe.hset(_k_refresh(new_tid), mapping={
            "usuario_id":        usuario_id,
            "familia_id":        familia_id,
            "emitido_en":        ahora.isoformat(),
            "expira_en_sliding": sliding.isoformat(),
            "cap_absoluto":      cap.isoformat(),
            "ip":                ip or "",
            "user_agent":        (user_agent or "")[:512],
            "rotated_to":        "",
        })
        pipe.expire(_k_refresh(new_tid), ttl_nuevo)

        # El viejo queda marcado rotated_to=nuevo, TTL 60 s (reintentos en carrera)
        pipe.hset(_k_refresh(token_id), "rotated_to", new_tid)
        pipe.expire(_k_refresh(token_id), ROTATED_TTL_SECONDS)

        await pipe.execute()

    return RefreshEmission(new_tid, familia_id, usuario_id, sliding, cap)


async def revoke_token(token_id: str) -> Optional[str]:
    """
    Logout puntual: borra este token. Retorna usuario_id para auditoría,
    o None si el token ya no existía. Otras familias del usuario NO se tocan.
    """
    if not token_id:
        return None
    usuario_id = await redis_client.hget(_k_refresh(token_id), "usuario_id")
    await redis_client.delete(_k_refresh(token_id))
    return usuario_id


async def revoke_family(familia_id: str, motivo: str) -> None:
    """Revoca una familia específica."""
    if not familia_id:
        return
    await _mark_family_revoked(familia_id, motivo=motivo)


async def revoke_all_families_for_user(usuario_id: str, motivo: str) -> int:
    """
    Revoca todas las familias activas del usuario.
    Usos: reset_password (Sprint 10), /arco/rectificacion (Sprint 11+).
    Retorna el número de familias revocadas.
    """
    if not usuario_id:
        return 0
    familias = await redis_client.smembers(_k_idx_user(usuario_id)) or set()
    for fid in familias:
        await _mark_family_revoked(fid, motivo=motivo)
    return len(familias)


async def list_families_for_user(usuario_id: str) -> list[dict]:
    """Lista familias activas del usuario para el panel ARCO de sesiones."""
    familias_ids = await redis_client.smembers(_k_idx_user(usuario_id)) or set()
    result = []
    for fid in familias_ids:
        data = await redis_client.hgetall(_k_familia(fid))
        if not data or data.get("revocada") == "1":
            continue
        ua = data.get("user_agent", "")
        result.append({
            "familia_id":          fid,
            "creado_en":           data.get("creado_en", ""),
            "ip":                  data.get("ip", ""),
            "user_agent_resumido": ua[:80] if ua else "",
        })
    result.sort(key=lambda x: x["creado_en"], reverse=True)
    return result


async def _mark_family_revoked(familia_id: str, motivo: str) -> None:
    await redis_client.hset(_k_familia(familia_id), mapping={
        "revocada": "1",
        "motivo":   (motivo or "")[:64],
    })
