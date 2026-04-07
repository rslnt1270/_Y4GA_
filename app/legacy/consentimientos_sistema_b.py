from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert
from pydantic import BaseModel
from datetime import datetime
from db import get_db
from models.consentimiento import Consentimiento
from models.auditoria import Auditoria
from dependencies import get_current_user
from models.usuario import Usuario

router = APIRouter(prefix="/consentimientos", tags=["Consentimientos"])

class ConsentimientoUpdate(BaseModel):
    finalidad: str
    estado: bool

@router.get("/")
async def list_consentimientos(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Consentimiento).where(Consentimiento.usuario_id == current_user.id)
    )
    consentimientos = result.scalars().all()
    return consentimientos

@router.put("/")
async def update_consentimiento(
    data: ConsentimientoUpdate,
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    result = await db.execute(
        select(Consentimiento).where(
            Consentimiento.usuario_id == current_user.id,
            Consentimiento.finalidad == data.finalidad
        )
    )
    existing = result.scalar_one_or_none()
    now = datetime.utcnow()
    if existing:
        old_state = existing.estado
        existing.estado = data.estado
        if data.estado:
            existing.fecha_otorgamiento = now
            existing.fecha_revocacion = None
        else:
            existing.fecha_revocacion = now
        await db.commit()
        await db.refresh(existing)
    else:
        old_state = None
        nuevo = Consentimiento(
            usuario_id=current_user.id,
            finalidad=data.finalidad,
            estado=data.estado,
            fecha_otorgamiento=now if data.estado else None,
            fecha_revocacion=None if data.estado else now
        )
        db.add(nuevo)
        await db.commit()
        await db.refresh(nuevo)
        existing = nuevo

    # Registrar en auditoría
    await db.execute(
        insert(Auditoria).values(
            usuario_id=current_user.id,
            accion="consent_change",
            ip=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None,
            detalles={
                "finalidad": data.finalidad,
                "nuevo_estado": data.estado,
                "anterior_estado": old_state
            }
        )
    )
    await db.commit()

    return existing
