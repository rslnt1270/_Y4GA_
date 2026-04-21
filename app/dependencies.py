# © YAGA Project
"""
Dependencias de autenticación — Sistema A (HS256 + asyncpg).
Todos los endpoints autenticados pasan por get_current_user().
"""
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from services.auth_service import decode_token
from services.database import get_pool

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Valida token HS256 y retorna usuario como dict vía asyncpg.

    Raises:
        HTTPException 401: Token inválido, expirado o usuario eliminado.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, nombre, deleted_at FROM usuarios WHERE id = $1",
        user_id,
    )

    if not row:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    if row["deleted_at"] is not None:
        raise HTTPException(status_code=401, detail="Cuenta desactivada")

    return dict(row)
