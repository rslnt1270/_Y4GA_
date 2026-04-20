# © YAGA Project — Todos los derechos reservados
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://valkey:6379")
    DB_ENCRYPT_KEY: str = os.getenv("DB_ENCRYPT_KEY", "")

    class Config:
        env_file = ".env"

settings = Settings()
