-- © YAGA Project — Todos los derechos reservados
-- Migración 002: añade nombre y telefono_texto a usuarios
-- Sprint 3 patch · 2026-04-01
BEGIN;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS nombre   VARCHAR(120) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS telefono VARCHAR(20);

-- Índice para búsquedas por conductor_id (alias semántico de id)
CREATE INDEX IF NOT EXISTS idx_usuarios_nombre ON usuarios (nombre);

INSERT INTO schema_migrations (version, description)
    VALUES ('002', 'usuarios: campos nombre + telefono para conductores')
    ON CONFLICT (version) DO NOTHING;

COMMIT;
