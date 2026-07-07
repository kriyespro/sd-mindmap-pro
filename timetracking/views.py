from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone

from timetracking.models import TimeEntry
from timetracking.services import (
    format_seconds,
    get_daily_seconds,
    get_recent_entries,
    get_running_timer,
    get_weekly_seconds,
    start_timer,
    stop_timer,
)


class TimeTrackingView(LoginRequiredMixin, TemplateView):
    template_name = 'timetracking/index.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        today = date.today()
        running = get_running_timer(user)
        ctx.update({
            'running': running,
            'entries': get_recent_entries(user),
            'today_seconds': get_daily_seconds(user, today),
            'week_seconds': get_weekly_seconds(user, today),
            'today_formatted': format_seconds(get_daily_seconds(user, today)),
            'week_formatted': format_seconds(get_weekly_seconds(user, today)),
            'today': today,
        })
        return ctx


class TimerStartView(LoginRequiredMixin, View):
    def post(self, request):
        description = request.POST.get('description', '').strip()
        entry = start_timer(request.user, description=description)
        if request.headers.get('HX-Request'):
            from django.template.loader import render_to_string
            html = render_to_string('timetracking/_timer_widget.jinja', {
                'running': entry,
            }, request=request)
            return HttpResponse(html, headers={'HX-Trigger': 'timerStarted'})
        from django.shortcuts import redirect
        return redirect('timetracking:index')


class TimerStopView(LoginRequiredMixin, View):
    def post(self, request):
        entry = stop_timer(request.user)
        if request.headers.get('HX-Request'):
            from django.template.loader import render_to_string
            html = render_to_string('timetracking/_timer_widget.jinja', {
                'running': None,
            }, request=request)
            return HttpResponse(html, headers={'HX-Trigger': 'timerStopped'})
        from django.shortcuts import redirect
        return redirect('timetracking:index')


class TimeEntryDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(TimeEntry, pk=pk, user=request.user)
        entry.delete()
        if request.headers.get('HX-Request'):
            return HttpResponse('')
        from django.shortcuts import redirect
        return redirect('timetracking:index')


class TimeEntryManualView(LoginRequiredMixin, View):
    """Add a manual time log entry."""
    def post(self, request):
        description = request.POST.get('description', '').strip()
        hours_str = request.POST.get('hours', '0')
        minutes_str = request.POST.get('minutes', '0')
        try:
            hours = max(0, int(hours_str))
            minutes = max(0, min(59, int(minutes_str)))
        except ValueError:
            hours, minutes = 0, 0
        seconds = hours * 3600 + minutes * 60
        if seconds <= 0:
            return HttpResponse('Enter valid time', status=400)
        entry = TimeEntry.objects.create(
            user=request.user,
            description=description,
            duration_seconds=seconds,
            status=TimeEntry.STATUS_STOPPED,
            started_at=timezone.now(),
            stopped_at=timezone.now(),
        )
        if request.headers.get('HX-Request'):
            from django.template.loader import render_to_string
            html = render_to_string('timetracking/_entry_row.jinja', {'entry': entry}, request=request)
            return HttpResponse(html, headers={'HX-Trigger': 'entryAdded'})
        from django.shortcuts import redirect
        return redirect('timetracking:index')
