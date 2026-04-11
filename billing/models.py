from decimal import Decimal

from django.conf import settings
from django.db import models


class Payment(models.Model):
    """Manual or integrated payment log; summed on admin home for revenue."""

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Amount collected (e.g. subscription or one-time).',
    )
    currency = models.CharField(max_length=8, default='USD')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='payments',
    )
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'payment'
        verbose_name_plural = 'payments'

    def __str__(self) -> str:
        return f'{self.currency} {self.amount} @ {self.created_at:%Y-%m-%d}'

    @classmethod
    def total_collected(cls) -> Decimal:
        from django.db.models import Sum

        agg = cls.objects.aggregate(s=Sum('amount'))
        return agg['s'] or Decimal('0')
