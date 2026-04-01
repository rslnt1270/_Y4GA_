---
name: poleana
description: "Motor de juego Poleana v7.0: parser alfanumérico, grafo, reglas, bugs conocidos, y arquitectura online."
---

# Poleana Engine v7.0 — Referencia

## Archivos
```
Poleana_Project/
├── web/
│   ├── poleana_engine.js     # Motor completo (~930 líneas)
│   ├── poleana_game.html     # UI (HTML/CSS)
│   └── boards/
│       ├── TABLERO1.txt      # J1 (abajo) — alfanumérico
│       ├── TABLERO2.txt      # J2 (derecha)
│       ├── TABLERO3.txt      # J3 (arriba)
│       └── TABLERO4.txt      # J4 (izquierda)
├── server/                   # Backend Python (WebSocket relay)
├── engine/                   # Motor Python (migración pendiente)
└── docs/                     # Reglas, arquitectura
```

## Identificadores alfanuméricos
| Token | Significado | Ejemplo |
|-------|-------------|---------|
| `15` | Camino estándar | Casilla 15, seguro |
| `3a` | Zona oponente A | Casa del primer rival |
| `5b` | Zona oponente B | Casa del segundo rival |
| `1c` | Zona oponente C | Casa del tercer rival |
| `4d` | Rampa de meta | Solo el dueño entra, 100% segura |
| `##` | Muro | No transitable |
| `.` | Centro vacío | No transitable |

## Grafo — cómo se construye
1. Parsear grid 16×16 → cells Map
2. Cardinal adjacency: `num+1, same zone` → NEXT_CELL
3. Diagonal fallback: esquinas donde cardinal no llega (6a→7a, 56→57)
4. Zone connections: `standard N → 1a/1b/1c` (entry), `7a/7b/7c → standard` (exit)
5. Branch detection: celda estándar con next→zona = bifurcación risk/safe

## Branch points (TABLERO1)
| Celda | Risk (zona) | Safe (estándar) | Merge |
|-------|-------------|-----------------|-------|
| 14 | → 1a...7a | → 15...28 | 18 |
| 28 | → 1b...7b | → 29...42 | 32 |
| 42 | → 1c...7c | → 43...51 | 46 |

## Reglas — resumen ejecutivo
- **Spawn**: par 6→2, par 3→1, 6+3→casilla 3, suma 6→1
- **Jerarquía**: captura obligatoria > spawn > libre
- **Espejo**: ficha en zona a/b/c con num = dado → cárcel (oponente pierde move)
- **Chismoso**: 3 pares → ficha más avanzada a cárcel
- **Premio**: captura +10, corona +10 (encadenable)
- **Torres**: 2 propias = bloqueo
- **Rebote**: pasos sobrantes retroceden desde el final
- **Conteo**: solo decrementa cuando cambia el número lógico

## Bugs conocidos / pendientes
- [ ] TABLERO2-4 necesitan conversión al formato alfanumérico
- [ ] Online multiplayer es client-authoritative (manipulable)
- [ ] Token de auth en localStorage (riesgo XSS)
- [ ] WebSocket relay sin validación de estado server-side
- [ ] Zona d (rampa de meta) no implementada en motor (retorna null)

## Testing en consola
```javascript
debugPath(1)           // "0 → 1 → ... → 14 → 1a → ... → 7a → 18 → ..."
debugMove(1, 0, 8)     // {risk: "2a", safe: "16"}
G.players[0].pieces[0].cellKey = getCellKeyFromNum(1, 8);
computeMoves(G.players[0], 6, 2).map(m => m.label);
```
