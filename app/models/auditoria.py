from sqlalchemy import Column, BigInteger, String, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import UUID, INET
from models.usuario import Base

class Auditoria(Base):
    __tablename__ = "auditoria"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id = Column(UUID(as_uuid=True))
    accion = Column(String, nullable=False)
    ip = Column(INET)
    user_agent = Column(String)
    detalles = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
