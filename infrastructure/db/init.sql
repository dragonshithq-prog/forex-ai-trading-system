-- =============================================================================
-- Forex AI Trading Platform — PostgreSQL Initialization Script
-- =============================================================================
-- This script runs on first database initialization (container startup).
-- It creates the database, user, installs required extensions, and sets
-- appropriate connection limits and performance parameters.
--
-- Applied automatically by:
--   - Docker: Mounted to /docker-entrypoint-initdb.d/
--   - K8s:    Run as an init Job or via manual migration
-- =============================================================================

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 1: Database & User Setup
-- ═════════════════════════════════════════════════════════════════════════════

-- Create the trading database (if not exists)
-- NOTE: In Docker, the database is already created by POSTGRES_DB env var.
-- This is provided for K8s and manual setups.
SELECT 'CREATE DATABASE forex_trading'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'forex_trading')\gexec

-- Create application user with limited permissions
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'forex') THEN
        CREATE ROLE forex WITH LOGIN PASSWORD 'changeme_db_password';
    END IF;
END
$$;

-- Grant minimal required permissions
GRANT CONNECT ON DATABASE forex_trading TO forex;
GRANT USAGE ON SCHEMA public TO forex;
GRANT CREATE ON SCHEMA public TO forex;

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 2: Extension Installation
-- ═════════════════════════════════════════════════════════════════════════════

-- pgcrypto: Cryptographic functions for password hashing, UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- pg_stat_statements: Query performance monitoring
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- pg_trgm: Trigram text search for fuzzy matching (useful for search features)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- uuid-ossp: UUID generation (alternative to pgcrypto's gen_random_uuid())
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- btree_gin: GIN index support for composite types
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 3: Connection Limits & Resource Management
-- ═════════════════════════════════════════════════════════════════════════════

-- Set connection limits for the application user
ALTER ROLE forex CONNECTION LIMIT 50;

-- Limit guest/anonymous connections
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'forex_readonly') THEN
        ALTER ROLE forex_readonly CONNECTION LIMIT 20;
    END IF;
END
$$;

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 4: Schema & Default Privileges
-- ═════════════════════════════════════════════════════════════════════════════

-- Connect to the target database before setting schema permissions
\c forex_trading

-- Grant schema-level permissions
GRANT USAGE, CREATE ON SCHEMA public TO forex;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO forex;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO forex;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO forex;

-- Set default privileges for future objects created by forex user
ALTER DEFAULT PRIVILEGES FOR ROLE forex IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO forex;

ALTER DEFAULT PRIVILEGES FOR ROLE forex IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO forex;

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 5: Performance Tuning (Session Level)
-- ═════════════════════════════════════════════════════════════════════════════

-- These are session-level defaults; system-level tuning is in postgresql.conf
ALTER ROLE forex SET statement_timeout = '30000';      -- 30 seconds
ALTER ROLE forex SET idle_in_session_timeout = '60000'; -- 60 seconds idle timeout
ALTER ROLE forex SET search_path = public;
ALTER ROLE forex SET work_mem = '64MB';
ALTER ROLE forex SET maintenance_work_mem = '256MB';

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 6: Monitoring & Auditing
-- ═════════════════════════════════════════════════════════════════════════════

-- Create a schema for audit logging (separate from application schema)
CREATE SCHEMA IF NOT EXISTS audit;

-- Grant access to audit schema
GRANT USAGE, CREATE ON SCHEMA audit TO forex;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA audit TO forex;
ALTER DEFAULT PRIVILEGES FOR ROLE forex IN SCHEMA audit
    GRANT SELECT, INSERT ON TABLES TO forex;

-- Create pg_stat_statements view for easy monitoring
CREATE OR REPLACE VIEW audit.query_stats AS
SELECT
    queryid,
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 100;

-- Grant select on the view
GRANT SELECT ON audit.query_stats TO forex;

-- ═════════════════════════════════════════════════════════════════════════════
-- SECTION 7: Verification
-- ═════════════════════════════════════════════════════════════════════════════

-- Verify extensions are installed
SELECT 'Extension Check:' as info, e.extname, e.extversion
FROM pg_extension e
WHERE e.extname IN ('pgcrypto', 'pg_stat_statements', 'pg_trgm', 'uuid-ossp');

-- Verify roles exist
SELECT 'Role Check:' as info, r.rolname, r.rolcanlogin, r.rolconnlimit
FROM pg_catalog.pg_roles r
WHERE r.rolname IN ('forex', 'postgres');

-- Verify database exists
SELECT 'Database Check:' as info, d.datname, d.datconnlimit
FROM pg_catalog.pg_database d
WHERE d.datname = 'forex_trading';
