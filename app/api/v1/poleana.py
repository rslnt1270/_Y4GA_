# © YAGA Project — Todos los derechos reservados
"""
POLEANA — Router REST + WebSocket para partidas en linea.
v2.0: Rooms en Redis (vuln 6.6) + validacion server-side (vuln 6.5).
"""
import asyncio
import json
import logging
import random
import string
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from api.poleana_redis_rooms import (
    create_room,
    get_room,
    update_room,
    delete_room,
    add_player,
    room_exists,
    set_game_state,
    set_started,
    is_started,
    validate_move,
    close_redis,
)
from services.database import get_pool
from services.auth_service import hash_password, verify_password, create_token, decode_token

logger = logging.getLogger("poleana")

router = APIRouter(prefix="/api/v1/poleana", tags=["Poleana"])

# ─── In-memory: solo WebSocket refs (no serializables) ──────────────────────
# { room_code: { username: WebSocket } }
_ws_connections: dict[str, dict[str, Optional[WebSocket]]] = {}

COLORS = ["#00e5a0", "#ff4444", "#4488ff", "#ffd700"]


def _gen_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=6))


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


# ─── Health ──────────────────────────────────────────────────────────────────
@router.get("/health")
async def health():
    return {"status": "ok", "storage": "redis"}


# ─── Auth ────────────────────────────────────────────────────────────────────
@router.post("/register", status_code=201)
async def register(body: RegisterBody, pool=Depends(get_pool)):
    if not (3 <= len(body.username) <= 30):
        raise HTTPException(400, "Username debe tener entre 3 y 30 caracteres")
    if len(body.password) < 6:
        raise HTTPException(400, "Contrasena minimo 6 caracteres")
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
        raise HTTPException(401, "Usuario o contrasena incorrectos")
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


# ─── Game rooms (Redis-backed) ──────────────────────────────────────────────
@router.post("/games")
async def create_game_endpoint(body: CreateGameBody, pool=Depends(get_pool)):
    code = _gen_code()
    while await room_exists(code):
        code = _gen_code()
    await create_room(code, rules=body.rules, max_players=body.max_players)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO poleana_games (code, rules, max_players) VALUES ($1, $2, $3)",
            code, body.rules, body.max_players,
        )
    return {"code": code, "rules": body.rules, "max_players": body.max_players}


@router.get("/games/{code}")
async def get_game(code: str):
    room = await get_room(code.upper())
    if not room:
        raise HTTPException(404, "Sala no encontrada o expirada")
    players = room.get("players", [])
    return {
        "code": code.upper(),
        "rules": room.get("rules", "T"),
        "max_players": int(room.get("max_players", 4)),
        "players": [{"username": p["username"], "color": p["color"]} for p in players],
        "started": is_started(room),
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────
@router.websocket("/ws/{code}")
async def ws_game(websocket: WebSocket, code: str, token: str = ""):
    code = code.upper()
    room = await get_room(code)
    if not room:
        await websocket.close(code=4004, reason="Sala no encontrada")
        return

    # Decode token -> username (stored in "email" field by auth_service)
    username = None
    if token:
        try:
            payload = decode_token(token)
            username = payload.get("email")
        except Exception:
            pass
    if not username:
        await websocket.close(code=4001, reason="Token invalido")
        return

    players = room.get("players", [])
    started = is_started(room)
    player_exists = any(p["username"] == username for p in players)

    if started and not player_exists:
        await websocket.close(code=4003, reason="Partida ya iniciada")
        return

    max_p = int(room.get("max_players", 4))
    if len(players) >= max_p and not player_exists:
        await websocket.close(code=4002, reason="Sala llena")
        return

    await websocket.accept()

    # --- Register WebSocket in-memory ---
    if code not in _ws_connections:
        _ws_connections[code] = {}
    _ws_connections[code][username] = websocket

    # --- Rejoin or new join in Redis ---
    if player_exists:
        color_idx = next(p["color"] for p in players if p["username"] == username)
    else:
        color_idx = len(players)
        await add_player(code, username, color_idx)

    # Re-read room after potential add
    room = await get_room(code)
    players = room.get("players", [])

    # Send current state to (re)joining player
    state_raw = room.get("state")
    state = None
    if isinstance(state_raw, str):
        try:
            state = json.loads(state_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(state_raw, dict):
        state = state_raw

    if state:
        await websocket.send_text(json.dumps({
            "type": "STATE", "state": state, "actor": None,
        }))

    await _broadcast(code, {
        "type": "JOINED",
        "username": username,
        "color": COLORS[color_idx] if color_idx < len(COLORS) else "#cccccc",
        "color_idx": color_idx,
        "count": len(players),
        "max": max_p,
        "players": [{"username": p["username"], "color": p["color"]} for p in players],
    })

    # --- Heartbeat task ---
    hb_task = asyncio.create_task(_heartbeat(websocket))

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "pong":
                # Respuesta al heartbeat -- no hacer nada
                continue

            # Re-read room from Redis for each action (authoritative state)
            room = await get_room(code)
            if not room:
                await websocket.send_text(json.dumps({
                    "type": "ERROR", "msg": "Sala expirada",
                }))
                break

            if mtype == "START" and not is_started(room):
                current_players = room.get("players", [])
                if len(current_players) < 2:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR", "msg": "Minimo 2 jugadores",
                    }))
                    continue
                await set_started(code, True)
                await _broadcast(code, {
                    "type": "GAME_START",
                    "rules": room.get("rules", "T"),
                    "players": [
                        {"username": p["username"], "color": p["color"]}
                        for p in current_players
                    ],
                })

            elif mtype == "ROLL":
                # Server-authoritative: dados generados en servidor
                is_valid, error_msg = validate_move(room, username, {})
                if not is_valid:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR", "msg": error_msg,
                    }))
                    continue
                d1 = random.randint(1, 6)
                d2 = random.randint(1, 6)
                # Guardar resultado de dados en state para validacion posterior
                state_raw = room.get("state")
                current_state = None
                if isinstance(state_raw, str):
                    try:
                        current_state = json.loads(state_raw)
                    except (json.JSONDecodeError, TypeError):
                        current_state = {}
                elif isinstance(state_raw, dict):
                    current_state = state_raw
                if current_state is None:
                    current_state = {}
                current_state["dice_result"] = [d1, d2]
                await set_game_state(code, current_state)
                await _broadcast(code, {"type": "DICE", "d1": d1, "d2": d2})

            elif mtype == "STATE":
                # Cliente envia nuevo estado despues de mover
                # Validar que es el turno del jugador
                is_valid, error_msg = validate_move(room, username, msg)
                if not is_valid:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR", "msg": error_msg,
                    }))
                    continue
                new_state = msg.get("state", {})
                await set_game_state(code, new_state)
                await _broadcast_except(code, username, {
                    "type": "STATE",
                    "state": new_state,
                    "actor": username,
                })

            elif mtype == "CHAT":
                text = str(msg.get("text", ""))[:200]
                await _broadcast(code, {
                    "type": "CHAT", "username": username, "text": text,
                })

            elif mtype == "GAME_OVER":
                winner = msg.get("winner", "")
                await set_started(code, False)
                await set_game_state(code, None)
                await _broadcast(code, {
                    "type": "GAME_OVER", "winner": winner,
                })

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Error en WebSocket Poleana room=%s user=%s: %s",
                         code, username, exc)
    finally:
        hb_task.cancel()
        # Limpiar WebSocket in-memory
        if code in _ws_connections:
            _ws_connections[code].pop(username, None)
            active = {u: ws for u, ws in _ws_connections[code].items() if ws is not None}
            if not active:
                _ws_connections.pop(code, None)
                await delete_room(code)
            else:
                await _broadcast(code, {
                    "type": "LEFT", "username": username, "count": len(active),
                })


# ─── Heartbeat ───────────────────────────────────────────────────────────────
async def _heartbeat(websocket: WebSocket):
    """Ping cada 30s para detectar conexiones caidas."""
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except Exception:
        pass  # WebSocket cerrado -- el finally del handler limpia


# ─── Broadcast helpers ───────────────────────────────────────────────────────
async def _broadcast(room_code: str, msg: dict):
    """Envia mensaje a todos los WebSockets conectados en la sala."""
    payload = json.dumps(msg)
    conns = _ws_connections.get(room_code, {})
    dead = []
    for uname, ws in conns.items():
        if ws:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(uname)
    for uname in dead:
        conns[uname] = None


async def _broadcast_except(room_code: str, exclude_username: str, msg: dict):
    """Envia mensaje a todos excepto al usuario especificado."""
    payload = json.dumps(msg)
    conns = _ws_connections.get(room_code, {})
    dead = []
    for uname, ws in conns.items():
        if ws and uname != exclude_username:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(uname)
    for uname in dead:
        conns[uname] = None
