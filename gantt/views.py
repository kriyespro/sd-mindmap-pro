from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.generic import TemplateView

from gantt.services import compute_gantt_layout, get_gantt_tasks
from gantt.models import TaskDependency
from planner.models import Task
from projects.models import Project
from projects.services import get_user_projects


class GanttProjectListView(LoginRequiredMixin, TemplateView):
    template_name = 'gantt/project_list.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['projects'] = get_user_projects(self.request.user)
        return ctx


class GanttView(LoginRequiredMixin, TemplateView):
    template_name = 'gantt/gantt.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = get_object_or_404(Project, slug=kwargs['slug'])
        view = self.request.GET.get('view', 'weekly')
        if view not in ('daily', 'weekly', 'monthly', 'quarterly', 'yearly'):
            view = 'weekly'
        tasks = get_gantt_tasks(project)
        layout = compute_gantt_layout(tasks, view=view)
        deps = TaskDependency.objects.filter(
            predecessor__project=project
        ).select_related('predecessor', 'successor')
        ctx.update({
            'project': project,
            'gantt': layout,
            'gantt_view': view,
            'dependencies': list(deps),
        })
        return ctx


class GanttPartialView(LoginRequiredMixin, View):
    """HTMX partial: re-render Gantt rows for a project."""

    def get(self, request, slug):
        from django.template.loader import render_to_string
        project = get_object_or_404(Project, slug=slug)
        view = request.GET.get('view', 'weekly')
        if view not in ('daily', 'weekly', 'monthly', 'quarterly', 'yearly'):
            view = 'weekly'
        tasks = get_gantt_tasks(project)
        layout = compute_gantt_layout(tasks, view=view)
        html = render_to_string(
            'gantt/_gantt_rows.jinja',
            {'gantt': layout, 'project': project, 'gantt_view': view},
            request=request,
        )
        return HttpResponse(html)


class TaskDateUpdateView(LoginRequiredMixin, View):
    """HTMX POST: update task start/end dates from Gantt drag."""

    def post(self, request, task_id):
        from planner.services import user_can_access_task
        task = get_object_or_404(Task, pk=task_id)
        if not user_can_access_task(request.user, task):
            return HttpResponse(status=403)
        start = request.POST.get('start_date')
        end = request.POST.get('due_date')
        from datetime import date as date_type
        import datetime
        if start:
            try:
                task.start_date = datetime.date.fromisoformat(start)
            except ValueError:
                pass
        if end:
            try:
                task.due_date = datetime.date.fromisoformat(end)
            except ValueError:
                pass
        task.save(update_fields=['start_date', 'due_date'])
        return HttpResponse(status=204)
