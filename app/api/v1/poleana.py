"""
POLEANA — Router REST + WebSocket para partidas en línea
"""
import json
import random
import string
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from services.database import get_pool
from services.auth_service import hash_password, verify_password, create_token, decode_token

router = APIRouter(prefix="/api/v1/poleana", tags=["Poleana"])

# ─── In-memory room registry ─────────────────────────────────────────────────
# { code: { players:[{username,color,ws}], state, max, rules, started } }
_rooms: dict = {}

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
    while code in _rooms:
        code = _gen_code()
    _rooms[code] = {
        "players": [],
        "state": None,
        "max": body.max_players,
        "rules": body.rules,
        "started": False,
    }
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO poleana_games (code, rules, max_players) VALUES ($1, $2, $3)",
            code, body.rules, body.max_players,
        )
    return {"code": code, "rules": body.rules, "max_players": body.max_players}


@router.get("/games/{code}")
async def get_game(code: str):
    room = _rooms.get(code.upper())
    if not room:
        raise HTTPException(404, "Sala no encontrada o expirada")
    return {
        "code": code.upper(),
        "rules": room["rules"],
        "max_players": room["max"],
        "players": [{"username": p["username"], "color": p["color"]} for p in room["players"]],
        "started": room["started"],
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────
@router.websocket("/ws/{code}")
async def ws_game(websocket: WebSocket, code: str, token: str = ""):
    code = code.upper()
    room = _rooms.get(code)
    if not room:
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

    if room["started"] and not any(p["username"] == username for p in room["players"]):
        await websocket.close(code=4003, reason="Partida ya iniciada")
        return

    if len(room["players"]) >= room["max"] and not any(p["username"] == username for p in room["players"]):
        await websocket.close(code=4002, reason="Sala llena")
        return

    await websocket.accept()

    # Rejoin or new join
    existing = next((p for p in room["players"] if p["username"] == username), None)
    if existing:
        existing["ws"] = websocket
        color_idx = existing["color"]
    else:
        color_idx = len(room["players"])
        room["players"].append({"username": username, "color": color_idx, "ws": websocket})

    # Send current state to (re)joining player
    if room["state"]:
        await websocket.send_text(json.dumps({"type": "STATE", "state": room["state"], "actor": None}))

    await _broadcast(room, {
        "type": "JOINED",
        "username": username,
        "color": COLORS[color_idx],
        "color_idx": color_idx,
        "count": len(room["players"]),
        "max": room["max"],
        "players": [{"username": p["username"], "color": p["color"]} for p in room["players"]],
    })

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "START" and not room["started"]:
                if len(room["players"]) < 2:
                    await websocket.send_text(json.dumps({"type": "ERROR", "msg": "Mínimo 2 jugadores"}))
                    continue
                room["started"] = True
                await _broadcast(room, {
                    "type": "GAME_START",
                    "rules": room["rules"],
                    "players": [{"username": p["username"], "color": p["color"]} for p in room["players"]],
                })

            elif mtype == "STATE":
                state = msg.get("state", {})
                turn = state.get("turn", 0)
                if turn < len(room["players"]) and room["players"][turn]["username"] != username:
                    await websocket.send_text(json.dumps({"type": "ERROR", "msg": "No es tu turno"}))
                    continue
                room["state"] = state
                await _broadcast_except(room, websocket, {
                    "type": "STATE",
                    "state": state,
                    "actor": username,
                })

            elif mtype == "CHAT":
                text = str(msg.get("text", ""))[:200]
                await _broadcast(room, {"type": "CHAT", "username": username, "text": text})

            elif mtype == "GAME_OVER":
                winner = msg.get("winner", "")
                room["started"] = False
                room["state"] = None
                await _broadcast(room, {"type": "GAME_OVER", "winner": winner})

    except WebSocketDisconnect:
        pass
    finally:
        # Keep slot but mark ws as None (allow rejoin)
        for p in room["players"]:
            if p["ws"] is websocket:
                p["ws"] = None
        active = [p for p in room["players"] if p["ws"] is not None]
        if not active:
            _rooms.pop(code, None)
        else:
            await _broadcast(room, {"type": "LEFT", "username": username, "count": len(active)})


async def _broadcast(room: dict, msg: dict):
    payload = json.dumps(msg)
    for p in room["players"]:
        if p["ws"]:
            try:
                await p["ws"].send_text(payload)
            except Exception:
                p["ws"] = None


async def _broadcast_except(room: dict, exclude: WebSocket, msg: dict):
    payload = json.dumps(msg)
    for p in room["players"]:
        if p["ws"] and p["ws"] is not exclude:
            try:
                await p["ws"].send_text(payload)
            except Exception:
                p["ws"] = None
