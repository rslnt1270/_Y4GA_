-- © YAGA Project — Todos los derechos reservados
-- =====================================================================
-- Migración 005: Consentimientos granulares por canal
-- Sprint 8 W1 — LFPDPPP compliance extension
-- =====================================================================
-- Permite que un usuario otorgue/revoque consentimiento diferenciado por
-- canal de comunicación (email, push, sms, whatsapp) dentro de la misma
-- finalidad (marketing, investigacion). La finalidad "operacion" siempre
-- usa canal='general' y es_obligatorio=true.
-- =====================================================================

BEGIN;

-- 1. Columna canal
ALTER TABLE consentimientos
    ADD COLUMN IF NOT EXISTS canal TEXT NOT NULL DEFAULT 'general'
    CHECK (canal IN ('general', 'email', 'push', 'sms', 'whatsapp'));

COMMENT ON COLUMN consentimientos.canal IS
    'Canal de comunicación al que aplica el consentimiento. general=operación núcleo (no revocable), email/push/sms/whatsapp=canales opcionales para marketing/investigacion.';

-- 2. Columna fecha_revocacion
ALTER TABLE consentimientos
    ADD COLUMN IF NOT EXISTS fecha_revocacion TIMESTAMPTZ NULL;

COMMENT ON COLUMN consentimientos.fecha_revocacion IS
    'Timestamp UTC de revocación del consentimiento. NULL si sigue activo. Preservado para auditoría LFPDPPP 7 años.';

-- 3. Drop constraint anterior (si existe)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'consentimientos_usuario_id_finalidad_key'
    ) THEN
        ALTER TABLE consentimientos
            DROP CONSTRAINT consentimientos_usuario_id_finalidad_key;
    END IF;
END $$;

-- 4. Nueva constraint incluyendo canal
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'consentimientos_usuario_id_finalidad_canal_key'
    ) THEN
        ALTER TABLE consentimientos
            ADD CONSTRAINT consentimientos_usuario_id_finalidad_canal_key
            UNIQUE (usuario_id, finalidad, canal);
    END IF;
END $$;

-- 5. Índice parcial sobre revocaciones activas (para reportes de opt-out)
CREATE INDEX IF NOT EXISTS idx_consentimientos_revocacion
    ON consentimientos(fecha_revocacion)
    WHERE fecha_revocacion IS NOT NULL;

COMMIT;
