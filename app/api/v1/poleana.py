# © YAGA Project — Todos los derechos reservados
"""
POLEANA — Router REST + WebSocket para partidas en línea

Migración Sprint 5-D.1: rooms persistidas en Redis (TTL 24h).
Conexiones WebSocket se mantienen en memoria (_connections) ya que
no son serializables; Redis almacena el estado serializable de cada sala.
"""
import json
import random
import string
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from services.database import get_pool
from services.auth_service import hash_password, verify_password, create_token, decode_token
from core.redis import redis_client

router = APIRouter(prefix="/api/v1/poleana", tags=["Poleana"])

# ─── WebSocket connections (local — no serializable) ─────────────────────────
# { code: [{"username": str, "color": int, "ws": WebSocket}] }
_connections: dict = {}

COLORS = ["#00e5a0", "#ff4444", "#4488ff", "#ffd700"]
ROOM_PREFIX = "poleana:room:"
ROOM_TTL = 86400  # 24h


def _gen_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


# ─── Redis helpers ────────────────────────────────────────────────────────────

async def _get_room_meta(code: str) -> dict | None:
    """Lee metadatos de la sala desde Redis. Retorna None si no existe."""
    raw = await redis_client.get(f"{ROOM_PREFIX}{code}")
    if not raw:
        return None
    return json.loads(raw)


async def _set_room_meta(code: str, meta: dict) -> None:
    """Persiste metadatos de la sala en Redis con TTL de 24h."""
    await redis_client.setex(f"{ROOM_PREFIX}{code}", ROOM_TTL, json.dumps(meta))


async def _del_room_meta(code: str) -> None:
    """Elimina la sala de Redis."""
    await redis_client.delete(f"{ROOM_PREFIX}{code}")


async def _room_exists(code: str) -> bool:
    """Retorna True si la sala existe en Redis."""
    return bool(await redis_client.exists(f"{ROOM_PREFIX}{code}"))


# ─── Models ──────────────────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    username: str
    password: str


class LoginBody(BaseModel):
    username: str
    password: str


class CreateGameBody(BaseModel):
    rules: str = "T"
    max_players: int = 4


# ─── Auth ────────────────────────────────────────────────────────────────────
@router.post("/register", status_code=201)
async def register(body: RegisterBody, pool=Depends(get_pool)):
    if not (3 <= len(body.username) <= 30):
        raise HTTPException(400, "Username debe tener entre 3 y 30 caracteres")
    if len(body.password) < 6:
        raise HTTPException(400, "Contraseña mínimo 6 caracteres")
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM poleana_users WHERE username = $1", body.username
        )
        if exists:
            raise HTTPException(400, "Username ya en uso")
        uid = await conn.fetchval(
            "INSERT INTO poleana_users (username, password_hash) VALUES ($1, $2) RETURNING id::text",
            body.username, hash_password(body.password),
        )
    token = create_token(uid, body.username)
    return {"token": token, "username": body.username}


@router.post("/login")
async def login(body: LoginBody, pool=Depends(get_pool)):
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, password_hash FROM poleana_users WHERE username = $1", body.username
        )
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    token = create_token(str(user["id"]), body.username)
    return {"token": token, "username": body.username}


@router.get("/stats/{username}")
async def stats(username: str, pool=Depends(get_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, wins, losses, games_played, created_at FROM poleana_users WHERE username = $1",
            username,
        )
    if not row:
        raise HTTPException(404, "Usuario no encontrado")
    return dict(row)


# ─── Game rooms ───────────────────────────────────────────────────────────────
@router.post("/games")
async def create_game(body: CreateGameBody, pool=Depends(get_pool)):
    code = _gen_code()
    while await _room_exists(code):
        code = _gen_code()

    meta = {
        "rules": body.rules,
        "max": body.max_players,
        "started": False,
        "state": None,
        "players_meta": [],  # [{"username": str, "color": int}]
    }
    await _set_room_meta(code, meta)

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO poleana_games (code, rules, max_players) VALUES ($1, $2, $3)",
            code, body.rules, body.max_players,
        )
    return {"code": code, "rules": body.rules, "max_players": body.max_players}


@router.get("/games/{code}")
async def get_game(code: str):
    meta = await _get_room_meta(code.upper())
    if not meta:
        raise HTTPException(404, "Sala no encontrada o expirada")
    return {
        "code": code.upper(),
        "rules": meta["rules"],
        "max_players": meta["max"],
        "players": meta["players_meta"],
        "started": meta["started"],
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────
@router.websocket("/ws/{code}")
async def ws_game(websocket: WebSocket, code: str, token: str = ""):
    code = code.upper()
    meta = await _get_room_meta(code)
    if not meta:
        await websocket.close(code=4004, reason="Sala no encontrada")
        return

    # Decode token → username stored in "email" field by auth_service
    username = None
    if token:
        try:
            payload = decode_token(token)
            username = payload.get("email")
        except Exception:
            pass
    if not username:
        await websocket.close(code=4001, reason="Token inválido")
        return

    conns = _connections.setdefault(code, [])

    if meta["started"] and not any(p["username"] == username for p in meta["players_meta"]):
        await websocket.close(code=4003, reason="Partida ya iniciada")
        return

    if len(conns) >= meta["max"] and not any(p["username"] == username for p in conns):
        await websocket.close(code=4002, reason="Sala llena")
        return

    await websocket.accept()

    # Rejoin or new join
    existing_conn = next((p for p in conns if p["username"] == username), None)
    if existing_conn:
        existing_conn["ws"] = websocket
        color_idx = existing_conn["color"]
    else:
        color_idx = len(conns)
        conns.append({"username": username, "color": color_idx, "ws": websocket})
        # Actualizar players_meta en Redis si es jugador nuevo
        if not any(p["username"] == username for p in meta["players_meta"]):
            meta["players_meta"].append({"username": username, "color": color_idx})
            await _set_room_meta(code, meta)

    # Enviar estado actual al jugador que (re)conecta
    if meta["state"]:
        await websocket.send_text(json.dumps({"type": "STATE", "state": meta["state"], "actor": None}))

    await _broadcast(conns, {
        "type": "JOINED",
        "username": username,
        "color": COLORS[color_idx],
        "color_idx": color_idx,
        "count": len(conns),
        "max": meta["max"],
        "players": meta["players_meta"],
    })

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "START" and not meta["started"]:
                if len(conns) < 2:
                    await websocket.send_text(json.dumps({"type": "ERROR", "msg": "Mínimo 2 jugadores"}))
                    continue
                meta["started"] = True
                await _set_room_meta(code, meta)
                await _broadcast(conns, {
                    "type": "GAME_START",
                    "rules": meta["rules"],
                    "players": meta["players_meta"],
                })

            elif mtype == "STATE":
                state = msg.get("state", {})
                turn = state.get("turn", 0)
                if turn < len(meta["players_meta"]) and meta["players_meta"][turn]["username"] != username:
                    await websocket.send_text(json.dumps({"type": "ERROR", "msg": "No es tu turno"}))
                    continue
                meta["state"] = state
                await _set_room_meta(code, meta)
                await _broadcast_except(conns, websocket, {
                    "type": "STATE",
                    "state": state,
                    "actor": username,
                })

            elif mtype == "CHAT":
                text = str(msg.get("text", ""))[:200]
                await _broadcast(conns, {"type": "CHAT", "username": username, "text": text})

            elif mtype == "GAME_OVER":
                winner = msg.get("winner", "")
                meta["started"] = False
                meta["state"] = None
                await _set_room_meta(code, meta)
                await _broadcast(conns, {"type": "GAME_OVER", "winner": winner})

    except WebSocketDisconnect:
        pass
    finally:
        # Marcar ws como None para permitir rejoin
        for p in conns:
            if p["ws"] is websocket:
                p["ws"] = None
        active = [p for p in conns if p["ws"] is not None]
        if not active:
            _connections.pop(code, None)
            await _del_room_meta(code)
        else:
            await _broadcast(conns, {"type": "LEFT", "username": username, "count": len(active)})


async def _broadcast(conns: list, msg: dict):
    payload = json.dumps(msg)
    for p in conns:
        if p["ws"]:
            try:
                await p["ws"].send_text(payload)
            except Exception:
                p["ws"] = None


async def _broadcast_except(conns: list, exclude: WebSocket, msg: dict):
    payload = json.dumps(msg)
    for p in conns:
        if p["ws"] and p["ws"] is not exclude:
            try:
                await p["ws"].send_text(payload)
            except Exception:
                p["ws"] = None
