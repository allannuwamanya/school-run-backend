from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import BaseModel, Parent


class SubscriptionPlan(BaseModel):
    """
    A subscription tier available to parents (e.g. Standard, Premium, Family+).
    """
    name = models.CharField(max_length=100, unique=True)
    monthly_cost = models.DecimalField(max_digits=10, decimal_places=2)
    max_children = models.PositiveSmallIntegerField(
        default=1, help_text='Number of children covered by this plan.'
    )
    priority_matching = models.BooleanField(
        default=False, help_text='Whether this plan gets priority driver matching.'
    )
    features = models.JSONField(
        default=list, blank=True,
        help_text='List of feature strings displayed in-app.'
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (₦{self.monthly_cost}/mo)"

    class Meta:
        verbose_name = 'Subscription Plan'
        verbose_name_plural = 'Subscription Plans'


class Subscription(BaseModel):
    """
    A parent's active (or past) subscription to a plan.
    """
    ACTIVE = 'active'
    CANCELLED = 'cancelled'
    OVERDUE = 'overdue'
    TRIAL = 'trial'
    STATUS_CHOICES = [
        (ACTIVE, _('Active')),
        (CANCELLED, _('Cancelled')),
        (OVERDUE, _('Overdue')),
        (TRIAL, _('Trial')),
    ]

    MONTHLY = 'monthly'
    ANNUAL = 'annual'
    BILLING_CHOICES = [
        (MONTHLY, _('Monthly')),
        (ANNUAL, _('Annual')),
    ]

    parent = models.ForeignKey(
        Parent, on_delete=models.CASCADE, related_name='subscriptions'
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, related_name='subscriptions'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CHOICES, default=MONTHLY)
    next_billing_date = models.DateField(null=True, blank=True)
    started_at = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.parent} — {self.plan} ({self.status})"

    class Meta:
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
        ordering = ['-started_at']


class Transaction(BaseModel):
    """
    A financial transaction linked to a parent. Covers subscriptions, emergency
    rides, wallet top-ups, and refunds.
    """
    MONTHLY_SUB = 'monthly_sub'
    EMERGENCY = 'emergency'
    TOP_UP = 'top_up'
    REFUND = 'refund'
    PAYMENT_TYPE_CHOICES = [
        (MONTHLY_SUB, _('Monthly Subscription')),
        (EMERGENCY, _('Emergency Ride')),
        (TOP_UP, _('Wallet Top Up')),
        (REFUND, _('Refund')),
    ]

    CARD = 'card'
    BANK_TRANSFER = 'bank_transfer'
    WALLET = 'wallet'
    METHOD_CHOICES = [
        (CARD, _('Card')),
        (BANK_TRANSFER, _('Bank Transfer')),
        (WALLET, _('Wallet')),
    ]

    PAID = 'paid'
    FAILED = 'failed'
    PENDING = 'pending'
    REFUNDED = 'refunded'
    STATUS_CHOICES = [
        (PAID, _('Paid')),
        (FAILED, _('Failed')),
        (PENDING, _('Pending')),
        (REFUNDED, _('Refunded')),
    ]

    transaction_id = models.CharField(max_length=50, unique=True)
    parent = models.ForeignKey(
        Parent, on_delete=models.CASCADE, related_name='transactions'
    )
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(
        max_length=200, null=True, blank=True,
        help_text='Payment gateway reference (Paystack, Flutterwave, etc.)'
    )

    def __str__(self):
        return f"{self.transaction_id} — {self.parent} — ₦{self.amount} ({self.status})"

    class Meta:
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        ordering = ['-processed_at']


class WalletTopUp(BaseModel):
    """
    A purchase of emergency ride credits added to a parent's wallet.
    """
    parent = models.ForeignKey(
        Parent, on_delete=models.CASCADE, related_name='wallet_topups'
    )
    credits = models.PositiveSmallIntegerField(help_text='Number of emergency ride credits purchased')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    transaction = models.OneToOneField(
        Transaction, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='wallet_topup'
    )

    def __str__(self):
        return f"{self.parent} — {self.credits} credits (₦{self.amount_paid})"

    class Meta:
        verbose_name = 'Wallet Top-Up'
        verbose_name_plural = 'Wallet Top-Ups'


class ScheduledReport(BaseModel):
    """
    System-generated report configuration.
    """
    BUSINESS_HEALTH = 'business_health'
    SAFETY_INCIDENTS = 'safety_incidents'
    REVENUE_CHURN = 'revenue_churn'
    DRIVER_PERFORMANCE = 'driver_performance'
    REPORT_TYPE_CHOICES = [
        (BUSINESS_HEALTH, _('Business Health')),
        (SAFETY_INCIDENTS, _('Safety Incidents')),
        (REVENUE_CHURN, _('Revenue & Churn')),
        (DRIVER_PERFORMANCE, _('Driver Performance')),
    ]

    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'
    FREQUENCY_CHOICES = [
        (DAILY, _('Daily')),
        (WEEKLY, _('Weekly')),
        (MONTHLY, _('Monthly')),
    ]

    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES, unique=True)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES, default=WEEKLY)
    last_run = models.DateTimeField(null=True, blank=True)
    recipients = models.JSONField(
        default=list, help_text='List of email addresses to receive this report.'
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.get_report_type_display()} — {self.frequency}"

    class Meta:
        verbose_name = 'Scheduled Report'
        verbose_name_plural = 'Scheduled Reports'
