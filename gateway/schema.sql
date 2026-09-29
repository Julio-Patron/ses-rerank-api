-- ==========================================================================
-- SES Enterprise Gateway: Esquema de Base de Datos (PostgreSQL)
-- ==========================================================================
-- Este script define el esquema relacional para soportar autenticación,
-- multi-tenancy, rate limiting y telemetría de uso para facturación.
-- ==========================================================================

-- Activar la extensión para generar UUIDs nativos (requiere superusuario)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- 1. Tabla: TENANTS (Clientes/Organizaciones)
-- ==========================================
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    plan_tier VARCHAR(50) DEFAULT 'developer', -- Niveles: developer, pro, enterprise
    rate_limit_per_minute INT NOT NULL DEFAULT 60, -- Límite base inyectado a Redis
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- 2. Tabla: API KEYS (Gestión de Acceso)
-- ==========================================
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE, -- SHA-256 hash de la llave
    key_prefix VARCHAR(15) NOT NULL, -- Prefijo (ej: 'ses_live_a1b2...') para mostrar en UI
    status VARCHAR(20) DEFAULT 'active', -- Estados: active, revoked, paused
    credits_remaining INT DEFAULT 1000,
    tokens_saved_total INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ
);

-- Índices optimizados para validaciones ultrarrápidas en middleware
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);

-- ==========================================
-- 3. Tabla: USAGE LOGS (Facturación y Auditoría)
-- ==========================================
CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    endpoint_accessed VARCHAR(255) NOT NULL,
    tokens_consumed INT DEFAULT 0, -- Estimación de consumo (tamaño del contexto RAG)
    processing_time_ms FLOAT, -- Duración de inferencia/búsqueda
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índice optimizado para consolidaciones de facturación mensuales rápidas
CREATE INDEX IF NOT EXISTS idx_usage_logs_tenant_date ON usage_logs(tenant_id, created_at);
