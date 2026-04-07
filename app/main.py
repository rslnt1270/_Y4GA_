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
from api.v1.arco import router as arco_router
from services.database import get_pool, close_pool
from api.poleana_router import router as poleana_router
from api.poleana_redis_rooms import close_redis as close_poleana_redis
from dependencies import get_current_user
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.rate_limit import limiter
# Sistema B (RS256) movido a app/legacy/ — ver auth_sistema_b.py, core_auth_sistema_b.py
# Archivos legacy NO deben importarse. Funcionalidad ARCO reimplementada en api/v1/arco.py


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_poleana_redis()
    await close_pool()


app = FastAPI(
    title="YAGA - Asistente para Conductores",
    description="Registra tus viajes y gastos con comandos de voz. GPS tracking cifrado AES-256.",
    version="0.5.0",
    docs_url="/api/docs",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://y4ga.app", "https://www.y4ga.app"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    allow_credentials=True,
    max_age=600,
)

app.include_router(auth_router, prefix="/api/v1", tags=["Auth"])
app.include_router(vehiculo_router, prefix="/api/v1", tags=["Vehículo"])
app.include_router(nlp_router, prefix="/api/v1", tags=["Comandos"])
app.include_router(historico_router, prefix="/api/v1", tags=["Historico"])
app.include_router(gps_router, tags=["GPS"])
app.include_router(arco_router, prefix="/api/v1/arco", tags=["ARCO"])
app.include_router(poleana_router)
# Sistema B eliminado — archivos movidos a app/legacy/


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "yaga-conductores", "version": "0.4.0"}


@app.post("/api/v1/jornada/cerrar", tags=["Operación"])
async def cerrar_jornada(current_user=Depends(get_current_user), pool=Depends(get_pool)):
    """Cierra la jornada activa del conductor autenticado."""
    async with pool.acquire() as conn:
        query_update = """
            UPDATE jornadas
            SET estado = 'cerrada', fin = NOW()
            WHERE fecha = CURRENT_DATE AND estado = 'activa' AND conductor_id = $1
            RETURNING id;
        """
        jornada = await conn.fetchrow(query_update, str(current_user.id))
        if not jornada:
            raise HTTPException(status_code=400, detail="No hay una jornada abierta para cerrar hoy.")

        stats = await conn.fetchrow("""
            SELECT COUNT(v.id) as total_viajes,
                   COALESCE(SUM(v.monto), 0) as total_ingresos,
                   (SELECT COALESCE(SUM(monto), 0) FROM gastos WHERE jornada_id = $1) as total_gastos
            FROM viajes v WHERE v.jornada_id = $1;
        """, jornada['id'])

        # Promedio histórico real del conductor (no hardcodeado)
        hist_ref = await conn.fetchval(
            "SELECT COALESCE(AVG(monto_bruto), 72.94) FROM viajes_historicos WHERE conductor_id = $1",
            str(current_user.id)
        )

        ingresos = float(stats['total_ingresos'])
        gastos = float(stats['total_gastos'])
        viajes = stats['total_viajes']
        utilidad = ingresos - gastos
        promedio_hoy = ingresos / viajes if viajes > 0 else 0
        delta = ((promedio_hoy - hist_ref) / hist_ref * 100) if hist_ref else 0

        return {
            "status": "Jornada Cerrada",
            "resumen": {
                "total_neto": f"${utilidad:,.2f} MXN",
                "viajes": viajes,
                "ingreso_promedio_viaje": f"${promedio_hoy:.2f}",
            },
            "rendimiento_vs_historico": {
                "delta_pct": f"{delta:+.1f}%",
                "mensaje": "Día por encima del promedio" if delta > 0 else "Hoy estuviste bajo tu promedio histórico."
            }
        }
