# © YAGA Project — Todos los derechos reservados
"""
Script de retención de datos LFPDPPP.

Ejecutar diariamente via cron:
  0 3 * * * docker exec yaga_api python /app/scripts/cleanup_old_transactions.py

Política:
- Retiene transaccionales 7 años (2557 días) desde created_at.
- Solo elimina registros de usuarios con soft delete (deleted_at IS NOT NULL).
- Exporta a CSV antes de eliminar (auditoría).
- NO toca viajes_historicos (datos de referencia, sin PII directa).
"""

import asyncio
import csv
import logging
import os
import sys
from datetime import datetime

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("yaga.cleanup")

DATABASE_URL = os.getenv("DATABASE_URL")
RETENTION_INTERVAL = "7 years"
ARCHIVE_DIR = "/tmp"


async def _export_to_csv(conn: asyncpg.Connection, table: str, rows: list[asyncpg.Record]) -> str:
    """Exporta registros a CSV en ARCHIVE_DIR. Retorna ruta del archivo."""
    if not rows:
        return ""
    datestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(ARCHIVE_DIR, f"yaga_archive_{table}_{datestamp}.csv")
    columns = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
    log.info("Archivo exportado: %s (%d registros)", path, len(rows))
    return path


async def cleanup():
    if not DATABASE_URL:
        log.error("DATABASE_URL no configurada. Abortando.")
        sys.exit(1)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # --- Identificar usuarios eliminados (soft delete) ---
        deleted_users = await conn.fetch(
            "SELECT id FROM usuarios WHERE deleted_at IS NOT NULL"
        )
        if not deleted_users:
            log.info("Sin usuarios con soft delete. Nada que limpiar.")
            return

        deleted_ids = [r["id"] for r in deleted_users]
        log.info("Usuarios con soft delete: %d", len(deleted_ids))

        # --- Jornadas de esos usuarios ---
        jornada_ids = await conn.fetch(
            """
            SELECT id FROM jornadas
            WHERE conductor_id::text = ANY($1::text[])
            """,
            [str(uid) for uid in deleted_ids],
        )
        if not jornada_ids:
            log.info("Sin jornadas asociadas a usuarios eliminados.")
            return

        j_ids = [r["id"] for r in jornada_ids]

        # --- VIAJES expirados (> 7 años y de usuarios eliminados) ---
        viajes_expired = await conn.fetch(
            """
            SELECT v.* FROM viajes v
            WHERE v.jornada_id = ANY($1::uuid[])
              AND v.created_at < NOW() - INTERVAL '7 years'
            """,
            j_ids,
        )
        log.info("Viajes expirados encontrados: %d", len(viajes_expired))

        if viajes_expired:
            await _export_to_csv(conn, "viajes", viajes_expired)
            v_ids = [r["id"] for r in viajes_expired]
            deleted_count = await conn.execute(
                "DELETE FROM viajes WHERE id = ANY($1::uuid[])",
                v_ids,
            )
            log.info("Viajes eliminados: %s", deleted_count)

        # --- GASTOS expirados (> 7 años y de usuarios eliminados) ---
        gastos_expired = await conn.fetch(
            """
            SELECT g.* FROM gastos g
            WHERE g.jornada_id = ANY($1::uuid[])
              AND g.created_at < NOW() - INTERVAL '7 years'
            """,
            j_ids,
        )
        log.info("Gastos expirados encontrados: %d", len(gastos_expired))

        if gastos_expired:
            await _export_to_csv(conn, "gastos", gastos_expired)
            g_ids = [r["id"] for r in gastos_expired]
            deleted_count = await conn.execute(
                "DELETE FROM gastos WHERE id = ANY($1::uuid[])",
                g_ids,
            )
            log.info("Gastos eliminados: %s", deleted_count)

        log.info("Limpieza completada exitosamente.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(cleanup())
