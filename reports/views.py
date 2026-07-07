from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from reports.services import (
    get_dashboard_stats,
    get_overdue_tasks,
    get_project_progress,
    get_tasks_by_priority,
    get_tasks_by_status,
    get_upcoming_milestones,
)


class ReportsDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/dashboard.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx.update({
            'stats': get_dashboard_stats(user),
            'project_progress': get_project_progress(user),
            'tasks_by_status': get_tasks_by_status(user),
            'tasks_by_priority': get_tasks_by_priority(user),
            'overdue_tasks': get_overdue_tasks(user),
            'upcoming_milestones': get_upcoming_milestones(user),
        })
        return ctx
