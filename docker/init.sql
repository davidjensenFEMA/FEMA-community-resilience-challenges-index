-- Database initialization script
-- This runs when the PostgreSQL container is first created

-- Create test database for pytest
CREATE DATABASE cria_test_db;

-- Grant privileges to cria_user
GRANT ALL PRIVILEGES ON DATABASE cria_db TO cria_user;
GRANT ALL PRIVILEGES ON DATABASE cria_test_db TO cria_user;

-- Connect to main database and create extensions if needed
\c cria_db;

-- Future: PostGIS extension for spatial queries
-- CREATE EXTENSION IF NOT EXISTS postgis;

-- Future: pg_trgm for fuzzy text matching
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Connect to test database and create same extensions
\c cria_test_db;

-- Same extensions for test database
-- CREATE EXTENSION IF NOT EXISTS postgis;
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;
