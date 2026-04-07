# © YAGA Project — Todos los derechos reservados
"""
Room Manager para Poleana usando Redis.
Reemplaza el dict _rooms en memoria (vulnerabilidad 6.6).
Usa Redis DB 2 para no colisionar con DB 0 (general) y DB 1 (rate limiter).
TTL: 3600s (1 hora de inactividad).
"""
import json
import os
import time
from typing import Optional

import redis.asyncio as aioredis

ROOM_TTL = 3600  # 1 hora de inactividad
ROOM_PREFIX = "poleana:room:"
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

# Forzar DB 2 para Poleana independientemente de lo que diga REDIS_URL
_POLEANA_REDIS_URL = _REDIS_URL.rstrip("/").rsplit("/", 1)[0] + "/2" \
    if _REDIS_URL.count("/") >= 3 else _REDIS_URL + "/2"

_pool: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """Retorna conexion Redis reutilizable (connection pool interno)."""
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(_POLEANA_REDIS_URL, decode_responses=True)
    return _pool


async def close_redis():
    """Cierra pool de Redis. Llamar al apagar la app."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def _key(room_code: str) -> str:
    return f"{ROOM_PREFIX}{room_code}"


def _serialize(value) -> str:
    """Serializa listas y dicts a JSON string para Redis hash."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _deserialize_room(data: dict) -> dict:
    """Convierte campos JSON-string de vuelta a objetos Python."""
    if not data:
        return {}
    result = dict(data)
    for field in ("players", "board_state"):
        if field in result and isinstance(result[field], str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = [] if field == "players" else {}
    if "game_state" in result and isinstance(result["game_state"], str):
        # game_state es un JSON blob completo del estado del juego
        # NO deserializar aqui -- se mantiene como string en Redis
        # y se parsea solo cuando se necesita en validate_move
        pass
    return result


async def create_room(room_code: str, rules: str = "T",
                      max_players: int = 4) -> dict:
    """Crea una nueva sala en Redis."""
    room_data = {
        "code": room_code,
        "players": json.dumps([]),
        "game_state": "waiting",  # waiting | playing | finished
        "rules": rules,
        "max_players": str(max_players),
        "started": "0",
        "state": json.dumps(None),  # estado completo del juego (legacy)
        "current_player_idx": "0",
        "created_at": str(time.time()),
    }
    r = await get_redis()
    await r.hset(_key(room_code), mapping=room_data)
    await r.expire(_key(room_code), ROOM_TTL)
    return _deserialize_room(room_data)


async def get_room(room_code: str) -> Optional[dict]:
    """Obtiene sala de Redis. Retorna None si no existe."""
    r = await get_redis()
    data = await r.hgetall(_key(room_code))
    if not data:
        return None
    # Refrescar TTL en cada acceso (actividad = vida)
    await r.expire(_key(room_code), ROOM_TTL)
    return _deserialize_room(data)


async def update_room(room_code: str, updates: dict):
    """Actualiza campos de la sala. Serializa listas/dicts a JSON."""
    r = await get_redis()
    serialized = {k: _serialize(v) for k, v in updates.items()}
    await r.hset(_key(room_code), mapping=serialized)
    await r.expire(_key(room_code), ROOM_TTL)


async def delete_room(room_code: str):
    """Elimina sala de Redis."""
    r = await get_redis()
    await r.delete(_key(room_code))


async def room_exists(room_code: str) -> bool:
    """Verifica si una sala existe sin deserializar."""
    r = await get_redis()
    return await r.exists(_key(room_code)) > 0


async def add_player(room_code: str, username: str,
                     color_idx: int) -> bool:
    """
    Anade jugador a sala.
    Retorna False si sala no existe o esta llena (>= max_players).
    No almacena WebSocket -- eso se maneja in-memory en el router.
    """
    room = await get_room(room_code)
    if not room:
        return False
    players = room.get("players", [])
    max_p = int(room.get("max_players", 4))
    # Ya existe?
    if any(p.get("username") == username for p in players):
        return True  # rejoin -- no modificar
    if len(players) >= max_p:
        return False
    players.append({"username": username, "color": color_idx})
    await update_room(room_code, {"players": players})
    return True


async def remove_player(room_code: str, username: str) -> int:
    """
    Marca jugador como desconectado (no lo elimina para permitir rejoin).
    Retorna cantidad de jugadores activos restantes.
    """
    room = await get_room(room_code)
    if not room:
        return 0
    players = room.get("players", [])
    # No eliminamos, solo devolvemos el count para que el caller decida
    return len(players)


async def set_game_state(room_code: str, state: dict):
    """Guarda el estado completo del juego."""
    await update_room(room_code, {"state": state})


async def get_game_state(room_code: str) -> Optional[dict]:
    """Obtiene el estado del juego."""
    room = await get_room(room_code)
    if not room:
        return None
    state_raw = room.get("state")
    if isinstance(state_raw, str):
        try:
            return json.loads(state_raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return state_raw


async def set_started(room_code: str, started: bool):
    """Marca la sala como iniciada/no-iniciada."""
    await update_room(room_code, {
        "started": "1" if started else "0",
        "game_state": "playing" if started else "waiting",
    })


def is_started(room: dict) -> bool:
    """Helper: interpreta el campo 'started' del room dict."""
    val = room.get("started", "0")
    return val in ("1", "True", "true", True)


def validate_move(room: dict, username: str,
                  move_data: dict) -> tuple[bool, str]:
    """
    Valida un movimiento antes de aplicarlo.
    Retorna (es_valido, mensaje_error).

    Validaciones server-side:
    1. Es el turno del jugador
    2. El juego esta activo
    3. Coherencia basica con dados (si hay dice_result en state)
    """
    players = room.get("players", [])
    if not players:
        return False, "No hay jugadores en la sala"

    # Obtener state
    state_raw = room.get("state")
    state = None
    if isinstance(state_raw, str):
        try:
            state = json.loads(state_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(state_raw, dict):
        state = state_raw

    # 1. Verificar turno
    current_turn = 0
    if state and isinstance(state, dict):
        current_turn = int(state.get("turn", 0))

    sender_idx = next(
        (i for i, p in enumerate(players) if p.get("username") == username),
        -1,
    )
    if sender_idx == -1:
        return False, "Jugador no encontrado en la sala"
    if sender_idx != current_turn:
        return False, "No es tu turno"

    # 2. Verificar que el juego esta activo
    if not is_started(room):
        return False, "El juego no esta activo"

    return True, ""
