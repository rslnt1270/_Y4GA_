---
description: "Valida el motor de Poleana: parseo de tableros, grafo, branch points, conteo de pasos, y reglas."
allowed-tools: Bash(node:*), Bash(cat:*), Bash(grep:*), Read
context: fork
agent: poleana
---

## Test del Motor Poleana

### Instrucciones
1. Lee `.claude/skills/poleana/SKILL.md`
2. Verifica que los 4 TABLERO*.txt tengan formato alfanumérico
3. Ejecuta los tests de grafo abajo
4. Reporta: path completo, branch points, diagonales, y bugs

### Tests a ejecutar (si node disponible)
```javascript
// Crear script temporal y ejecutar con node
// Test 1: ¿Los 4 tableros parsean correctamente?
// Test 2: ¿El path de 0 a 56 está completo?
// Test 3: ¿Los branch points detectan risk/safe?
// Test 4: ¿El conteo 8+8 = 16 (safe) o 2a (risk)?
// Test 5: ¿Las diagonales de esquina se resuelven?
```

### Validación visual
- Verificar que los 6 gaps diagonales conocidos están conectados:
  - 6a→7a, 6b→7b, 6c→7c (esquinas de zona)
  - 51→52, 53→54, 56→57 (rampa de meta)
- Verificar que las safe lanes están desconectadas del main path
  (15-17, 29-31, 43-45 no aparecen en tracePath pero son alcanzables via walkGraph safe)
