# © YAGA Project — Todos los derechos reservados
"""
Poleana Engine Adapter — Server-authoritative state machine.

Este módulo encapsula la lógica del juego Poleana en el servidor para
cerrar la vulnerabilidad 6.5 (client-authoritative). El cliente solo
envía intenciones (ROLL, MOVE); el servidor calcula, valida y persiste.

DISEÑO
------
El motor original (`Poleana_Project/engine/engine.py`) requiere cargar
archivos de tablero (TABLERO*.txt) y opera sobre coordenadas (x, y) del
laberinto. Estos archivos NO están disponibles en el container de
producción (`yaga_api`), por lo que este adaptador implementa una
versión simplificada que:

  1. Mantiene la misma jerarquía de reglas (captura > spawn > mover)
     delegando en `PoleanaRuleSet.check_spawn` del motor real.
  2. Reemplaza la navegación por tablero con tracking puro de `valor`
     (posición numérica 0..VALOR_META) aplicando la regla del rebote.
  3. Detecta capturas cuando dos fichas de jugadores distintos caen en
     el mismo `valor` fuera de zonas seguras.
  4. Declara ganador cuando las 4 fichas de un jugador llegan a META.

Mantiene interoperabilidad futura: si los tableros se bakean en el
container, se puede sustituir este adaptador por uno basado en
`PoleanaEngine` sin cambiar el contrato público.
"""
from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Importa las reglas del motor real (no requiere archivos de tablero).
_ENGINE_DIR = Path(__file__).resolve().parents[2] / "Poleana_Project" / "engine"
if _ENGINE_DIR.exists() and str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

try:
    from rules import PoleanaRuleSet, TOURNAMENT_RULES, STREET_RULES  # type: ignore
    from constants import VALOR_META, BRIDGE_MIN, ZONAS_SEGURAS        # type: ignore
except Exception:
    # Fallback: constantes y reglas mínimas embebidas si el paquete no
    # está disponible en el PYTHONPATH del container.
    VALOR_META = 56
    BRIDGE_MIN = 50
    ZONAS_SEGURAS = {0, 3}

    @dataclass
    class PoleanaRuleSet:  # type: ignore[no-redef]
        allow_towers: bool = True
        capture_reward: int = 10
        goal_reward: int = 10
        strict_hierarchy: bool = True
        failed_dice_chance: float = 0.0

        def check_spawn(self, d1: int, d2: int):
            if d1 == 6 and d2 == 6:
                return True, "par_6", 0
            if d1 == 3 and d2 == 3:
                return True, "par_3", 0
            if {d1, d2} == {6, 3}:
                return True, "especial", 3
            if (d1 + d2) == 6 and d1 != d2:
                return True, "normal", 0
            return False, "", 0

    TOURNAMENT_RULES = PoleanaRuleSet()
    STREET_RULES = PoleanaRuleSet(
        capture_reward=20, strict_hierarchy=False, failed_dice_chance=0.05
    )


# ---------------------------------------------------------------------------
# Estado serializable
# ---------------------------------------------------------------------------

@dataclass
class FichaState:
    idx: int
    valor: int = -1          # -1 = en base
    x: Optional[int] = None  # reservado para migración futura
    y: Optional[int] = None
    en_base: bool = True
    llego: bool = False
    zona_segura: bool = False


@dataclass
class JugadorState:
    id: int
    fichas: list = field(default_factory=list)  # list[FichaState]


@dataclass
class PoleanaGameState:
    jugadores: list                     # list[JugadorState]
    turno_actual: int = 0
    fase: str = "ESPERANDO_TIRO"        # ESPERANDO_TIRO | ESPERANDO_MOVIMIENTO
    ultimo_dado: Optional[dict] = None  # {d1, d2, suma, es_par}
    ganador: Optional[str] = None
    reglas: str = "T"                   # "T" | "S"
    pares_consec: list = field(default_factory=list)  # por jugador
    opciones: list = field(default_factory=list)      # opciones del turno actual


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _get_rules(flag: str) -> PoleanaRuleSet:
    return STREET_RULES if flag == "S" else TOURNAMENT_RULES


def _rebote(valor: int) -> int:
    """Aplica la regla del rebote si sobrepasa META."""
    if valor > VALOR_META:
        return VALOR_META - (valor - VALOR_META)
    return valor


def _es_zona_segura(valor: int) -> bool:
    return valor in ZONAS_SEGURAS or valor >= BRIDGE_MIN


def _ficha_dict(f: FichaState) -> dict:
    return {
        "idx": f.idx,
        "valor": f.valor,
        "x": f.x,
        "y": f.y,
        "en_base": f.en_base,
        "llego": f.llego,
        "zona_segura": f.zona_segura,
    }


def _jugador_dict(j: JugadorState) -> dict:
    return {"id": j.id, "fichas": [_ficha_dict(f) for f in j.fichas]}


def _state_to_dict(state: PoleanaGameState) -> dict:
    return {
        "jugadores": [_jugador_dict(j) for j in state.jugadores],
        "turno_actual": state.turno_actual,
        "fase": state.fase,
        "ultimo_dado": state.ultimo_dado,
        "ganador": state.ganador,
        "reglas": state.reglas,
        "pares_consec": state.pares_consec,
        "opciones": state.opciones,
    }


def _state_from_dict(data: dict) -> PoleanaGameState:
    jugadores = []
    for jd in data.get("jugadores", []):
        fichas = [FichaState(**fd) for fd in jd.get("fichas", [])]
        jugadores.append(JugadorState(id=jd["id"], fichas=fichas))
    return PoleanaGameState(
        jugadores=jugadores,
        turno_actual=data.get("turno_actual", 0),
        fase=data.get("fase", "ESPERANDO_TIRO"),
        ultimo_dado=data.get("ultimo_dado"),
        ganador=data.get("ganador"),
        reglas=data.get("reglas", "T"),
        pares_consec=data.get("pares_consec", []),
        opciones=data.get("opciones", []),
    )


def state_to_redis(state: PoleanaGameState) -> str:
    """Serializa el estado a JSON para persistir en Redis."""
    return json.dumps(_state_to_dict(state))


def state_from_redis(data: str) -> PoleanaGameState:
    """Deserializa un estado desde JSON almacenado en Redis."""
    return _state_from_dict(json.loads(data))


def state_to_public_dict(state: PoleanaGameState) -> dict:
    """Devuelve el dict serializable (para broadcast a clientes)."""
    return _state_to_dict(state)


# ---------------------------------------------------------------------------
# Inicialización
# ---------------------------------------------------------------------------

def init_game_state(num_jugadores: int, reglas: str = "T") -> PoleanaGameState:
    """Crea el estado inicial con todas las fichas en base."""
    if num_jugadores < 2 or num_jugadores > 4:
        raise ValueError("num_jugadores debe estar entre 2 y 4")
    jugadores = [
        JugadorState(id=i, fichas=[FichaState(idx=k) for k in range(4)])
        for i in range(num_jugadores)
    ]
    return PoleanaGameState(
        jugadores=jugadores,
        turno_actual=0,
        fase="ESPERANDO_TIRO",
        ultimo_dado=None,
        ganador=None,
        reglas=reglas,
        pares_consec=[0] * num_jugadores,
        opciones=[],
    )


# ---------------------------------------------------------------------------
# Cálculo de opciones y movimiento (versión simplificada basada en valor)
# ---------------------------------------------------------------------------

def _fichas_activas(jug: JugadorState) -> list:
    return [f for f in jug.fichas if not f.en_base and not f.llego]


def _fichas_en_base(jug: JugadorState) -> list:
    return [f for f in jug.fichas if f.en_base]


def _alcanza(f: FichaState, pasos: int) -> bool:
    """¿La ficha puede avanzar `pasos` aplicando rebote?"""
    if f.en_base or f.llego:
        return False
    destino = _rebote(f.valor + pasos)
    return 0 <= destino <= VALOR_META


def _destino(f: FichaState, pasos: int) -> int:
    return _rebote(f.valor + pasos)


def _enemigo_capturable(
    state: PoleanaGameState, jug_id: int, valor: int
) -> Optional[tuple]:
    """Retorna (jug_id_enemigo, ficha_idx) si hay ficha capturable en `valor`."""
    if _es_zona_segura(valor):
        return None
    for j in state.jugadores:
        if j.id == jug_id:
            continue
        for f in j.fichas:
            if not f.en_base and not f.llego and f.valor == valor:
                return (j.id, f.idx)
    return None


def _buscar_opciones(
    state: PoleanaGameState, jug_id: int, d1: int, d2: int, rules: PoleanaRuleSet
) -> tuple:
    """
    Computa opciones para el turno.

    Retorna: (tipo, opciones, spawn_info)
      tipo       : 'CAPTURA' | 'SPAWN' | 'MOVER' | 'SIN_MOVIMIENTO'
      opciones   : list[dict] con {ficha_idx, pasos, dado_usado, dest, es_captura}
      spawn_info : dict | None con {tipo, pos, num} si tipo == 'SPAWN'
    """
    jug = state.jugadores[jug_id]
    suma = d1 + d2
    activas = _fichas_activas(jug)

    # --- PRIORIDAD 1: CAPTURA obligatoria (jerarquía estricta) ---
    if rules.strict_hierarchy and activas:
        capturas = []
        for f in activas:
            for pasos, dado in _pasos_disponibles(d1, d2, len(activas)):
                if not _alcanza(f, pasos):
                    continue
                dest = _destino(f, pasos)
                if _enemigo_capturable(state, jug_id, dest):
                    capturas.append({
                        "ficha_idx": f.idx,
                        "pasos": pasos,
                        "dado_usado": dado,
                        "dest": dest,
                        "es_captura": True,
                    })
        if capturas:
            return ("CAPTURA", capturas, None)

    # --- PRIORIDAD 2: SPAWN ---
    puede, tipo_s, pos_s = rules.check_spawn(d1, d2)
    en_base = _fichas_en_base(jug)
    if puede and en_base:
        num = 2 if tipo_s == "par_6" and len(en_base) >= 2 else 1
        opciones = [
            {
                "ficha_idx": en_base[i].idx,
                "pasos": 0,
                "dado_usado": 0,
                "dest": pos_s,
                "es_captura": False,
                "es_spawn": True,
            }
            for i in range(num)
        ]
        return ("SPAWN", opciones, {"tipo": tipo_s, "pos": pos_s, "num": num})

    # --- PRIORIDAD 3: MOVER ---
    if not activas:
        return ("SIN_MOVIMIENTO", [], None)

    ops = []
    for f in activas:
        for pasos, dado in _pasos_disponibles(d1, d2, len(activas)):
            if _alcanza(f, pasos):
                ops.append({
                    "ficha_idx": f.idx,
                    "pasos": pasos,
                    "dado_usado": dado,
                    "dest": _destino(f, pasos),
                    "es_captura": False,
                })
    if not ops:
        return ("SIN_MOVIMIENTO", [], None)
    return ("MOVER", ops, None)


def _pasos_disponibles(d1: int, d2: int, num_activas: int) -> list:
    """Retorna [(pasos, dado_usado), ...] incluyendo split si aplica."""
    out = [(d1 + d2, 0)]
    if d1 != d2 and num_activas >= 2:
        out.append((d1, d1))
        out.append((d2, d2))
    return out


def _avanzar_turno(state: PoleanaGameState) -> None:
    """Pasa al siguiente jugador. No avanza si hay extra turn."""
    n = len(state.jugadores)
    state.turno_actual = (state.turno_actual + 1) % n
    state.fase = "ESPERANDO_TIRO"
    state.ultimo_dado = None
    state.opciones = []


# ---------------------------------------------------------------------------
# Acciones públicas
# ---------------------------------------------------------------------------

def apply_roll(state: PoleanaGameState, jug_id: int) -> tuple:
    """
    El jugador en turno lanza los dados.

    Validaciones:
      - jug_id debe coincidir con turno_actual
      - fase debe ser ESPERANDO_TIRO
      - no debe haber ganador

    Si no hay movimiento posible → avanza turno automáticamente.
    """
    if state.ganador is not None:
        return state, {"ok": False, "error": "La partida ya terminó"}
    if jug_id != state.turno_actual:
        return state, {"ok": False, "error": "No es tu turno"}
    if state.fase != "ESPERANDO_TIRO":
        return state, {"ok": False, "error": f"Fase incorrecta: {state.fase}"}

    rules = _get_rules(state.reglas)
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    suma = d1 + d2
    es_par = (d1 == d2)

    tipo, opciones, spawn_info = _buscar_opciones(state, jug_id, d1, d2, rules)

    state.ultimo_dado = {"d1": d1, "d2": d2, "suma": suma, "es_par": es_par}
    state.opciones = opciones

    # Regla Chismoso: 3 pares consecutivos → ficha más avanzada a base.
    chismoso_aplicado = False
    if es_par and rules.strict_hierarchy:
        state.pares_consec[jug_id] += 1
        if state.pares_consec[jug_id] >= 3:
            jug = state.jugadores[jug_id]
            activas = _fichas_activas(jug)
            if activas:
                mas_avanzada = max(activas, key=lambda f: f.valor)
                mas_avanzada.valor = -1
                mas_avanzada.en_base = True
                mas_avanzada.x = None
                mas_avanzada.y = None
                mas_avanzada.zona_segura = False
                chismoso_aplicado = True
            state.pares_consec[jug_id] = 0
            tipo = "SIN_MOVIMIENTO"
            opciones = []
            state.opciones = []
    elif not es_par:
        state.pares_consec[jug_id] = 0

    result = {
        "ok": True,
        "d1": d1,
        "d2": d2,
        "suma": suma,
        "es_par": es_par,
        "tipo": tipo,
        "opciones": opciones,
        "spawn_info": spawn_info,
        "chismoso": chismoso_aplicado,
    }

    if tipo == "SIN_MOVIMIENTO":
        _avanzar_turno(state)
        result["turno_siguiente"] = state.turno_actual
    else:
        state.fase = "ESPERANDO_MOVIMIENTO"

    return state, result


def apply_move(
    state: PoleanaGameState,
    jug_id: int,
    ficha_idx: int,
    pasos: int,
) -> tuple:
    """
    Aplica un movimiento validado contra las opciones calculadas en apply_roll.

    El cliente solo envía (ficha_idx, pasos); el servidor verifica que la
    combinación esté en state.opciones.
    """
    if state.ganador is not None:
        return state, {"ok": False, "error": "La partida ya terminó"}
    if jug_id != state.turno_actual:
        return state, {"ok": False, "error": "No es tu turno"}
    if state.fase != "ESPERANDO_MOVIMIENTO":
        return state, {"ok": False, "error": f"Fase incorrecta: {state.fase}"}

    # Buscar la opción exacta en las precalculadas.
    opcion = next(
        (o for o in state.opciones
         if o["ficha_idx"] == ficha_idx and o["pasos"] == pasos),
        None,
    )
    if not opcion:
        return state, {"ok": False, "error": "Movimiento no permitido"}

    rules = _get_rules(state.reglas)
    jug = state.jugadores[jug_id]
    ficha = jug.fichas[ficha_idx]

    resultado = {
        "ok": True,
        "ficha_idx": ficha_idx,
        "pasos": pasos,
        "captura": None,
        "llego": False,
        "premio": 0,
        "es_spawn": opcion.get("es_spawn", False),
    }

    # --- SPAWN ---
    if opcion.get("es_spawn"):
        ficha.en_base = False
        ficha.valor = opcion["dest"]
        ficha.zona_segura = _es_zona_segura(ficha.valor)
        # Captura al salir (spawn en casilla 3 si hay enemigo)
        enemigo = _enemigo_capturable(state, jug_id, ficha.valor)
        if enemigo:
            ej, ei = enemigo
            en_f = state.jugadores[ej].fichas[ei]
            en_f.valor = -1
            en_f.en_base = True
            en_f.x = None
            en_f.y = None
            en_f.zona_segura = False
            resultado["captura"] = {"jug_id": ej, "ficha_idx": ei}
            resultado["premio"] = rules.capture_reward
    else:
        # --- MOVIMIENTO ---
        destino = _destino(ficha, pasos)
        ficha.valor = destino
        ficha.zona_segura = _es_zona_segura(destino)

        if destino == VALOR_META:
            ficha.llego = True
            resultado["llego"] = True
            resultado["premio"] = rules.goal_reward
        else:
            enemigo = _enemigo_capturable(state, jug_id, destino)
            if enemigo:
                ej, ei = enemigo
                en_f = state.jugadores[ej].fichas[ei]
                en_f.valor = -1
                en_f.en_base = True
                en_f.x = None
                en_f.y = None
                en_f.zona_segura = False
                resultado["captura"] = {"jug_id": ej, "ficha_idx": ei}
                resultado["premio"] = rules.capture_reward

    # --- Chequear ganador ---
    if all(f.llego for f in jug.fichas):
        state.ganador = f"J{jug_id + 1}"
        resultado["ganador"] = state.ganador
        state.fase = "TERMINADO"
        state.opciones = []
        return state, resultado

    # --- Avanzar turno ---
    # Regla: par concede turno extra; spawn múltiple consume una ficha a la vez
    # (simplificación: cada MOVE avanza turno salvo par).
    es_par = state.ultimo_dado and state.ultimo_dado.get("es_par", False)
    if es_par:
        state.fase = "ESPERANDO_TIRO"
        state.opciones = []
        state.ultimo_dado = None
        resultado["turno_extra"] = True
    else:
        _avanzar_turno(state)

    resultado["turno_siguiente"] = state.turno_actual
    return state, resultado
