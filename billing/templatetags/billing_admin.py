from decimal import Decimal

from django import template
from django.db.models import Sum

register = template.Library()


@register.simple_tag
def billing_total_collected() -> Decimal:
    from billing.models import Payment

    s = Payment.objects.aggregate(t=Sum('amount'))['t']
    return s or Decimal('0')
