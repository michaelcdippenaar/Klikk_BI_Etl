#!/bin/bash
# Script to create database dump for Klikk ETL
# Usage: ./create_database_dump.sh [database_name] [host] [user] [password]

# Default values (can be overridden by environment variables or arguments)
DB_NAME=${1:-${DB_NAME:-klikk_financials}}
DB_HOST=${2:-${DB_HOST:-127.0.0.1}}
DB_USER=${3:-${DB_USER:-klikk_user}}
DB_PASSWORD=${4:-${DB_PASSWORD:-StrongPasswordHere}}

# Generate filename with date
DUMP_FILE="Klikk_ETL_$(date +%Y%m%d).sql"

echo "Creating database dump..."
echo "Database: $DB_NAME"
echo "Host: $DB_HOST"
echo "User: $DB_USER"
echo "Output file: $DUMP_FILE"

# Create dump using custom format (compressible, restorable)
export PGPASSWORD="$DB_PASSWORD"
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -F c -f "$DUMP_FILE"

if [ $? -eq 0 ]; then
    echo "✓ Dump created successfully: $DUMP_FILE"
    ls -lh "$DUMP_FILE"
    
    # Optionally create a plain SQL format as well
    SQL_FILE="Klikk_ETL_$(date +%Y%m%d)_plain.sql"
    echo "Creating plain SQL format: $SQL_FILE"
    pg_restore -f "$SQL_FILE" "$DUMP_FILE" 2>/dev/null || pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -F p -f "$SQL_FILE"
    
    if [ $? -eq 0 ]; then
        echo "✓ Plain SQL dump created: $SQL_FILE"
        ls -lh "$SQL_FILE"
    fi
else
    echo "✗ Error creating dump. Please check your database credentials and connection."
    exit 1
fi

unset PGPASSWORD
