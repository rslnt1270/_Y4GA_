# © YAGA Project — Todos los derechos reservados
"""
core/limiter.py — Instancia compartida de slowapi para rate limiting.

Separado de main.py para evitar importaciones circulares con los routers.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
