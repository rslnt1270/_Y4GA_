import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # JWT — Sistema A activo usa HS256 (auth_service.py). RS256 está deshabilitado.
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
    JWT_PRIVATE_KEY_FILE: str = ""
    JWT_PUBLIC_KEY_FILE: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    # REDIS_URL debe incluir la contraseña: redis://:<VALKEY_PASSWORD>@valkey:6379
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://valkey:6379")
    DB_ENCRYPT_KEY: str = os.getenv("DB_ENCRYPT_KEY", "")

    class Config:
        env_file = ".env"

    def get_jwt_private_key(self) -> str:
        if self.JWT_PRIVATE_KEY_FILE and Path(self.JWT_PRIVATE_KEY_FILE).exists():
            return Path(self.JWT_PRIVATE_KEY_FILE).read_text()
        return self.JWT_PRIVATE_KEY

    def get_jwt_public_key(self) -> str:
        if self.JWT_PUBLIC_KEY_FILE and Path(self.JWT_PUBLIC_KEY_FILE).exists():
            return Path(self.JWT_PUBLIC_KEY_FILE).read_text()
        return self.JWT_PUBLIC_KEY

settings = Settings()
