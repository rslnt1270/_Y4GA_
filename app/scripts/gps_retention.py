# © YAGA Project — Todos los derechos reservados
"""
gps_retention.py — Elimina particiones de jornada_gps_logs con datos > retention_months.
Compliance LFPDPPP: GPS es PII, retención máxima 12 meses.
Uso: docker exec yaga_api python3 /app/scripts/gps_retention.py
"""
import asyncio
import os
import re
from datetime import date
from dateutil.relativedelta import relativedelta

import asyncpg

PARTITION_PATTERN = re.compile(r"^jornada_gps_logs_(\d{4})_(\d{2})$")


async def drop_old_partitions(retention_months: int = 12, dry_run: bool = False) -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        cutoff = date.today().replace(day=1) - relativedelta(months=retention_months)

        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE tablename LIKE 'jornada_gps_logs_%' ORDER BY tablename"
        )

        for row in rows:
            name = row["tablename"]
            m = PARTITION_PATTERN.match(name)
            if not m:
                print(f"[SKIP] Nombre no reconocido: {name}")
                continue

            year, month = int(m.group(1)), int(m.group(2))
            partition_date = date(year, month, 1)

            if partition_date < cutoff:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {name}")
                if dry_run:
                    print(f"[DRY-RUN] Eliminaría: {name} ({count} registros, fecha {partition_date})")
                else:
                    await conn.execute(f"DROP TABLE {name}")
                    print(f"[ELIMINADA] {name} ({count} registros, fecha {partition_date})")
            else:
                print(f"[RETENIDA] {name} (fecha {partition_date}, dentro de {retention_months} meses)")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(drop_old_partitions(retention_months=12, dry_run=True))
