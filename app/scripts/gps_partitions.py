# © YAGA Project — Todos los derechos reservados
"""
gps_partitions.py — Crea particiones futuras de jornada_gps_logs.
Idempotente: puede ejecutarse múltiples veces sin error.
Uso: docker exec yaga_api python3 /app/scripts/gps_partitions.py
"""
import asyncio
import os
from datetime import date
from dateutil.relativedelta import relativedelta

import asyncpg


async def create_future_partitions(months_ahead: int = 3) -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        today = date.today()
        base = today.replace(day=1)

        for i in range(1, months_ahead + 1):
            start = base + relativedelta(months=i)
            end = start + relativedelta(months=1)
            partition_name = f"jornada_gps_logs_{start.year}_{start.month:02d}"

            exists = await conn.fetchval(
                "SELECT to_regclass($1) IS NOT NULL", partition_name
            )
            if exists:
                print(f"[OK] Ya existe: {partition_name}")
                continue

            await conn.execute(f"""
                CREATE TABLE {partition_name}
                PARTITION OF jornada_gps_logs
                FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')
            """)
            print(f"[CREADA] {partition_name} ({start.isoformat()} → {end.isoformat()})")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_future_partitions(months_ahead=3))
