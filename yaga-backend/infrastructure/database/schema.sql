-- YAGA PROJECT - Schema para Conductores de Plataformas
-- Copyright (c) 2026 YAGA Project

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Conductores registrados (auth)
CREATE TABLE IF NOT EXISTS conductores (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre          VARCHAR(100) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    telefono        VARCHAR(20),
    activo          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conductores_email ON conductores(email);

-- Vehículos de los conductores
CREATE TABLE IF NOT EXISTS vehiculos (
    id                  SERIAL PRIMARY KEY,
    conductor_id        VARCHAR(100) NOT NULL UNIQUE DEFAULT 'default',
    km_actuales         NUMERIC(10,1) NOT NULL DEFAULT 0,
    km_ultimo_aceite    NUMERIC(10,1) NOT NULL DEFAULT 0,
    km_ultimo_servicio  NUMERIC(10,1) NOT NULL DEFAULT 0,
    rendimiento_kmlt    NUMERIC(5,2) DEFAULT 10.0,
    marca               VARCHAR(100),
    modelo              VARCHAR(100),
    anio                INTEGER,
    color               VARCHAR(50),
    placa               VARCHAR(20),
    notas               TEXT,
    updated_at          TIMESTAMP DEFAULT NOW()
);

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
CREATE INDEX IF NOT EXISTS idx_viajes_jornada ON viajes(jornada_id);
CREATE INDEX IF NOT EXISTS idx_gastos_jornada ON gastos(jornada_id);
CREATE INDEX IF NOT EXISTS idx_jornadas_fecha ON jornadas(fecha);
CREATE INDEX IF NOT EXISTS idx_jornadas_conductor ON jornadas(conductor_id);
