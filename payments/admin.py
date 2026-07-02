from django.contrib import admin
from .models import SubscriptionPlan, Subscription, Transaction, WalletTopUp, ScheduledReport


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'monthly_cost', 'max_children', 'priority_matching', 'is_active')
    list_filter = ('is_active', 'priority_matching')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('parent', 'plan', 'status', 'billing_cycle', 'next_billing_date', 'started_at')
    list_filter = ('status', 'billing_cycle', 'plan')
    search_fields = ('parent__user__full_name', 'parent__user__email')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'parent', 'payment_type', 'amount', 'payment_method', 'status', 'processed_at')
    list_filter = ('payment_type', 'payment_method', 'status')
    search_fields = ('transaction_id', 'parent__user__full_name', 'reference')
    readonly_fields = ('processed_at',)


@admin.register(WalletTopUp)
class WalletTopUpAdmin(admin.ModelAdmin):
    list_display = ('parent', 'credits', 'amount_paid', 'created_at')
    search_fields = ('parent__user__full_name',)


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ('report_type', 'frequency', 'last_run', 'is_active')
    list_filter = ('frequency', 'is_active')
