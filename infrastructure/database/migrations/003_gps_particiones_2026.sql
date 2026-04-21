-- © YAGA Project — Todos los derechos reservados
-- ============================================================
-- Migración 003: Particiones jornada_gps_logs Jun–Dic 2026
-- Sprint 5 · 2026-04-09
-- Ejecutar: psql -U yaga_user -d yaga_db -f 003_gps_particiones_2026.sql
-- ============================================================

BEGIN;

-- ── Particiones mensuales Jun–Dic 2026 ──────────────────────────
-- Las particiones 2026_03, 2026_04 y 2026_05 fueron creadas en 001.

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_06
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_07
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_08
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_09
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_10
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_11
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE IF NOT EXISTS jornada_gps_logs_2026_12
    PARTITION OF jornada_gps_logs
    FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

-- ── Registro de migración ───────────────────────────────────────
INSERT INTO schema_migrations (version, description)
    VALUES ('003', 'Particiones jornada_gps_logs Jun–Dic 2026')
    ON CONFLICT (version) DO NOTHING;

COMMIT;
