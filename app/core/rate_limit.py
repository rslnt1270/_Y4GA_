# © YAGA Project — Todos los derechos reservados
"""
core/rate_limit.py — Instancia compartida de slowapi Limiter.

Se importa tanto en main.py como en los routers que necesiten rate limiting.
Almacenamiento en Redis DB 1 (separado de tokens/reset en DB 0).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379/1")
