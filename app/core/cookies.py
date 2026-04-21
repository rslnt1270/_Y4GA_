# © YAGA Project — Todos los derechos reservados
"""
core/cookies.py — Helpers de cookies para el flujo Refresh Token (Sprint 10).

Centraliza atributos de la cookie `yaga_rt` y la validación de Origin, para
que los endpoints de auth no repitan la configuración. El comportamiento
cambia según `ENVIRONMENT`:
    production  → Secure=on, Origin estricto (`APP_ORIGIN`, default y4ga.app)
    development → Secure=off (HTTP local), Origin permite localhost/127.0.0.1
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Request, Response

REFRESH_COOKIE_NAME = "yaga_rt"
REFRESH_COOKIE_PATH = "/api/v1/auth"  # solo viaja a /refresh y /logout

_ENV = os.getenv("ENVIRONMENT", "development").lower()
_IS_PROD = _ENV in ("production", "prod")
_PROD_ORIGIN = os.getenv("APP_ORIGIN", "https://y4ga.app")
_DEV_ORIGIN_PREFIXES = (
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
)


def set_refresh_cookie(response: Response, token_id: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token_id,
        max_age=max_age_seconds,
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=_IS_PROD,
        samesite="strict",
    )


def get_refresh_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(REFRESH_COOKIE_NAME)


def validate_origin(request: Request) -> bool:
    """
    Defensa en profundidad contra CSRF (además de SameSite=Strict).
    Acepta header Origin; si falta, falla (fetch() moderno siempre lo envía en POST).
    """
    origin = request.headers.get("origin") or ""
    if not origin:
        return False
    if _IS_PROD:
        return origin == _PROD_ORIGIN
    if origin == _PROD_ORIGIN:
        return True
    return any(origin.startswith(p) for p in _DEV_ORIGIN_PREFIXES)
