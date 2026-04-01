-- © YAGA Project — Todos los derechos reservados
-- ============================================================
-- Migración 001: GPS logs + campos de viaje expandidos
-- Sprint 3 · 2026-03-31
-- Ejecutar: psql -U yaga_user -d yaga_db -f 001_gps_viajes_upgrade.sql
-- ============================================================

BEGIN;

-- ── 1. CAMPOS NUEVOS EN viajes ───────────────────────────────
ALTER TABLE viajes
    ADD COLUMN IF NOT EXISTS tipo_servicio       VARCHAR(20)
        CHECK (tipo_servicio IN ('x','xl','comfort','flash','moto','cargo','otro')),
    ADD COLUMN IF NOT EXISTS monto_oferta_inicial NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS monto_final_app      NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS ganancia_real_calculada NUMERIC(10,2),
    ADD COLUMN IF NOT EXISTS caseta               NUMERIC(8,2)  DEFAULT 0,
    ADD COLUMN IF NOT EXISTS distancia_gps_km     NUMERIC(8,3),
    ADD COLUMN IF NOT EXISTS duracion_real_min     NUMERIC(8,2);

COMMENT ON COLUMN viajes.monto_oferta_inicial    IS 'Monto que mostró la app al conductor al recibir el viaje';
COMMENT ON COLUMN viajes.monto_final_app         IS 'Monto liquidado por la app al finalizar el viaje';
COMMENT ON COLUMN viajes.ganancia_real_calculada IS 'monto_final_app - caseta - gastos_proporcionales (calculado server-side)';
COMMENT ON COLUMN viajes.distancia_gps_km        IS 'Distancia calculada desde jornada_gps_logs con geopy';

-- ── 2. TABLA jornada_gps_logs ─────────────────────────────────
-- Particionada por mes para evitar table bloat con alta frecuencia
CREATE TABLE IF NOT EXISTS jornada_gps_logs (
    id            BIGSERIAL,
    jornada_id    UUID         NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
    -- lat/lng cifrados AES-256 en capa de aplicación (BYTEA)
    lat_cifrado   BYTEA        NOT NULL,
    lng_cifrado   BYTEA        NOT NULL,
    -- velocidad y timestamp en claro (no son PII directa)
    vel_kmh       NUMERIC(6,1),
    precision_m   NUMERIC(8,2),
    ts            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

-- Particiones iniciales (Q2 2026 + retrospectiva Q1)
CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_03
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_04
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_05
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- BRIN index: ideal para series temporales (insert-order ≈ timestamp-order)
CREATE INDEX IF NOT EXISTS idx_gps_logs_ts
    ON jornada_gps_logs USING BRIN (ts) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS idx_gps_logs_jornada
    ON jornada_gps_logs (jornada_id, ts DESC);

COMMENT ON TABLE jornada_gps_logs IS
    'GPS track de jornadas. lat/lng cifrados AES-256. Particionado mensual.';

-- ── 3. TABLA viajes_historicos (si no existe aún) ──────────────
CREATE TABLE IF NOT EXISTS viajes_historicos (
    id            BIGSERIAL PRIMARY KEY,
    trip_id       TEXT UNIQUE NOT NULL,
    conductor_id  TEXT NOT NULL,
    fecha_local   TIMESTAMPTZ,
    monto_bruto   NUMERIC(10,2),
    duracion_min  NUMERIC(8,2),
    distancia_km  NUMERIC(8,3),
    eficiencia_km NUMERIC(8,3),
    plataforma    TEXT DEFAULT 'UberX',
    origen        TEXT,
    destino       TEXT,
    lat           NUMERIC(12,8),
    lng           NUMERIC(12,8),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vh_conductor
    ON viajes_historicos (conductor_id, fecha_local DESC);

-- ── 4. REGISTRO DE MIGRACIONES ────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(50) PRIMARY KEY,
    applied_at  TIMESTAMPTZ DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_migrations (version, description)
    VALUES ('001', 'GPS logs + campos viaje expandidos + viajes_historicos')
    ON CONFLICT (version) DO NOTHING;

COMMIT;
