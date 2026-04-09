# © YAGA Project — Todos los derechos reservados

# Deuda Tecnica: Poleana Server-Authoritative (Vulnerabilidad 6.5)

**Estado:** Diferido a Sprint 6
**Severidad:** Alta
**Fecha de registro:** 2026-04-09

---

## Problema actual

El WebSocket handler de Poleana (`app/api/v1/poleana.py`) acepta mensajes de tipo `STATE` donde el cliente envia el estado completo del juego:

```python
elif mtype == "STATE":
    state = msg.get("state", {})
    # ...
    meta["state"] = state
    await _set_room_meta(code, meta)
    await _broadcast_except(conns, websocket, {
        "type": "STATE",
        "state": state,
        "actor": username,
    })
```

El servidor solo valida que sea el turno correcto del jugador (comparando `state.turn` contra `players_meta`), pero no valida la legalidad del movimiento ni la integridad del estado. El cliente es la fuente de verdad: construye el estado localmente y lo envia completo al servidor, que lo persiste en Redis y lo retransmite a los demas jugadores.

El mismo patron se repite con `GAME_OVER`: el cliente decide quien gano y el servidor lo acepta sin verificacion.

## Riesgos de seguridad

1. **Cheating por manipulacion de estado:** Un jugador puede enviar un estado arbitrario donde sus fichas estan en posiciones ventajosas, dados falsos, o fichas del oponente eliminadas.

2. **Victoria forzada:** Un cliente malicioso puede enviar `{"type": "GAME_OVER", "winner": "su_username"}` en cualquier momento para ganar la partida sin jugarla.

3. **Corrupcion de estado:** Un cliente puede enviar estado malformado o inconsistente que corrompe la partida para todos los jugadores conectados.

4. **Escalacion:** Si se implementan apuestas o ranking competitivo en el futuro, esta vulnerabilidad permite fraude directo.

## Diseno propuesto para Sprint 6

### Arquitectura objetivo

El servidor se convierte en la unica fuente de verdad. El cliente solo envia **intenciones** (acciones), nunca estado.

### Mensajes del cliente (entrada)

Solo se aceptan dos tipos de mensaje del cliente durante la partida:

```json
{"type": "ROLL"}
```
- El servidor genera el resultado del dado usando `random.randint(1, 6)`.
- Solo se acepta si es el turno del jugador que lo envia.

```json
{"type": "MOVE", "to": "C3"}
```
- El servidor valida que el movimiento es legal usando `PoleanaRuleSet`.
- Si es valido, aplica el movimiento al estado interno.
- Si es invalido, responde con `{"type": "ERROR", "msg": "Movimiento no permitido"}`.

### Mensajes del servidor (salida)

```json
{"type": "ROLL_RESULT", "player": "username", "value": 4}
{"type": "STATE", "state": {...}, "actor": "username"}
{"type": "GAME_OVER", "winner": "username"}
{"type": "ERROR", "msg": "..."}
```

El servidor calcula el nuevo estado completo despues de cada accion valida y lo envia a todos los jugadores via broadcast.

### Flujo de un turno

1. Cliente A envia `{"type": "ROLL"}`.
2. Servidor verifica que es el turno de A. Genera dado = 4.
3. Servidor hace broadcast de `ROLL_RESULT` a todos.
4. Cliente A envia `{"type": "MOVE", "to": "C3"}`.
5. Servidor valida con `PoleanaRuleSet.is_valid_move(state, player_idx, "C3", dice=4)`.
6. Si es valido: aplica movimiento, actualiza estado en Redis, hace broadcast del nuevo `STATE`.
7. Si el movimiento resulta en victoria, el servidor envia `GAME_OVER`.

### Archivos a modificar

| Archivo | Cambio |
|---|---|
| `app/api/v1/poleana.py` | Reemplazar handler de `STATE` por handlers de `ROLL` y `MOVE`. Eliminar aceptacion de `GAME_OVER` del cliente. Instanciar `PoleanaRuleSet` al iniciar partida. Mantener estado del juego en el servidor (Redis). |
| `Poleana_Project/poleana_engine.py` (o equivalente) | Exponer metodos `is_valid_move(state, player, target, dice)`, `apply_move(state, player, target, dice)`, `check_winner(state)` como API del motor. Asegurar que el motor sea determinista y no dependa de I/O. |
| `Poleana_Project/` (frontend JS) | Eliminar logica de construccion de estado. El cliente solo envia intenciones (`ROLL`, `MOVE`). Renderizar el estado que recibe del servidor. |

### Estado del juego en el servidor

```python
# Estructura del estado gestionado por el servidor
game_state = {
    "board": {...},         # Posiciones de todas las fichas
    "turn": 0,              # Indice del jugador actual
    "dice": None,           # Ultimo resultado del dado (o None si no ha tirado)
    "players": [...],       # Lista de jugadores con sus fichas
    "phase": "ROLL",        # "ROLL" | "MOVE" | "FINISHED"
    "winner": None,         # Username del ganador o None
}
```

## Criterios de aceptacion

### Pruebas funcionales

- [ ] Un cliente que envia `{"type": "STATE", "state": {...}}` recibe `{"type": "ERROR", "msg": "Tipo de mensaje no permitido"}`.
- [ ] Un cliente que envia `{"type": "GAME_OVER", "winner": "..."}` recibe un error (solo el servidor puede declarar victoria).
- [ ] `ROLL` solo funciona cuando es el turno del jugador y la fase es `ROLL`.
- [ ] `MOVE` solo funciona cuando es el turno del jugador, la fase es `MOVE`, y el movimiento es legal segun `PoleanaRuleSet`.
- [ ] Todos los jugadores reciben el mismo estado despues de cada accion.
- [ ] Reconexion: un jugador que se desconecta y reconecta recibe el estado actual correcto desde Redis.

### Pruebas de seguridad

- [ ] Enviar estado manipulado no altera el juego.
- [ ] Enviar un movimiento fuera de turno es rechazado.
- [ ] Enviar un movimiento ilegal (segun las reglas) es rechazado.
- [ ] No es posible forzar una victoria desde el cliente.

### Pruebas de regresion

- [ ] Partidas de 2, 3 y 4 jugadores funcionan correctamente.
- [ ] El chat (`CHAT`) sigue funcionando sin cambios.
- [ ] La funcionalidad de rejoin sigue operativa.
- [ ] Las reglas `TOURNAMENT_RULES` y `STREET_RULES` producen comportamiento correcto.

## Razon del diferimiento

La migracion a server-authoritative requiere:

1. Refactorizar el motor de juego (`PoleanaRuleSet`) para exponer una API de validacion y aplicacion de movimientos.
2. Reescribir el handler WebSocket completo.
3. Reescribir la logica del frontend para que solo envie intenciones.
4. Pruebas end-to-end con multiples jugadores simultaneos.

Esta complejidad excede el alcance del Sprint 5, donde la prioridad fue migrar las rooms de memoria a Redis (vulnerabilidad 6.6, completada). La vulnerabilidad 6.5 se abordara como objetivo principal del Sprint 6.
