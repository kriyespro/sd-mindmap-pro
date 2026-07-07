from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.views.generic import TemplateView

from calendar_app.services import build_calendar_weeks, get_calendar_events


class CalendarView(LoginRequiredMixin, TemplateView):
    template_name = 'calendar/month.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        try:
            year = int(self.request.GET.get('year', today.year))
            month = int(self.request.GET.get('month', today.month))
        except ValueError:
            year, month = today.year, today.month
        month = max(1, min(12, month))

        events = get_calendar_events(self.request.user, year, month)
        weeks = build_calendar_weeks(year, month)

        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1

        import calendar
        ctx.update({
            'year': year,
            'month': month,
            'month_name': date(year, month, 1).strftime('%B %Y'),
            'weeks': weeks,
            'events': events,
            'today': today,
            'prev_year': prev_year,
            'prev_month': prev_month,
            'next_year': next_year,
            'next_month': next_month,
            'day_names': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        })
        return ctx


class CalendarMonthPartialView(LoginRequiredMixin, TemplateView):
    template_name = 'calendar/_month_grid.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        try:
            year = int(self.request.GET.get('year', today.year))
            month = int(self.request.GET.get('month', today.month))
        except ValueError:
            year, month = today.year, today.month
        month = max(1, min(12, month))

        events = get_calendar_events(self.request.user, year, month)
        weeks = build_calendar_weeks(year, month)

        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1

        ctx.update({
            'year': year,
            'month': month,
            'month_name': date(year, month, 1).strftime('%B %Y'),
            'weeks': weeks,
            'events': events,
            'today': today,
            'prev_year': prev_year,
            'prev_month': prev_month,
            'next_year': next_year,
            'next_month': next_month,
        })
        return ctx
