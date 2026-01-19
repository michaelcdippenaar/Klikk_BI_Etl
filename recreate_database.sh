#!/bin/bash
# Script to recreate database and rerun all migrations
# Usage: ./recreate_database.sh [environment]

ENV=${1:-development}
export DJANGO_ENV=$ENV

echo "Recreating database for environment: $ENV"
echo "=========================================="

# Get database credentials from environment or use defaults
DB_NAME=${DB_NAME:-klikk_financials}
DB_USER=${DB_USER:-klikk_user}
DB_PASSWORD=${DB_PASSWORD:-StrongPasswordHere}
DB_HOST=${DB_HOST:-127.0.0.1}
DB_PORT=${DB_PORT:-5432}

echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo "Host: $DB_HOST"
echo ""

# Activate virtual environment
source venv/bin/activate

echo "Step 1: Dropping and recreating database..."
export PGPASSWORD="$DB_PASSWORD"

# Drop existing database (ignore errors if it doesn't exist)
psql -h "$DB_HOST" -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>&1 | grep -v "does not exist" || true

# Create new database
psql -h "$DB_HOST" -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" || {
    echo "Error: Could not create database. Please check your credentials and PostgreSQL server."
    unset PGPASSWORD
    exit 1
}

echo "✓ Database created successfully"
echo ""

echo "Step 2: Running migrations..."
python manage.py migrate

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ All migrations applied successfully!"
    echo ""
    echo "Step 3: Verifying migration status..."
    python manage.py showmigrations
else
    echo ""
    echo "✗ Error applying migrations"
    unset PGPASSWORD
    exit 1
fi

unset PGPASSWORD
echo ""
echo "Database recreation complete!"
