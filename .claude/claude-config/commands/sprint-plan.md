---
description: "Planifica un sprint: analiza estado actual, propone tareas por rol, estima esfuerzo, identifica riesgos."
allowed-tools: Bash(git:*), Bash(find:*), Bash(wc:*), Read
context: fork
agent: architect
---

## Sprint Planning

### Auto-contexto
- Rama: !`git branch --show-current`
- Últimos commits: !`git log --oneline -10`
- Estado: !`git status --short`
- Archivos modificados recientes: !`git diff --name-only HEAD~10 2>/dev/null | head -20`

### Instrucciones
1. Lee `CLAUDE.md` y `docs/` para contexto
2. Analiza los cambios recientes para determinar qué sprint sigue
3. Propón tareas concretas agrupadas por rol:
   - @agent-backend: endpoints, modelos, servicios
   - @agent-frontend: componentes, pantallas, UX
   - @agent-security: auditorías, controles nuevos
   - @agent-data: migraciones, ETL, análisis
   - @agent-devops: infra, deploy, monitoreo
   - @agent-poleana: motor de juego, tableros
4. Para cada tarea: descripción, archivos, criterio de aceptación, estimado (S/M/L)
5. Identifica dependencias entre tareas y riesgos

### Formato
```
Sprint N — [Tema]
─────────────────
[ROL] Tarea — Archivos — Criterio — Estimado
  ↳ Dependencia: ...
  ↳ Riesgo: ...
```
