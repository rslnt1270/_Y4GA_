from sqlalchemy import Column, String, Boolean, DateTime, ARRAY, LargeBinary, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    email_cifrado = Column(LargeBinary, nullable=False)
    phone = Column(String(20), unique=True)
    phone_cifrado = Column(LargeBinary)
    password_hash = Column(String, nullable=False)
    roles = Column(ARRAY(String))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True))
