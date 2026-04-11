from django.contrib import admin

from billing.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'amount', 'currency', 'user', 'description')
    list_filter = ('currency',)
    search_fields = ('description', 'user__username', 'user__email')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
