---
description: "Verifica compliance LFPDPPP: endpoints ARCO, consentimientos, cifrado PII, auditoría."
allowed-tools: Bash(grep:*), Bash(find:*), Read
context: fork
agent: backend
---

## Verificación ARCO — LFPDPPP

### Escaneo
- Rutas ARCO: !`grep -rn "arco\|cancelacion\|rectificacion\|oposicion\|acceso" app/api/ --include="*.py" 2>/dev/null | head -15`
- Consentimientos: !`grep -rn "consentimiento\|finalidad" app/ --include="*.py" 2>/dev/null | head -10`
- Cifrado PII: !`grep -rn "encrypt_pii\|decrypt_pii\|encrypt_value" app/ --include="*.py" 2>/dev/null | head -10`
- Auditoría: !`grep -rn "auditoria\|audit" app/ --include="*.py" 2>/dev/null | head -10`

### Checklist
| # | Requisito | Estado |
|---|-----------|--------|
| 1 | GET /arco/acceso → export JSON datos personales + transaccionales | |
| 2 | PUT /arco/rectificacion → re-cifra PII, valida unicidad | |
| 3 | POST /arco/cancelacion → soft delete, anonimiza, retiene 7 años | |
| 4 | POST /arco/oposicion → revoca finalidades secundarias | |
| 5 | PUT /consentimientos → toggle marketing/investigación | |
| 6 | Finalidades obligatorias no revocables | |
| 7 | GPS logs incluidos en anonimización ARCO | |
| 8 | Toda acción ARCO → tabla auditoria | |
| 9 | Aviso de privacidad accesible en frontend | |

Marca cada uno con ✅/❌/⚠️ y agrega notas.
