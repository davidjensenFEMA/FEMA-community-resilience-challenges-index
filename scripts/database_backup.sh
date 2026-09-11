#!/bin/bash
#
# Database Backup Script for FEMA CRIA
#
# This script backs up the PostgreSQL database to compressed SQL files.
#
# Usage:
#   ./scripts/database_backup.sh                    # Backup with timestamp
#   ./scripts/database_backup.sh custom_name        # Backup with custom name
#   ./scripts/database_backup.sh --help             # Show help
#

set -e  # Exit on error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="${PROJECT_ROOT}/backups"
CONTAINER_NAME="cria_postgres"
DB_USER="cria_user"
DB_NAME="cria_db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Help message
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "FEMA CRIA Database Backup Script"
    echo ""
    echo "Usage:"
    echo "  $0                    # Create timestamped backup"
    echo "  $0 custom_name        # Create backup with custom name"
    echo "  $0 --help             # Show this help message"
    echo ""
    echo "Backups are stored in: ${BACKUP_DIR}"
    echo "Format: cria_backup_YYYYMMDD_HHMMSS.sql.gz"
    exit 0
fi

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Determine backup filename
if [ -n "$1" ]; then
    BACKUP_FILE="${BACKUP_DIR}/cria_backup_${1}_${TIMESTAMP}.sql"
else
    BACKUP_FILE="${BACKUP_DIR}/cria_backup_${TIMESTAMP}.sql"
fi

echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}FEMA CRIA Database Backup${NC}"
echo -e "${GREEN}==================================================${NC}"
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

# Get database statistics before backup
echo ""
echo "Database Statistics:"
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

# Create backup
echo -n "Creating backup... "
if docker exec "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" "${DB_NAME}" > "${BACKUP_FILE}" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Compress backup
echo -n "Compressing backup... "
if gzip "${BACKUP_FILE}"; then
    echo -e "${GREEN}OK${NC}"
    BACKUP_FILE="${BACKUP_FILE}.gz"
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

# Get backup file size
BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)

echo ""
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}Backup Complete!${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo "  File: ${BACKUP_FILE}"
echo "  Size: ${BACKUP_SIZE}"
echo "  Database: ${DB_NAME}"
echo "  Records: See statistics above"
echo ""
echo "To restore this backup:"
echo "  ./scripts/database_restore.sh ${BACKUP_FILE}"
echo ""

# List recent backups
BACKUP_COUNT=$(ls -1 "${BACKUP_DIR}"/cria_backup_*.sql.gz 2>/dev/null | wc -l)
if [ "${BACKUP_COUNT}" -gt 1 ]; then
    echo "Recent backups (latest 5):"
    ls -lht "${BACKUP_DIR}"/cria_backup_*.sql.gz | head -5 | awk '{printf "  %s  %-10s  %s\n", $6" "$7" "$8, $5, $9}'
    echo ""

    # Warn if too many backups
    if [ "${BACKUP_COUNT}" -gt 30 ]; then
        echo -e "${YELLOW}Warning: You have ${BACKUP_COUNT} backups. Consider cleaning old backups:${NC}"
        echo -e "${YELLOW}  find ${BACKUP_DIR} -name 'cria_backup_*.sql.gz' -mtime +30 -delete${NC}"
        echo ""
    fi
fi

exit 0
