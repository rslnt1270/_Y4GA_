---
description: "Auditoría de seguridad: secretos, OWASP, PII, tokens, WAF."
allowed-tools: Bash(grep:*), Bash(find:*), Bash(cat:*), Read
context: fork
agent: security
---

## Auditoría de Seguridad

### Escaneo automático
- Secretos en código: !`grep -rn "password\|secret\|key\|token\|DB_ENCRYPT" app/ frontend/src/ --include="*.py" --include="*.ts" --include="*.js" 2>/dev/null | grep -v node_modules | grep -v ".pyc" | head -20`
- localStorage: !`grep -rn "localStorage\|sessionStorage" frontend/src/ 2>/dev/null | head -10`
- SQL inseguro: !`grep -rn "pgp_sym_encrypt\|f\".*SELECT\|f\".*INSERT" app/ --include="*.py" 2>/dev/null | head -10`
- Env files tracked: !`git ls-files | grep -E "\.env|\.pem|\.key" 2>/dev/null`

### Instrucciones
1. Lee `.claude/skills/security/SKILL.md` para el modelo de amenazas
2. Ejecuta los escaneos automáticos arriba
3. Para cada hallazgo, clasifica: CRITICAL / HIGH / MEDIUM / LOW
4. Sugiere corrección concreta con código

### Formato de reporte
```
[SEVERITY] Hallazgo
  Ubicación: archivo:línea
  Riesgo: descripción del impacto
  Fix: código o comando concreto
```
