-- YAGA PROJECT - Schema para Conductores de Plataformas
-- Copyright (c) 2026 YAGA Project

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Jornadas de trabajo
CREATE TABLE IF NOT EXISTS jornadas (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conductor_id    TEXT NOT NULL DEFAULT 'default',
    fecha           DATE NOT NULL DEFAULT CURRENT_DATE,
    inicio          TIMESTAMPTZ,
    fin             TIMESTAMPTZ,
    estado          VARCHAR(20) DEFAULT 'activa' CHECK (estado IN ('activa','cerrada')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Viajes registrados por voz
CREATE TABLE IF NOT EXISTS viajes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jornada_id      UUID REFERENCES jornadas(id),
    plataforma      VARCHAR(20) NOT NULL CHECK (plataforma IN ('uber','didi','cabify','indriver','rappi','ubereats','otro')),
    monto           NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    metodo_pago     VARCHAR(20) NOT NULL CHECK (metodo_pago IN ('efectivo','tarjeta','app')),
    propina         NUMERIC(10,2) DEFAULT 0,
    distancia_km    NUMERIC(8,2),
    duracion_min    NUMERIC(8,2),
    notas           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Gastos registrados por voz
CREATE TABLE IF NOT EXISTS gastos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jornada_id      UUID REFERENCES jornadas(id),
    categoria       VARCHAR(30) NOT NULL CHECK (categoria IN ('gasolina','comida','mantenimiento','lavado','estacionamiento','otro')),
    monto           NUMERIC(10,2) NOT NULL CHECK (monto > 0),
    descripcion     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para consultas rápidas
CREATE INDEX idx_viajes_jornada ON viajes(jornada_id);
CREATE INDEX idx_gastos_jornada ON gastos(jornada_id);
CREATE INDEX idx_jornadas_fecha ON jornadas(fecha);
CREATE INDEX idx_jornadas_conductor ON jornadas(conductor_id);
