-- © YAGA Project — Todos los derechos reservados
-- ============================================================
-- Migración 003: UNIQUE constraint + columna es_obligatorio en consentimientos
-- Sprint 5 · 2026-04-07
-- Ejecutar: psql -U yaga_user -d yaga_db -f 003_consentimientos_unique_obligatorio.sql
-- ============================================================
-- Idempotente: seguro de re-ejecutar.

BEGIN;

-- 1. Agregar columna es_obligatorio si no existe
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'consentimientos' AND column_name = 'es_obligatorio'
    ) THEN
        ALTER TABLE consentimientos
            ADD COLUMN es_obligatorio BOOLEAN NOT NULL DEFAULT FALSE;
        RAISE NOTICE 'Columna es_obligatorio agregada';
    ELSE
        RAISE NOTICE 'Columna es_obligatorio ya existe — skip';
    END IF;
END $$;

-- 2. Backfill: finalidades de operación son obligatorias (no revocables)
UPDATE consentimientos
SET es_obligatorio = TRUE
WHERE finalidad = 'operacion'
  AND es_obligatorio = FALSE;

-- 3. Eliminar duplicados si existen (conservar el más reciente por id)
DELETE FROM consentimientos a
USING consentimientos b
WHERE a.id < b.id
  AND a.usuario_id = b.usuario_id
  AND a.finalidad = b.finalidad;

-- 4. Agregar constraint UNIQUE si no existe
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'unique_usuario_finalidad'
    ) THEN
        ALTER TABLE consentimientos
            ADD CONSTRAINT unique_usuario_finalidad
            UNIQUE (usuario_id, finalidad);
        RAISE NOTICE 'Constraint unique_usuario_finalidad creado';
    ELSE
        RAISE NOTICE 'Constraint unique_usuario_finalidad ya existe — skip';
    END IF;
END $$;

COMMIT;
