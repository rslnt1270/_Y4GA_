"""
YAGA PROJECT - API Principal
Copyright (c) 2026 YAGA Project
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.nlp import router as nlp_router
from services.database import get_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    yield
    await close_pool()


app = FastAPI(
    title="YAGA - Asistente para Conductores",
    description="Registra tus viajes y gastos con comandos de voz",
    version="0.3.0",
    docs_url="/api/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(nlp_router, prefix="/api/v1", tags=["Comandos"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "yaga-conductores", "version": "0.3.0"}
