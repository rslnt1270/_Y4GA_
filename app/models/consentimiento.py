from sqlalchemy import Column, Integer, UUID, String, Boolean, DateTime, UniqueConstraint, func
from models.usuario import Base

class Consentimiento(Base):
    __tablename__ = "consentimientos"
    __table_args__ = (
        UniqueConstraint('usuario_id', 'finalidad', name='unique_usuario_finalidad'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(UUID(as_uuid=True), nullable=False)
    finalidad = Column(String, nullable=False)
    estado = Column(Boolean, nullable=False, default=False)
    es_obligatorio = Column(Boolean, nullable=False, default=False)
    fecha_otorgamiento = Column(DateTime(timezone=True))
    fecha_revocacion = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
