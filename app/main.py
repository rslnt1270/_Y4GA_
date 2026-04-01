# © YAGA Project — Todos los derechos reservados
"""
YAGA PROJECT - API Principal v0.5.0
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api.v1.nlp import router as nlp_router
from api.v1.vehiculo import router as vehiculo_router
from api.v1.auth import router as auth_router
from api.v1.historico import router as historico_router
from api.v1.gps import router as gps_router
from services.database import get_pool, close_pool
from api.poleana_router import router as poleana_router
from routers.auth import router as auth_router_new
from routers.consentimientos import router as consentimientos_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(
    title="YAGA - Asistente para Conductores",
    description="Registra tus viajes y gastos con comandos de voz. GPS tracking cifrado AES-256.",
    version="0.5.0",
    docs_url="/api/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1", tags=["Auth"])
app.include_router(vehiculo_router, prefix="/api/v1", tags=["Vehículo"])
app.include_router(nlp_router, prefix="/api/v1", tags=["Comandos"])
app.include_router(historico_router, prefix="/api/v1", tags=["Historico"])
app.include_router(gps_router, tags=["GPS"])
app.include_router(poleana_router)
app.include_router(auth_router_new)                     # autenticación JWT (/auth/...)
app.include_router(consentimientos_router)              # gestión de consentimientos (/consentimientos)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "yaga-conductores", "version": "0.4.0"}


@app.post("/api/v1/jornada/cerrar", tags=["Operación"])
async def cerrar_jornada(pool=Depends(get_pool)):
    async with pool.acquire() as conn:
        query_update = """
            UPDATE jornadas
            SET estado = 'cerrada', fin = NOW()
            WHERE fecha = CURRENT_DATE AND estado = 'activa'
            RETURNING id;
        """
        jornada = await conn.fetchrow(query_update)

        if not jornada:
            raise HTTPException(status_code=400, detail="No hay una jornada abierta para cerrar hoy.")

        query_stats = """
            SELECT
                COUNT(v.id) as total_viajes,
                COALESCE(SUM(v.monto), 0) as total_ingresos,
                (SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE jornada_id = $1) as total_gastos
            FROM viajes v
            WHERE v.jornada_id = $1;
        """
        stats = await conn.fetchrow(query_stats, jornada['id'])

        ingresos = float(stats['total_ingresos'])
        gastos = float(stats['total_gastos'])
        viajes = stats['total_viajes']
        utilidad = ingresos - gastos
        promedio_hoy = ingresos / viajes if viajes > 0 else 0

        HISTORICO_REF = 72.94
        delta = ((promedio_hoy - HISTORICO_REF) / HISTORICO_REF) * 100

        return {
            "status": "Jornada Cerrada",
            "resumen": {
                "total_neto": f"${utilidad:,.2f} MXN",
                "viajes": viajes,
                "ingreso_promedio_viaje": f"${promedio_hoy:.2f}",
            },
            "rendimiento_vs_historico": {
                "delta_pct": f"{delta:+.1f}%",
                "mensaje": "Dia por encima del promedio" if delta > 0 else "Hoy estuviste bajo el promedio historico."
            }
        }
