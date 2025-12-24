from django.contrib import admin
from .models import InvestecJseTransaction, InvestecJsePortfolio, InvestecJseShareNameMapping


@admin.register(InvestecJseTransaction)
class InvestecJseTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'year', 'month', 'day', 'account_number', 'share_name', 'type', 'quantity', 'value', 'value_per_share', 'value_calculated', 'created_at']
    list_filter = ['date', 'year', 'month', 'type', 'account_number']
    search_fields = ['account_number', 'share_name', 'description']
    date_hierarchy = 'date'


@admin.register(InvestecJsePortfolio)
class InvestecJsePortfolioAdmin(admin.ModelAdmin):
    list_display = ['date', 'year', 'month', 'day', 'company', 'share_code', 'quantity', 'currency', 'unit_cost', 'total_cost', 'price', 'total_value', 'profit_loss']
    list_filter = ['date', 'year', 'month', 'currency', 'company']
    search_fields = ['company', 'share_code']
    date_hierarchy = 'date'
    readonly_fields = ['created_at', 'updated_at']


@admin.register(InvestecJseShareNameMapping)
class InvestecJseShareNameMappingAdmin(admin.ModelAdmin):
    list_display = ['share_name', 'company', 'share_code', 'created_at', 'updated_at']
    list_filter = ['company']
    search_fields = ['share_name', 'company', 'share_code']
    readonly_fields = ['created_at', 'updated_at']
