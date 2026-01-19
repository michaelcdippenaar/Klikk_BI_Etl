#!/bin/bash
# Script to reset migrations without dropping database
# This unapplies all migrations and then reapplies them
# Usage: ./reset_migrations.sh [environment] [app_name]

ENV=${1:-development}
APP_NAME=${2:-investec}
export DJANGO_ENV=$ENV

echo "Resetting migrations for app: $APP_NAME (environment: $ENV)"
echo "============================================================"

# Activate virtual environment
source venv/bin/activate

# Get the last migration number (zero state would be before 0001)
echo "Step 1: Finding migrations to unapply..."
python manage.py showmigrations $APP_NAME | grep -E "\[X\]" | tail -1

echo ""
echo "Step 2: Unapplying all migrations (fake)..."
# Unapply all migrations by going to zero state
python manage.py migrate $APP_NAME zero --fake

if [ $? -eq 0 ]; then
    echo "✓ All migrations unapplied (fake)"
else
    echo "✗ Error unapplying migrations"
    exit 1
fi

echo ""
echo "Step 3: Reapplying all migrations..."
python manage.py migrate $APP_NAME

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ All migrations reapplied successfully!"
    echo ""
    echo "Step 4: Verifying migration status..."
    python manage.py showmigrations $APP_NAME
else
    echo ""
    echo "✗ Error reapplying migrations"
    exit 1
fi

echo ""
echo "Migration reset complete!"
