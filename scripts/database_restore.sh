#!/bin/bash
#
# Database Restore Script for FEMA CRIA
#
# This script restores a PostgreSQL database from a backup file.
#
# Usage:
#   ./scripts/database_restore.sh backups/cria_backup_20251108_120000.sql.gz
#   ./scripts/database_restore.sh --help
#
# WARNING: This will overwrite all existing data in the database!
#

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONTAINER_NAME="cria_postgres"
DB_USER="cria_user"
DB_NAME="cria_db"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Help message
if [ "$1" == "--help" ] || [ "$1" == "-h" ] || [ -z "$1" ]; then
    echo "FEMA CRIA Database Restore Script"
    echo ""
    echo "Usage:"
    echo "  $0 BACKUP_FILE        # Restore from backup file"
    echo "  $0 --help             # Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 backups/cria_backup_20251108_120000.sql.gz"
    echo ""
    echo -e "${YELLOW}WARNING: This will overwrite all existing data!${NC}"
    echo ""

    # List available backups
    BACKUP_DIR="${PROJECT_ROOT}/backups"
    if [ -d "${BACKUP_DIR}" ]; then
        BACKUP_COUNT=$(ls -1 "${BACKUP_DIR}"/cria_backup_*.sql.gz 2>/dev/null | wc -l)
        if [ "${BACKUP_COUNT}" -gt 0 ]; then
            echo "Available backups:"
            ls -lht "${BACKUP_DIR}"/cria_backup_*.sql.gz | head -10 | awk '{printf "  %s  %-10s  %s\n", $6" "$7" "$8, $5, $9}'
        else
            echo "No backups found in ${BACKUP_DIR}"
        fi
    fi
    echo ""
    exit 0
fi

BACKUP_FILE="$1"

echo -e "${YELLOW}==================================================${NC}"
echo -e "${YELLOW}FEMA CRIA Database Restore${NC}"
echo -e "${YELLOW}WARNING: This will OVERWRITE existing data!${NC}"
echo -e "${YELLOW}==================================================${NC}"
echo ""

# Check if backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    echo -e "${RED}Error: Backup file not found: ${BACKUP_FILE}${NC}"
    exit 1
fi

echo "Backup file: ${BACKUP_FILE}"
echo "Backup size: $(du -h "${BACKUP_FILE}" | cut -f1)"
echo "Target database: ${DB_NAME}"
echo ""

# Check if container is running
echo -n "Checking PostgreSQL container... "
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}FAILED${NC}"
    echo -e "${RED}Error: Container '${CONTAINER_NAME}' is not running${NC}"
    echo "Start it with: docker compose -f docker/docker-compose.yml up -d postgres"
    exit 1
fi
echo -e "${GREEN}OK${NC}"

# Test database connection
echo -n "Testing database connection... "
if ! docker exec "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}FAILED${NC}"
    echo -e "${RED}Error: Cannot connect to database${NC}"
    exit 1
fi
echo -e "${GREEN}OK${NC}"

# Show current database statistics
echo ""
echo "Current Database Statistics:"
docker exec "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c "
    SELECT
        'Reference Indicators: ' || COUNT(*) FROM reference_indicators
    UNION ALL
    SELECT 'Geographies: ' || COUNT(*) FROM geographies
    UNION ALL
    SELECT 'Source Data: ' || COUNT(*) FROM source_data
    UNION ALL
    SELECT 'Indicators: ' || COUNT(*) FROM indicators
    UNION ALL
    SELECT 'Aggregates: ' || COUNT(*) FROM aggregate_indicators;
" | sed 's/^[ \t]*/  /' 2>/dev/null || echo "  (empty database)"
echo ""

# Confirm restoration
echo -e "${YELLOW}This will DELETE all existing data and restore from backup.${NC}"
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    echo "Restoration cancelled."
    exit 0
fi

echo ""
echo "Starting restoration..."
echo ""

# Decompress if needed
TEMP_FILE=""
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    echo -n "Decompressing backup... "
    TEMP_FILE="${BACKUP_FILE%.gz}"
    if gunzip -c "${BACKUP_FILE}" > "${TEMP_FILE}"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED${NC}"
        rm -f "${TEMP_FILE}"
        exit 1
    fi
    RESTORE_FILE="${TEMP_FILE}"
else
    RESTORE_FILE="${BACKUP_FILE}"
fi

# Drop existing data
echo -n "Clearing existing data... "
if docker exec "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "
    TRUNCATE TABLE aggregate_indicators, indicators, source_data,
                  geographies, data_years, reference_indicators CASCADE;
" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    [ -n "${TEMP_FILE}" ] && rm -f "${TEMP_FILE}"
    exit 1
fi

# Restore from backup
echo -n "Restoring from backup... "
if cat "${RESTORE_FILE}" | docker exec -i "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    [ -n "${TEMP_FILE}" ] && rm -f "${TEMP_FILE}"
    exit 1
fi

# Clean up temporary file
[ -n "${TEMP_FILE}" ] && rm -f "${TEMP_FILE}"

# Show restored database statistics
echo ""
echo "Restored Database Statistics:"
docker exec "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c "
    SELECT
        'Reference Indicators: ' || COUNT(*) FROM reference_indicators
    UNION ALL
    SELECT 'Geographies: ' || COUNT(*) FROM geographies
    UNION ALL
    SELECT 'Source Data: ' || COUNT(*) FROM source_data
    UNION ALL
    SELECT 'Indicators: ' || COUNT(*) FROM indicators
    UNION ALL
    SELECT 'Aggregates: ' || COUNT(*) FROM aggregate_indicators;
" | sed 's/^[ \t]*/  /'

# Get database size
DB_SIZE=$(docker exec "${CONTAINER_NAME}" psql -U "${DB_USER}" -d "${DB_NAME}" -t -c "
    SELECT pg_size_pretty(pg_database_size('${DB_NAME}'));
" | tr -d ' ')
echo "  Database Size: ${DB_SIZE}"

echo ""
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}Restore Complete!${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo "Database '${DB_NAME}' has been restored from:"
echo "  ${BACKUP_FILE}"
echo ""

exit 0
