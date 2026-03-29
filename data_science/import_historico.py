"""
YAGA PROJECT - Importador de Dataset Histórico Uber
Copyright (c) 2026 YAGA Project
3,300 viajes reales - Valle de México 2024
"""
import csv
import asyncio
import asyncpg
from datetime import datetime

DATABASE_URL = "postgresql://yaga_user:Yaga2026SecurePass@localhost:5432/yaga_db"
CSV_PATH = "/home/ec2-user/yaga-project/YAGA_DataSet_Clean.csv"


async def import_historico():
    conn = await asyncpg.connect(DATABASE_URL)

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"📂 Leyendo {len(rows)} viajes...")

    insertados = 0
    errores = 0

    for row in rows:
        try:
            await conn.execute("""
                INSERT INTO viajes_historicos
                    (trip_id, fecha_local, monto_bruto, duracion_min,
                     distancia_km, eficiencia_km, ciudad, origen, destino)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (trip_id) DO NOTHING
            """,
                row["trip_id"],
                datetime.fromisoformat(row["fecha_local"]),
                float(row["monto_bruto"]),
                float(row["duracion_min"]),
                float(row["distancia_km"]),
                float(row["eficiencia_por_km"]),
                row["ciudad"],
                row["origen"],
                row["destino"],
            )
            insertados += 1
        except Exception as e:
            errores += 1
            if errores <= 3:
                print(f"⚠️  Error en fila {insertados+errores}: {e}")

    await conn.close()

    print(f"✅ Importados: {insertados} viajes")
    print(f"⚠️  Errores:    {errores}")
    print(f"📊 Total:       {insertados + errores}")


if __name__ == "__main__":
    asyncio.run(import_historico())
