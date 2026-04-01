---
name: data
description: "Esquema de BD, migraciones, anonimización, dataset de viajes, y patrones ETL para YAGA."
---

# Data Engineering YAGA — Referencia

## Esquema actual (post Sprint 3)

### Tablas core
```sql
usuarios        UUID PK, email, email_cifrado BYTEA, phone, phone_cifrado BYTEA, 
                password_hash, roles TEXT[], deleted_at (soft delete)
viajes          UUID PK, usuario_id FK, jornada_id FK, plataforma, monto, metodo_pago,
                propina, tipo_servicio, monto_oferta_inicial, monto_final_app,
                ganancia_real_calculada, distancia_gps_km
gastos          UUID PK, usuario_id FK, jornada_id FK, categoria, monto
jornadas        UUID PK, usuario_id FK, fecha, estado, inicio, fin
consentimientos SERIAL PK, usuario_id FK, finalidad, estado, es_obligatorio, UNIQUE(usuario_id, finalidad)
auditoria       BIGSERIAL PK, usuario_id, accion, ip INET, user_agent, detalles JSONB
```

### Tabla GPS (Sprint 3)
```sql
jornada_gps_logs  BIGSERIAL PK, jornada_id FK, lat_cifrado BYTEA, lng_cifrado BYTEA,
                  velocidad NUMERIC, timestamp TIMESTAMPTZ, precisión NUMERIC
-- Particionada por rango mensual
-- BRIN index en timestamp
-- Sin usuario_id directo (se deriva de jornada → usuario)
```

## Proceso de anonimización (ARCO cancelación)
```sql
BEGIN;
  UPDATE usuarios SET email='anon_<uuid>@deleted', phone=NULL,
    email_cifrado=NULL, phone_cifrado=NULL, deleted_at=NOW() WHERE id=$1;
  UPDATE viajes SET usuario_id=NULL WHERE usuario_id=$1;
  UPDATE gastos SET usuario_id=NULL WHERE usuario_id=$1;
  UPDATE jornadas SET usuario_id=NULL WHERE usuario_id=$1;
  -- GPS logs: anonimizar coordenadas (2 decimales) después de 7 años
  INSERT INTO auditoria(usuario_id,accion,detalles) VALUES($1,'arco_cancelacion','{}');
COMMIT;
```

## Dataset comparativo
- ~3,300 viajes reales Uber, Valle de México, Jun 2024 – Feb 2026
- Fuente 1: PDFs semanales Uber (pdfplumber + regex)
- Fuente 2: JSON interceptado (Playwright network capture)
- Fusión: YagaDataFusionEngine → delta calculations → color-coded discrepancies
- Endpoint: `/api/v1/comparativa`

## Patrones
- Migraciones: `IF NOT EXISTS`, `DO $$` guards, idempotentes
- Bulk insert: `INSERT INTO t SELECT * FROM UNNEST($1::uuid[], $2::bytea[], ...)`
- Particionado: `CREATE TABLE gps_logs_2026_01 PARTITION OF jornada_gps_logs FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')`
